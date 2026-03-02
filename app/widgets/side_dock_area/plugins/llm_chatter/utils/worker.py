# -*- coding: utf-8 -*-
import time
import re
import json
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
from loguru import logger


class TopicSummaryTask(QRunnable):
    """异步生成话题摘要任务 - 支持增量摘要和长期记忆判断"""

    def __init__(
        self,
        messages: list,
        llm_config: dict,
        callback,
        previous_summary: str = None,
        long_term_memory: str = "",
    ):
        super().__init__()
        self.messages = messages
        self.llm_config = llm_config
        self.callback = callback
        self.previous_summary = previous_summary
        self.long_term_memory = long_term_memory
        self.setAutoDelete(True)

    def _extract_content_without_think(self, content: str) -> str:
        import re

        think_pattern = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)
        content = think_pattern.sub("", content)
        return content.strip()

    @pyqtSlot()
    def run(self):
        try:
            summary_text = ""
            recent_msgs = (
                self.messages[-6:] if len(self.messages) > 6 else self.messages
            )
            for msg in recent_msgs:
                content = msg.get("content", "")
                if isinstance(content, list):
                    texts = [
                        item.get("text", "")
                        for item in content
                        if item.get("type") == "text"
                    ]
                    content = "\n".join(texts)

                content = self._extract_content_without_think(content)

                role = "用户" if msg.get("role") == "user" else "助手"
                summary_text += f"{role}：{content[:500]}\n"

            memory_context = ""
            if self.long_term_memory:
                memory_context = f"\n\n## 用户偏好和长期记忆\n{self.long_term_memory}\n"

            if self.previous_summary:
                prompt = (
                    "你是一个专业的对话主题分析助手，专门负责从对话中提取用户的偏好、特定需求和用户导向型内容。\n"
                    "你的任务是根据以下对话内容，判断是否需要更新用户的长期记忆。\n\n"
                    "【重要】长期记忆应该记录：\n"
                    "1. 用户的偏好（如：喜欢简洁的回复、喜欢详细解释、使用中文等）\n"
                    "2. 用户的特定需求（如：需要代码示例、需要学术风格、需要创意写作等）\n"
                    "3. 用户导向型内容（如：用户的工作领域、使用的技术栈、关注的问题等）\n"
                    "4. 重要的事实和信息（如：用户的项目名称、使用的框架等）\n\n"
                    "【不应当记录的】：\n"
                    "- 普通的闲聊内容\n"
                    "- 临时性的问题\n"
                    "- 通用技术知识\n\n"
                    f"之前的主题摘要：{self.previous_summary}\n\n"
                    f"最新对话内容：\n{summary_text}\n"
                    f"{memory_context}\n\n"
                    "请严格按以下JSON格式输出，不要有其他内容：\n"
                    "```json\n"
                    "{\n"
                    '  "topic_summary": "简短主题摘要（不超过50字）",\n'
                    '  "should_update_memory": true/false,  // 判断是否值得记录到用户偏好记忆\n'
                    '  "memory_content": "如果should_update_memory为true，提取用户偏好或特定需求（不超过100字）"\n'
                    "}\n"
                    "```"
                )
            else:
                prompt = (
                    "你是一个专业的对话主题分析助手，专门负责从对话中提取用户的偏好、特定需求和用户导向型内容。\n"
                    "你的任务是根据以下对话内容，判断是否需要更新用户的长期记忆。\n\n"
                    "【重要】长期记忆应该记录：\n"
                    "1. 用户的偏好（如：喜欢简洁的回复、喜欢详细解释、使用中文等）\n"
                    "2. 用户的特定需求（如：需要代码示例、需要学术风格、需要创意写作等）\n"
                    "3. 用户导向型内容（如：用户的工作领域、使用的技术栈、关注的问题等）\n"
                    "4. 重要的事实和信息（如：用户的项目名称、使用的框架等）\n\n"
                    "【不应当记录的】：\n"
                    "- 普通的闲聊内容\n"
                    "- 临时性的问题\n"
                    "- 通用技术知识\n\n"
                    f"对话内容：\n{summary_text}\n"
                    f"{memory_context}\n\n"
                    "请严格按以下JSON格式输出，不要有其他内容：\n"
                    "```json\n"
                    "{\n"
                    '  "topic_summary": "简短主题摘要（不超过50字）",\n'
                    '  "should_update_memory": true/false,  // 判断是否值得记录到用户偏好记忆\n'
                    '  "memory_content": "如果should_update_memory为true，提取用户偏好或特定需求（不超过100字）"\n'
                    "}\n"
                    "```"
                )

            client = OpenAI(
                api_key=self.llm_config.get("API_KEY", ""),
                base_url=self.llm_config.get("API_URL"),
            )
            resp = client.chat.completions.create(
                model=self.llm_config.get("模型名称", "gpt-4o"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1000,
            )
            raw_response = resp.choices[0].message.content.strip()

            import json
            import re

            json_match = re.search(r"\{[^{}]*\}", raw_response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                callback_data = {
                    "topic_summary": result.get("topic_summary", ""),
                    "should_update_memory": result.get("should_update_memory", False),
                    "memory_content": result.get("memory_content", ""),
                }
                self.callback(callback_data)
            else:
                self.callback(
                    {
                        "topic_summary": raw_response,
                        "should_update_memory": False,
                        "memory_content": "",
                    }
                )
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
    tool_call_received = pyqtSignal(dict)
    tool_calls_finished = pyqtSignal(list)

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
        self._tool_calls_buffer = {}
        self._max_tool_iterations = 10

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

            # 添加工具定义
            if self.tools:
                logger.info(
                    f"[Worker] Adding {len(self.tools)} tools to request, model={model}"
                )
                # 检查工具定义
                for i, tool in enumerate(self.tools):
                    func = tool.get("function", {})
                    logger.info(
                        f"[Worker] Tool {i}: name={func.get('name')}, has_params={bool(func.get('parameters'))}"
                    )
                    if not func.get("name"):
                        logger.error(f"[Worker] Tool {i} has empty name!")
                    if not func.get("parameters"):
                        logger.error(f"[Worker] Tool {i} has empty parameters!")

                # 打印第一个工具的完整定义用于调试
                import json

                first_tool = self.tools[0]
                logger.info(
                    f"[Worker] First tool: {json.dumps(first_tool, ensure_ascii=False)}"
                )

                # 尝试不传工具，看看是否正常工作
                # 如果你看到这行日志但请求仍然失败，说明问题不在工具
                logger.info(f"[Worker] Proceeding with tools in request...")
                req_kwargs["tools"] = self.tools

            # 处理不同的认证方式
            auth_type = self.llm_config.get("认证方式", "bearer")

            if auth_type == "bce":
                # 百度BCE认证方式
                import base64

                auth_str = f"{api_key}:{api_key}"
                b64_auth = base64.b64encode(auth_str.encode()).decode()
                req_kwargs["extra_headers"] = {"Authorization": f"Basic {b64_auth}"}
            elif auth_type == "none":
                # 无认证（如Ollama本地）
                pass
            else:
                pass
            # 5. 执行请求
            client = OpenAI(
                api_key=api_key if api_key and auth_type != "none" else "dummy",
                base_url=base_url,
                timeout=120.0,
            )

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

                # 处理工具调用
                tool_calls = getattr(delta, "tool_calls", None)
                if tool_calls:
                    for tc in tool_calls:
                        tc_id = tc.id

                        # 如果 tc_id 为 None，使用最后一个有效的 tc_id
                        if tc_id is None:
                            if self._tool_calls_buffer:
                                tc_id = list(self._tool_calls_buffer.keys())[-1]
                            else:
                                continue

                        if tc_id not in self._tool_calls_buffer:
                            self._tool_calls_buffer[tc_id] = {
                                "id": tc_id,
                                "type": getattr(tc, "type", "function"),
                                "function": {
                                    "name": "",
                                    "arguments": "",
                                },
                            }

                        buffer = self._tool_calls_buffer[tc_id]

                        if tc.function and tc.function.name:
                            buffer["function"]["name"] = tc.function.name

                        if tc.function and tc.function.arguments:
                            buffer["function"]["arguments"] += tc.function.arguments

                        if (
                            buffer["function"]["name"]
                            and buffer["function"]["arguments"]
                        ):
                            try:
                                parsed_args = json.loads(
                                    buffer["function"]["arguments"]
                                )
                                tc_dict = {
                                    "id": buffer["id"],
                                    "type": buffer["type"],
                                    "function": {
                                        "name": buffer["function"]["name"],
                                        "arguments": parsed_args,
                                    },
                                }
                                self.tool_call_received.emit(tc_dict)
                                del self._tool_calls_buffer[tc_id]
                            except json.JSONDecodeError:
                                pass

                if content:
                    self.full_response += content
                    self.content_received.emit(content)
                    last_chunk_time = time.time()

            # 处理剩余的buffered tool calls
            for tc_id, buffer in self._tool_calls_buffer.items():
                if buffer["function"]["name"] and buffer["function"]["arguments"]:
                    try:
                        parsed_args = json.loads(buffer["function"]["arguments"])
                        tc_dict = {
                            "id": buffer["id"],
                            "type": buffer["type"],
                            "function": {
                                "name": buffer["function"]["name"],
                                "arguments": parsed_args,
                            },
                        }
                        self.tool_call_received.emit(tc_dict)
                    except json.JSONDecodeError:
                        logger.warning(
                            f"[Worker] Failed to parse tool call arguments: {buffer['function']['arguments']}"
                        )

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


class ShellExecutionTask(QRunnable):
    """异步执行Shell命令任务"""

    def __init__(self, command: str, callback):
        super().__init__()
        self.command = command
        self.callback = callback
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self):
        import subprocess
        import platform

        try:
            system = platform.system()
            if system == "Windows":
                res = subprocess.run(
                    self.command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            else:
                res = subprocess.run(
                    self.command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            output = res.stdout.strip() if res.stdout else ""
            error_out = res.stderr.strip() if res.stderr else ""
            combined = "\n".join(filter(None, [output, error_out]))
            result_text = combined if combined else "(命令执行完成，无输出)"
        except subprocess.TimeoutExpired:
            result_text = "[错误] 命令执行超时"
        except Exception as e:
            result_text = f"[错误] {str(e)}"

        self.callback(result_text)
