# -*- coding: utf-8 -*-
import time
from typing import Dict, List

import openai
from PyQt5.QtCore import QRunnable, pyqtSlot
from PyQt5.QtCore import QThread, pyqtSignal
from openai import OpenAI, APIError, APIConnectionError, RateLimitError, BadRequestError, APITimeoutError


class TitleGenerationTask(QRunnable):
    def __init__(self, current_title: str, messages_for_summary: list, llm_config: dict, callback):
        super().__init__()
        self.current_title = current_title
        self.messages_for_summary = messages_for_summary
        self.llm_config = llm_config
        self.callback = callback  # 用于线程安全地回传结果到主线程（通过信号或直接调用）
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self):
        try:
            # 构造 prompt（复用你的逻辑）
            summary_text = ""
            for msg in self.messages_for_summary[-4:]:
                content = msg["content"]
                if isinstance(content, list):
                    texts = [item["text"] for item in content if item["type"] == "text"]
                    content = "\n".join(texts)
                role = "用户" if msg["role"] == "user" else "助手"
                summary_text += f"{role}：{content}\n"

            prompt = (
                "你是一个对话标题生成器。请根据以下对话内容，生成一个不超过20个字的中文标题.\n"
                f"对话内容：\n{summary_text}\n\n"
                f"概括整个对话的核心主题。当前已有对话标题为：{self.current_title}\n\n"
                "请严格按以下格式输出，不要包含任何其他文字、解释或标点：\n\n"
                "```title\n你的标题\n```\n\n"
                "标题内容为：\n"
            )

            # 调用 OpenAI API（同步调用，因为在线程中）
            client = openai.OpenAI(
                api_key=self.llm_config["API_KEY"],
                base_url=self.llm_config["API_URL"]
            )
            resp = client.chat.completions.create(
                model=self.llm_config["模型名称"],
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
                stream=False
            )
            raw_title = resp.choices[0].message.content.strip()
            # 安全回传（QRunnable 不能直接 emit 信号，但可调用主线程的槽，前提是用 QObject）
            self.callback(raw_title)
        except Exception as e:
            error_msg = f"[TitleGen Error] {str(e)}"
            self.callback(None, error=error_msg)


class OpenAIChatWorker(QThread):
    content_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished_with_content = pyqtSignal(str)

    def __init__(self, messages: List[Dict], llm_config: Dict, stream: bool = True):
        super().__init__()
        self.messages = messages
        self.llm_config = llm_config
        self.full_response = ""
        self._is_cancelled = False
        self.stream = stream

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
                "stream": self.stream,
            }

            # 仅对支持 thinking 的官方 API 才加 extra_body（避免第三方报错）
            # 这里保守处理：只在 base_url 为 None 或 openai 官方域名时启用
            if enable_thinking and (not base_url or "openai" in (base_url or "")):
                req_kwargs["extra_body"] = {
                    "enable_thinking": True,
                    "chat_template_kwargs": {"enable_thinking": True}
                }

            # 执行请求
            response = client.chat.completions.create(**req_kwargs)

            self.full_response = ""
            last_chunk_time = time.time()

            for chunk in response:
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
