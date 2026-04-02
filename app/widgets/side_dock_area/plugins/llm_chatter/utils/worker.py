# -*- coding: utf-8 -*-
import json
import re
import time
import traceback
from typing import Dict, List
from loguru import logger

from PyQt5.QtCore import QRunnable, pyqtSlot, QThread, pyqtSignal, QCoreApplication
from PyQt5.QtWidgets import QApplication
from openai import (
    OpenAI,
)


class TopicSummaryTask(QRunnable):
    """异步生成话题摘要任务 - 支持增量摘要和长期记忆判断"""

    def __init__(
        self,
        messages: list,
        llm_config: dict,
        callback,
        previous_summary: str = None,
        long_term_memory: str = "",
        existing_memories: list = None,
    ):
        super().__init__()
        self.messages = messages
        self.llm_config = llm_config
        self.callback = callback
        self.previous_summary = previous_summary
        self.long_term_memory = long_term_memory
        self.existing_memories = existing_memories or []
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
            user_only_msgs = [msg for msg in recent_msgs if msg.get("role") == "user"]
            if not user_only_msgs:
                self.callback(
                    {
                        "topic_summary": "",
                        "should_update_memory": False,
                        "memory_content": "",
                    }
                )
                return
            for msg in user_only_msgs:
                content = msg.get("content", "")
                if isinstance(content, list):
                    texts = [
                        item.get("text", "")
                        for item in content
                        if item.get("type") == "text"
                    ]
                    content = "\n".join(texts)

                content = self._extract_content_without_think(content)

                summary_text += f"用户：{content[:500]}\n"

            memory_context = ""
            if self.long_term_memory:
                memory_context = f"\n\n## 用户偏好和长期记忆\n{self.long_term_memory}\n"

            existing_memories_text = ""
            if self.existing_memories:
                mem_lines = []
                for mem in self.existing_memories:
                    if isinstance(mem, dict):
                        content = mem.get("content", "")
                        enabled = mem.get("enabled", True)
                        if enabled:
                            mem_lines.append(f"- {content}")
                    elif isinstance(mem, str) and mem:
                        mem_lines.append(f"- {mem}")
                if mem_lines:
                    existing_memories_text = (
                        "\n【已有记忆】（请勿生成重复或相似内容）:\n"
                        + "\n".join(mem_lines)
                    )

            if self.previous_summary:
                prompt = (
                    "你是一个对话标题生成助手。\n"
                    "请为用户对话生成一个简短标题。\n\n"
                    "【标题要求】\n"
                    '- 格式像标题，如："生成一个关于xxx的ppt"、"调试某个bug"、"咨询法律问题"\n'
                    "- 体现用户意图，不要描述过程\n"
                    "- 不超过20字\n\n"
                    f"{existing_memories_text}\n\n"
                    "【长期记忆】判断是否需要更新：\n"
                    f"{memory_context}\n\n"
                    f"之前的标题：{self.previous_summary}\n\n"
                    f"最新对话内容：\n{summary_text}\n\n"
                    "请严格按以下JSON格式输出，不要有其他内容：\n"
                    "```json\n"
                    "{\n"
                    '  "topic_summary": "生成的标题（如：生成一个关于xxx的ppt）",\n'
                    '  "should_update_memory": true/false,\n'
                    '  "memory_content": "用户偏好或特定需求（必须与已有记忆不同）"\n'
                    "}\n"
                    "```"
                )
            else:
                prompt = (
                    "你是一个对话标题生成助手。\n"
                    "请为用户对话生成一个简短标题。\n\n"
                    "【标题要求】\n"
                    '- 格式像标题，如："生成一个关于xxx的ppt"、"调试某个bug"、"咨询法律问题"\n'
                    "- 体现用户意图，不要描述过程\n"
                    "- 不超过20字\n\n"
                    f"{existing_memories_text}\n\n"
                    "【长期记忆】判断是否需要更新：\n"
                    f"{memory_context}\n\n"
                    f"对话内容：\n{summary_text}\n\n"
                    "请严格按以下JSON格式输出，不要有其他内容：\n"
                    "```json\n"
                    "{\n"
                    '  "topic_summary": "生成的标题（如：生成一个关于xxx的ppt）",\n'
                    '  "should_update_memory": true/false,\n'
                    '  "memory_content": "用户偏好或特定需求（必须与已有记忆不同）"\n'
                    "}\n"
                    "```"
                )

            client = OpenAI(
                api_key=self.llm_config.get("API_KEY", ""),
                base_url=self.llm_config.get("API_URL"),
            )

            from .retry_helper import create_api_call_with_retry

            def create_task():
                return client.chat.completions.create(
                    model=self.llm_config.get("模型名称", "gpt-4o"),
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=1000,
                )

            resp = create_api_call_with_retry(client, create_task)
            raw_response = resp.choices[0].message.content.strip()
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

            from .retry_helper import create_api_call_with_retry

            def create_task():
                return client.chat.completions.create(
                    model=self.llm_config.get("模型名称", "gpt-4o"),
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=100,
                )

            resp = create_api_call_with_retry(client, create_task)
            raw_title = resp.choices[0].message.content.strip()
            self.callback(raw_title)
        except Exception as e:
            self.callback(None, error=str(e))


class OpenAIChatWorker(QThread):
    content_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished_with_content = pyqtSignal(str)
    finished_with_messages = pyqtSignal(list)
    tool_call_started = pyqtSignal(str, str, dict, str)
    tool_result_received = pyqtSignal(str, str, dict, object)
    question_asked = pyqtSignal(str, str, list, bool)
    permission_approval_requested = pyqtSignal(str, str, dict)
    _DEFERRED_PREVIEW_TOOLS = {"question", "task", "todowrite", "todoread"}

    def __init__(
        self,
        messages: List[Dict],
        llm_config: Dict,
        tools: List[Dict] = None,
        stream: bool = True,
        tool_executor=None,
        tool_start_callback=None,
        get_stage_prompt=None,
        stage_changed_callback=None,
        permission_check_callback=None,
    ):
        super().__init__()
        self.messages = messages
        self.llm_config = llm_config
        self.tools = tools or []
        self.stream = stream
        self.tool_executor = tool_executor
        self.tool_start_callback = tool_start_callback
        self.get_stage_prompt = get_stage_prompt
        self.stage_changed_callback = stage_changed_callback
        self.permission_check_callback = permission_check_callback
        self.full_response = ""
        self._is_cancelled = False
        self._question_pending = None
        self._pending_answer = None
        self._permission_pending = None
        self._permission_approved = False
        self._previewed_tool_call_ids = set()

    def cancel(self):
        self._is_cancelled = True
        if self._question_pending:
            self._question_pending = None
        if self._permission_pending:
            self._permission_pending = None

    def provide_answer(self, answer: str):
        self._pending_answer = answer

    def approve_permission(self, tool_call_id: str):
        if (
            self._permission_pending
            and self._permission_pending.get("tool_call_id") == tool_call_id
        ):
            self._permission_approved = True
            self._permission_pending = None

    def deny_permission(self, tool_call_id: str):
        if (
            self._permission_pending
            and self._permission_pending.get("tool_call_id") == tool_call_id
        ):
            self._permission_approved = False
            self._permission_pending = None

    def run(self):
        try:
            iteration = 0
            max_iterations = 10
            current_messages = self.messages.copy()

            while iteration < max_iterations:
                if self._is_cancelled:
                    return

                iteration += 1
                tool_results = self._make_api_call(current_messages)

                if self._is_cancelled:
                    return

                if tool_results == "FINISH":
                    self.finished_with_content.emit(self.full_response)
                    self.finished_with_messages.emit(current_messages)
                    return

                if tool_results is None:
                    while self._pending_answer is None and not self._is_cancelled:
                        QApplication.processEvents()
                        time.sleep(0.1)

                    if self._is_cancelled:
                        return

                    q = self._question_pending
                    current_messages.append(
                        {
                            "role": "assistant",
                            "content": self.full_response,
                            "tool_calls": self._current_tool_calls,
                        }
                    )
                    current_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": q["tool_call_id"],
                            "content": self._pending_answer,
                        }
                    )
                    self._question_pending = None
                    self._pending_answer = None
                    continue

                current_messages.append(
                    {
                        "role": "assistant",
                        "content": self.full_response,
                        "tool_calls": self._current_tool_calls,
                    }
                )
                if isinstance(tool_results, list):
                    current_messages.extend(tool_results)

                self._check_and_notify_stage_change()

                QCoreApplication.processEvents()
                time.sleep(0.2)

            self.finished_with_content.emit(self.full_response)
            self.finished_with_messages.emit(current_messages)

        except Exception as e:
            logger.exception("请求失败!")
            self._handle_error(e)

    def _make_api_call(self, messages: List[Dict]):
        api_key = self.llm_config.get("API_KEY", "").strip()
        base_url = self.llm_config.get("API_URL") or None
        model = str(self.llm_config.get("模型名称", "gpt-4o"))

        req_kwargs = {
            "model": model,
            "messages": messages,
            "stream": self.stream,
        }

        extra_body = {}
        mapping = {
            "温度": "temperature",
            "最大Token": "max_tokens",
            "核采样": "top_p",
            "频率惩罚": "presence_penalty",
            "重复惩罚": "frequency_penalty",
            "思考等级": "reasoning_effort",
        }

        for cn_key, value in self.llm_config.items():
            if cn_key in ["API_KEY", "API_URL", "模型名称", "系统提示"]:
                continue

            if cn_key == "是否思考":
                status = (
                    "enabled"
                    if (value is True or str(value).lower() == "true")
                    else "disabled"
                )
                extra_body["enable_thinking"] = status == "enabled"
                extra_body["include_reasoning"] = status == "enabled"

            en_key = mapping.get(cn_key)
            if not en_key and re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", cn_key):
                en_key = cn_key
            if not en_key:
                continue
            elif en_key in ["temperature", "top_p"] and (
                model.startswith("o1") or model.startswith("o3")
            ):
                continue
            elif en_key in [
                "temperature",
                "max_tokens",
                "top_p",
                "presence_penalty",
                "frequency_penalty",
                "reasoning_effort",
            ]:
                req_kwargs[en_key] = value
            else:
                extra_body[en_key] = value

        if extra_body:
            req_kwargs["extra_body"] = extra_body

        if self.tools:
            req_kwargs["tools"] = self.tools

        auth_type = self.llm_config.get("认证方式", "bearer")
        if auth_type == "bce":
            import base64

            auth_str = f"{api_key}:{api_key}"
            b64_auth = base64.b64encode(auth_str.encode()).decode()
            req_kwargs["extra_headers"] = {"Authorization": f"Basic {b64_auth}"}

        client = OpenAI(
            api_key=api_key if api_key and auth_type != "none" else "dummy",
            base_url=base_url,
            timeout=120.0,
        )

        if "o1-preview" in model or "o1-mini" in model:
            req_kwargs.pop("stream", None)
            self.stream = False

        max_retries = 3
        retry_delay = 5
        last_error = None

        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(**req_kwargs)
                break
            except Exception as e:
                last_error = e
                from openai import RateLimitError, APIError

                is_rate_limit = isinstance(e, RateLimitError)
                is_server_overload = isinstance(e, APIError) and "2064" in str(e)

                if (is_rate_limit or is_server_overload) and attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    logger.warning(
                        f"[API] {'RateLimit' if is_rate_limit else 'ServerOverload'} error, "
                        f"retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait_time)
                    continue
                raise

        tool_calls_found = self._process_response(response)

        if not tool_calls_found:
            return "FINISH"

        tool_results = self._execute_all_tools()

        if tool_results is None:
            return None

        if tool_results:
            messages.append(
                {
                    "role": "assistant",
                    "content": self.full_response,
                    "tool_calls": self._current_tool_calls,
                }
            )
            messages.extend(tool_results)
            return self._make_api_call(messages)

        return "FINISH"

    def _process_response(self, response):
        self.full_response = ""
        self._current_tool_calls = []
        self._tool_calls_buffer = {}
        tool_calls_found = False

        for chunk in response:
            if self._is_cancelled:
                return False

            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)

            tool_calls = getattr(delta, "tool_calls", None)
            if tool_calls:
                tool_calls_found = True
                for tc in tool_calls:
                    tc_id = tc.id
                    if tc_id is None:
                        if self._tool_calls_buffer:
                            tc_id = list(self._tool_calls_buffer.keys())[-1]
                        else:
                            continue

                    if tc_id not in self._tool_calls_buffer:
                        self._tool_calls_buffer[tc_id] = {
                            "id": tc_id,
                            "type": getattr(tc, "type", "function"),
                            "function": {"name": "", "arguments": ""},
                        }

                    buffer = self._tool_calls_buffer[tc_id]
                    if tc.function and tc.function.name:
                        buffer["function"]["name"] = tc.function.name
                        tool_name = buffer["function"]["name"]
                        if (
                            tool_name
                            and tool_name not in self._DEFERRED_PREVIEW_TOOLS
                            and tc_id not in self._previewed_tool_call_ids
                        ):
                            self._previewed_tool_call_ids.add(tc_id)
                            if self.tool_start_callback:
                                self.tool_start_callback(
                                    tc_id, tool_name, {}, "preview"
                                )
                            else:
                                self.tool_call_started.emit(
                                    tc_id, tool_name, {}, "preview"
                                )
                    if tc.function and tc.function.arguments:
                        buffer["function"]["arguments"] += tc.function.arguments

                    if buffer["function"]["name"] and buffer["function"]["arguments"]:
                        try:
                            parsed_args = json.loads(buffer["function"]["arguments"])
                            self._current_tool_calls.append(
                                {
                                    "id": buffer["id"],
                                    "type": buffer["type"],
                                    "function": {
                                        "name": buffer["function"]["name"],
                                        "arguments": buffer["function"]["arguments"],
                                    },
                                }
                            )
                            del self._tool_calls_buffer[tc_id]
                        except json.JSONDecodeError:
                            pass

            if content:
                self.full_response += content
                self.content_received.emit(content)

        for tc_id, buffer in self._tool_calls_buffer.items():
            if buffer["function"]["name"] and buffer["function"]["arguments"]:
                try:
                    parsed_args = json.loads(buffer["function"]["arguments"])
                    self._current_tool_calls.append(
                        {
                            "id": buffer["id"],
                            "type": buffer["type"],
                            "function": {
                                "name": buffer["function"]["name"],
                                "arguments": buffer["function"]["arguments"],
                            },
                        }
                    )
                except json.JSONDecodeError:
                    pass

        return tool_calls_found

    def _execute_all_tools(self):
        if not self._current_tool_calls or not self.tool_executor:
            return []

        results = []
        for tc in self._current_tool_calls:
            tool_name = tc["function"]["name"]
            arguments = tc["function"]["arguments"]

            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except:
                    arguments = {}

            tool_call_id = tc["id"]

            round_id = f"round_{id(tc)}"
            if self.tool_start_callback:
                self.tool_start_callback(tool_call_id, tool_name, arguments, round_id)
            else:
                self.tool_call_started.emit(
                    tool_call_id, tool_name, arguments, round_id
                )
                QApplication.processEvents()

            if tool_name == "question":
                question_text = arguments.get("question", "")
                options = arguments.get("options", [])
                multiple = arguments.get("multiple", False)
                self.question_asked.emit(tool_call_id, question_text, options, multiple)
                self._question_pending = {
                    "tool_call_id": tool_call_id,
                    "question": question_text,
                    "options": options,
                    "multiple": multiple,
                }
                return None

            if self.permission_check_callback:
                permission_result = self.permission_check_callback(tool_name, arguments)
                if permission_result == "ask":
                    self.permission_approval_requested.emit(
                        tool_call_id, tool_name, arguments
                    )
                    self._permission_pending = {
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "arguments": arguments,
                    }
                    self._permission_approved = False
                    while (
                        self._permission_pending is not None and not self._is_cancelled
                    ):
                        QApplication.processEvents()
                        time.sleep(0.1)

                    if self._is_cancelled:
                        return None

                    if not self._permission_approved:
                        self.tool_result_received.emit(
                            tool_call_id,
                            tool_name,
                            arguments,
                            type(
                                "ToolResult",
                                (),
                                {
                                    "success": False,
                                    "error": "Permission denied by user",
                                },
                            )(),
                        )
                        QApplication.processEvents()
                        results.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": "Error: Permission denied by user",
                                "round_id": round_id,
                            }
                        )
                        continue

            result = self.tool_executor.execute(tool_name, arguments)
            result_content = str(result) if result else ""

            self.tool_result_received.emit(tool_call_id, tool_name, arguments, result)
            QApplication.processEvents()
            results.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_content,
                    "round_id": round_id,
                }
            )

        return results

    def _check_and_notify_stage_change(self):
        if not self.stage_changed_callback:
            return

        import re

        pattern = re.compile(r"\[STAGE:\s*(\w+)\]", re.IGNORECASE)
        matches = pattern.findall(self.full_response)

        if matches:
            new_stage = matches[-1].lower()
            self.stage_changed_callback(new_stage)

    def _handle_error(self, error):
        from openai import (
            BadRequestError,
            RateLimitError,
            APIConnectionError,
            APITimeoutError,
            APIError,
        )

        error_msg = str(error)
        if isinstance(error, BadRequestError):
            if "json" in error_msg.lower() or "format" in error_msg.lower():
                self.error_occurred.emit(
                    f"[JSON格式错误] 请确保输入有效的JSON格式: {error_msg}"
                )
            else:
                self.error_occurred.emit(f"[请求错误] {error_msg}")
        elif isinstance(error, RateLimitError):
            self.error_occurred.emit(
                f"[速率限制] 请求过于频繁，请稍后再试。详情: {error_msg}"
            )
        elif isinstance(error, APIConnectionError):
            self.error_occurred.emit(
                f"[连接失败] 无法连接到 API 服务器，请检查网络或 API_URL 设置。详情: {error_msg}"
            )
        elif isinstance(error, APITimeoutError):
            self.error_occurred.emit(
                f"[超时] 请求超时（120秒），请检查网络或模型负载。详情: {error_msg}"
            )
        elif isinstance(error, APIError):
            if "context length" in error_msg and "overflow" in error_msg:
                self.error_occurred.emit(
                    f"[上下文超限] 输入内容过长，请缩短对话或清除历史记录。详情: {error_msg}"
                )
            elif "insufficient_quota" in error_msg:
                self.error_occurred.emit(
                    f"[配额不足] API配额已用完，请检查账户余额或更换API Key。"
                )
            else:
                self.error_occurred.emit(f"[API错误] {error_msg}")
        elif "unrecognized_parameter" in error_msg or "extra_parameters" in error_msg:
            self.error_occurred.emit(
                f"[兼容性提示] 当前模型可能不支持某些高级设置（如思考模式或温度）。错误: {error_msg}"
            )
        elif "max_tokens" in error_msg.lower() or "context length" in error_msg.lower():
            self.error_occurred.emit(
                f"[错误] 模型上下文或最大Token超出限制，请减少输入长度或调低 max_tokens"
            )
        elif "authentication" in error_msg.lower() or "api key" in error_msg.lower():
            self.error_occurred.emit(f"[认证错误] API Key无效或已过期，请检查配置。")
        else:
            self.error_occurred.emit(f"[未知错误] {error_msg}")


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
                    encoding="utf-8",
                    errors="ignore",
                    timeout=120,
                )
            else:
                res = subprocess.run(
                    self.command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
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
