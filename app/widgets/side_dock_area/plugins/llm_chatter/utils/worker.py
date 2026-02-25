# -*- coding: utf-8 -*-
import time
import re
from typing import Dict, List, Any, Optional
import openai
from PyQt5.QtCore import QRunnable, pyqtSlot, QThread, pyqtSignal
from openai import (
    OpenAI,
    APIError,
    APIConnectionError,
    RateLimitError,
    BadRequestError,
    APITimeoutError,
)


class TopicSummaryTask(QRunnable):
    """异步生成话题摘要任务"""

    def __init__(self, messages: list, llm_config: dict, callback):
        super().__init__()
        self.messages = messages
        self.llm_config = llm_config
        self.callback = callback
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self):
        try:
            summary_text = ""
            for msg in self.messages[-6:]:
                content = msg.get("content", "")
                if isinstance(content, list):
                    texts = [
                        item.get("text", "")
                        for item in content
                        if item.get("type") == "text"
                    ]
                    content = "\n".join(texts)
                role = "用户" if msg.get("role") == "user" else "助手"
                summary_text += f"{role}：{content[:200]}\n"

            prompt = (
                "你是一个专业的对话主题分析助手。请仔细阅读以下对话内容，"
                "生成一个简短精炼的主题摘要（不超过50字）。\n"
                f"对话内容：\n{summary_text}\n\n"
                "请直接输出主题摘要，不要任何格式修饰。例如：\n"
                "「关于画布节点配置的问题讨论」\n"
                "「代码生成与优化建议」\n"
                "「组件库使用指导」"
            )

            client = OpenAI(
                api_key=self.llm_config.get("API_KEY", ""),
                base_url=self.llm_config.get("API_URL"),
            )
            resp = client.chat.completions.create(
                model=self.llm_config.get("模型名称", "gpt-4o"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=100,
            )
            raw_summary = resp.choices[0].message.content.strip()
            self.callback(raw_summary)
        except Exception as e:
            self.callback(None, error=str(e))


class TitleGenerationTask(QRunnable):
    """异步生成标题任务"""

    def __init__(
        self, current_title: str, messages_for_summary: list, llm_config: dict, callback
    ):
        super().__init__()
        self.current_title = current_title
        self.messages_for_summary = messages_for_summary
        self.llm_config = llm_config
        self.callback = callback
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self):
        try:
            summary_text = ""
            for msg in self.messages_for_summary[-4:]:
                content = msg["content"]
                if isinstance(content, list):
                    texts = [
                        item.get("text", "")
                        for item in content
                        if item.get("type") == "text"
                    ]
                    content = "\n".join(texts)
                role = "用户" if msg["role"] == "user" else "助手"
                summary_text += f"{role}：{content}\n"

            prompt = (
                "你是一个对话标题生成器。请根据以下对话内容，生成一个不超过20个字的中文标题.\n"
                f"对话内容：\n{summary_text}\n\n"
                "请严格按以下格式输出：\n```title\n你的标题\n```"
            )

            client = OpenAI(
                api_key=self.llm_config.get("API_KEY", ""),
                base_url=self.llm_config.get("API_URL"),
            )
            resp = client.chat.completions.create(
                model=self.llm_config.get("模型名称", "gpt-4o"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=100,
            )
            raw_title = resp.choices[0].message.content.strip()
            self.callback(raw_title)
        except Exception as e:
            self.callback(None, error=str(e))


class OpenAIChatWorker(QThread):
    content_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished_with_content = pyqtSignal(str)

    def __init__(
        self,
        messages: List[Dict],
        llm_config: Dict,
        tools: List[Dict] = None,
        stream: bool = True,
    ):
        super().__init__()
        self.messages = messages
        self.llm_config = llm_config
        self.tools = tools or []
        self.stream = stream
        self.full_response = ""
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            # 1. 基础必需参数
            api_key = self.llm_config.get("API_KEY", "").strip()
            base_url = self.llm_config.get("API_URL") or None
            model = str(self.llm_config.get("模型名称", "gpt-4o"))

            # 2. 准备参数桶
            # 顶层参数：极其严格，只放最稳妥的
            req_kwargs = {
                "model": model,
                "messages": self.messages,
                "stream": self.stream,
            }

            # 额外参数桶：比较宽松，大部分平台会忽略不认识的
            extra_body = {}
            # 3. 映射表：将中文配置映射为 API 英文键名
            mapping = {
                "温度": "temperature",
                "最大Token": "max_tokens",
                "核采样": "top_p",
                "频率惩罚": "presence_penalty",
                "重复惩罚": "frequency_penalty",
                "思考等级": "reasoning_effort",
            }

            # 4. 【一股脑逻辑】遍历所有配置
            for cn_key, value in self.llm_config.items():
                if cn_key in ["API_KEY", "API_URL", "模型名称", "系统提示"]:
                    continue

                # --- 核心处理：根据参数类型决定放哪 ---

                # A. 思考模式的特殊结构处理（自动适配 Claude 和普通模型）
                if cn_key == "是否思考":
                    status = (
                        "enabled"
                        if (value is True or str(value).lower() == "true")
                        else "disabled"
                    )
                    # 针对 Claude：放在顶层，但如果报错我们会捕获
                    # 针对其他模型：在 extra_body 传一份布尔值
                    extra_body["enable_thinking"] = status == "enabled"
                    extra_body["include_reasoning"] = status == "enabled"

                # B. 温度和 Top_P 的特殊性
                # 获取对应的英文 Key（如果没映射，且本来就是英文，则直接用）
                en_key = mapping.get(cn_key)
                if not en_key and re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", cn_key):
                    en_key = cn_key
                if not en_key:
                    continue
                # 很多推理模型 (o1, R1) 传温度会报错，所以我们优先放 extra_body，或者只在非 o1 模型放顶层
                elif en_key in ["temperature", "top_p"] and (
                    model.startswith("o1") or model.startswith("o3")
                ):
                    continue  # o1 模型坚决不传温度

                # C. 其他所有参数一律尝试放进 req_kwargs
                # 如果这个参数属于 OpenAI 的标准顶层参数，放这里
                elif en_key in [
                    "temperature",
                    "max_tokens",
                    "top_p",
                    "presence_penalty",
                    "frequency_penalty",
                    "reasoning_effort",
                ]:
                    req_kwargs[en_key] = value

                # D. 其余不确定的全塞进 extra_body（这部分最安全，不认识也不报错）
                else:
                    extra_body[en_key] = value

            if extra_body:
                req_kwargs["extra_body"] = extra_body
            # 5. 执行请求
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)

            # --- 最后的“暴力”修正：处理不支持流式的模型 ---
            if "o1-preview" in model or "o1-mini" in model:
                req_kwargs.pop("stream", None)
                self.stream = False

            response = client.chat.completions.create(**req_kwargs)

            # --- 流式处理逻辑 (提取 content 和 reasoning_content) ...
            self.full_response = ""
            for chunk in response:
                if self._is_cancelled:
                    return
                delta = chunk.choices[0].delta

                # 自动兼容 DeepSeek 的推理内容
                reasoning = getattr(delta, "reasoning_content", None)
                content = getattr(delta, "content", None)

                if content:
                    self.full_response += content
                    self.content_received.emit(content)
                    last_chunk_time = time.time()

            self.finished_with_content.emit(self.full_response)

        except BadRequestError as e:
            error_msg = e.message or str(e)
            if "json" in error_msg.lower() or "format" in error_msg.lower():
                self.error_occurred.emit(
                    f"[JSON格式错误] 请确保输入有效的JSON格式: {error_msg}"
                )
            else:
                self.error_occurred.emit(f"[请求错误] {error_msg}")

        except RateLimitError as e:
            self.error_occurred.emit(
                f"[速率限制] 请求过于频繁，请稍后再试。详情: {str(e)}"
            )

        except APIConnectionError as e:
            self.error_occurred.emit(
                f"[连接失败] 无法连接到 API 服务器，请检查网络或 API_URL 设置。详情: {str(e)}"
            )

        except APITimeoutError as e:
            self.error_occurred.emit(
                f"[超时] 请求超时（120秒），请检查网络或模型负载。详情: {str(e)}"
            )

        except APIError as e:
            error_str = str(e)
            if "context length" in error_str and "overflow" in error_str:
                self.error_occurred.emit(
                    f"[上下文超限] 输入内容过长，请缩短对话或清除历史记录。详情: {error_str}"
                )
            elif "insufficient_quota" in error_str:
                self.error_occurred.emit(
                    f"[配额不足] API配额已用完，请检查账户余额或更换API Key。"
                )
            else:
                self.error_occurred.emit(f"[API错误] {error_str}")

        except ValueError as e:
            self.error_occurred.emit(f"[配置错误] 参数类型无效: {str(e)}")

        except Exception as e:
            error_str = str(e)
            if "unrecognized_parameter" in error_str or "extra_parameters" in error_str:
                self.error_occurred.emit(
                    f"[兼容性提示] 当前模型可能不支持某些高级设置（如思考模式或温度）。错误: {error_str}"
                )
            elif (
                "max_tokens" in error_str.lower()
                or "context length" in error_str.lower()
            ):
                self.error_occurred.emit(
                    f"[错误] 模型上下文或最大Token超出限制，请减少输入长度或调低 max_tokens"
                )
            elif (
                "authentication" in error_str.lower() or "api key" in error_str.lower()
            ):
                self.error_occurred.emit(
                    f"[认证错误] API Key无效或已过期，请检查配置。"
                )
            else:
                self.error_occurred.emit(f"[未知错误] {error_str}")
