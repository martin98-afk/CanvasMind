# -*- coding: utf-8 -*-
import time
from typing import Dict, List

from PyQt5.QtCore import QThread, pyqtSignal
from openai import OpenAI, APIError, Timeout, APIConnectionError, RateLimitError, BadRequestError, APITimeoutError


class OpenAIChatWorker(QThread):
    content_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished_with_content = pyqtSignal(str)

    def __init__(self, messages: List[Dict], llm_config: Dict):
        super().__init__()
        self.messages = messages
        self.llm_config = llm_config
        self.full_response = ""
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def _check_cancel(self) -> bool:
        return self._is_cancelled

    def run(self):
        try:
            api_key = self.llm_config.get("API_KEY", "").strip()
            base_url = self.llm_config.get("API_URL") or None
            model = self.llm_config.get("模型名称", "gpt-4o").strip()
            temperature = float(self.llm_config.get("温度", 0.7))
            max_tokens = int(self.llm_config.get("最大Token", 2048))
            enable_thinking = bool(self.llm_config.get("是否思考", True))

            if not model:
                self.error_occurred.emit("[错误] 模型名称未配置")
                return

            # 设置超时（连接 + 读取）
            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=60.0,  # 总超时 60 秒
                max_retries=2  # 最多重试 2 次
            )

            # 构建请求参数
            req_kwargs = {
                "model": model,
                "messages": self.messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }

            # 仅对支持 thinking 的官方 API 才加 extra_body（避免第三方报错）
            # 这里保守处理：只在 base_url 为 None 或 openai 官方域名时启用
            if enable_thinking and (not base_url or "openai" in (base_url or "")):
                req_kwargs["extra_body"] = {
                    "enable_thinking": True,
                    "chat_template_kwargs": {"enable_thinking": True}
                }

            # 执行请求
            stream = client.chat.completions.create(**req_kwargs)

            self.full_response = ""
            last_chunk_time = time.time()

            for chunk in stream:
                if self._is_cancelled:
                    self.error_occurred.emit("[已取消] 用户手动中止请求")
                    return

                # 防止无限等待（虽然有 timeout，但流式可能卡在某 chunk）
                if time.time() - last_chunk_time > 30:
                    self.error_occurred.emit("[超时] 流式响应超过 30 秒无数据")
                    return

                if chunk.choices and chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    self.full_response += content
                    self.content_received.emit(content)
                    last_chunk_time = time.time()

            self.finished_with_content.emit(self.full_response)


        except BadRequestError as e:

            self.error_occurred.emit(f"[请求错误] {e.message or str(e)}")

        except RateLimitError:

            self.error_occurred.emit("[速率限制] 请求过于频繁，请稍后再试")

        except APIConnectionError:

            self.error_occurred.emit("[连接失败] 无法连接到 API 服务器，请检查网络或 API_URL")

        except APITimeoutError:  # ✅ 使用 APITimeoutError

            self.error_occurred.emit("[超时] 请求超时（60秒），请检查网络或模型负载")

        except APIError as e:

            # 专门处理上下文超长的情况

            error_str = str(e)

            if "context length" in error_str and "overflow" in error_str:

                self.error_occurred.emit(error_str)

            else:

                self.error_occurred.emit(f"[API 错误] {error_str}")

        except ValueError as e:

            self.error_occurred.emit(f"[配置错误] 参数类型无效: {str(e)}")

        except Exception as e:

            error_str = str(e)

            if "max_tokens" in error_str.lower() or "context length" in error_str.lower():

                self.error_occurred.emit("[错误] 模型上下文或最大Token超出限制，请减少输入长度或调低 max_tokens")

            else:

                self.error_occurred.emit(f"[未知错误] {error_str}")
