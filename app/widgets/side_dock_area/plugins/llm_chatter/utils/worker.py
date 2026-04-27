# -*- coding: utf-8 -*-
import json
import re
import time
import traceback
from datetime import datetime
from threading import Event
from typing import Any, Dict, List

import httpx
from loguru import logger

from PyQt5.QtCore import QRunnable, pyqtSlot, QThread, pyqtSignal, QCoreApplication
from PyQt5.QtWidgets import QApplication
from openai import (
    OpenAI,
)

from app.widgets.side_dock_area.plugins.llm_chatter.core.provider_profile import (
    get_provider_profile,
)
from app.widgets.side_dock_area.plugins.llm_chatter.core.memory_manager import (
    MEMORY_CATEGORIES,
)
from app.widgets.side_dock_area.plugins.llm_chatter.utils.message_content import (
    append_text_block,
    consolidate_messages,
    content_to_text,
    messages_to_api,
    normalize_tool_arguments,
)


def _fix_incomplete_json(raw_arguments: Any) -> str | None:
    text = str(raw_arguments or "")
    if not text.strip():
        return "{}"

    try:
        parsed = json.loads(text)
    except Exception:
        return None

    if not isinstance(parsed, dict):
        return None
    return json.dumps(parsed, ensure_ascii=False)


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
                summary_text += f"用户：{content[:500]}\n"

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

            category_list = ";".join(
                f"{k}: {v.replace('【', '').replace('】', '')}"
                for k, v in MEMORY_CATEGORIES.items()
            )

            if self.previous_summary:
                prompt = (
                    "你是一个对话标题和长期记忆辅助助手。\n"
                    "请根据用户对话生成一个简短标题，概况当前整体的会话内容。\n\n"
                    "【标题要求】\n"
                    '- 格式像标题，如："生成一个关于xxx的ppt"、"调试某个bug"、"咨询法律问题"\n'
                    "- 体现用户意图，不要描述过程，需要具有代表性、简短性，能概括用户整体的会话内容。\n"
                    "- 不超过15字\n\n"
                    "【已有的长期记忆】：\n"
                    f"{existing_memories_text}\n\n"
                    f"之前的标题：{self.previous_summary}\n\n"
                    f"最新用户对话内容：\n{summary_text}\n\n"
                    "请严格按以下JSON格式输出，不要有其他内容：\n"
                    "```json\n"
                    "{\n"
                    '  "topic_summary": "生成的具有代表性、简短的主旨标题（如：生成一个关于xxx的ppt）",\n'
                    '  "should_update_memory": true/false, \n'
                    '  "memory_content": "需要保存的长期记忆（只有should_update_memory为true时才填写）",\n'
                    f'  "memory_category": "分类key（记忆类型列表：{category_list}）",\n'
                    '  "hit_memories": ["已有记忆内容1", "已有记忆内容2"]（本轮对话中引用或验证过的已有记忆，最多3条）\n'
                    "}\n"
                    "```"
                )
            else:
                prompt = (
                    "你是一个对话标题生成助手。\n"
                    "请根据用户对话生成一个简短标题，概况当前整体的会话内容。\n\n"
                    "【标题要求】\n"
                    '- 格式像标题，如："生成一个关于xxx的ppt"、"调试某个bug"、"咨询法律问题"\n'
                    "- 体现用户意图，不要描述过程，需要具有代表性、简短性，能概括用户整体的会话内容。\n"
                    "- 不超过15字\n\n"
                    "【已有的长期记忆】：\n"
                    f"{existing_memories_text}\n\n"
                    f"对话内容：\n{summary_text}\n\n"
                    "请严格按以下JSON格式输出，不要有其他内容：\n"
                    "```json\n"
                    "{\n"
                    '  "topic_summary": "生成的具有代表性、简短的主旨标题（如：生成一个关于xxx的ppt）",\n'
                    '  "should_update_memory": true/false, \n'
                    '  "memory_content": "需要保存的长期记忆（只有should_update_memory为true时才填写）",\n'
                    f'  "memory_category": "分类key（记忆类型列表：{category_list}）",\n'
                    '  "hit_memories": ["已有记忆内容1", "已有记忆内容2"]（本轮对话中引用或验证过的已有记忆，最多3条）\n'
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
                    "memory_category": result.get("memory_category", "task_preference"),
                    "hit_memories": result.get("hit_memories", []),
                }
                self.callback(callback_data)
            else:
                self.callback(
                    {
                        "topic_summary": raw_response,
                        "should_update_memory": False,
                        "memory_content": "",
                        "memory_category": "task_preference",
                        "hit_memories": [],
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
    compaction_status_changed = pyqtSignal(dict)
    tool_call_started = pyqtSignal(str, str, dict, str)
    tool_result_received = pyqtSignal(str, str, dict, object)
    question_asked = pyqtSignal(str, str, list, bool)
    permission_approval_requested = pyqtSignal(str, str, dict)
    _DEFERRED_PREVIEW_TOOLS = {"question", "task", "todowrite", "todoread"}

    def __init__(
        self,
        messages: List[Dict],
        session_messages: List[Dict],
        llm_config: Dict,
        tools: List[Dict] = None,
        stream: bool = True,
        tool_executor=None,
        tool_start_callback=None,
        get_stage_prompt=None,
        stage_changed_callback=None,
        permission_check_callback=None,
        compaction_prompt: str = "",
        compaction_config: Dict = None,
    ):
        super().__init__()
        self.messages = messages
        self.session_messages = consolidate_messages(session_messages or [])
        self.llm_config = llm_config
        self.tools = tools or []
        self.stream = stream
        self.tool_executor = tool_executor
        self.tool_start_callback = tool_start_callback
        self.get_stage_prompt = get_stage_prompt
        self.stage_changed_callback = stage_changed_callback
        self.permission_check_callback = permission_check_callback
        self.compaction_prompt = compaction_prompt
        self.compaction_config = compaction_config or {}
        self.full_response = ""
        self._is_cancelled = False
        self._question_pending = None
        self._pending_answer = None
        self._answer_event = Event()
        self._permission_pending = None
        self._permission_approved = False
        self._round_permission_cache = {}
        self._previewed_tool_call_ids = set()
        self._current_tool_calls = []
        self._tool_calls_buffer = {}
        self._invalid_tool_calls = []
        self._response_content_blocks = []
        self._tool_execution_cancelled = False
        self._last_compaction_state = {
            "active": False,
            "source": "worker",
            "kind": "",
            "original_count": len(messages or []),
            "summarized_count": 0,
            "kept_count": len(messages or []),
            "summary_count": 0,
            "note": "",
        }
        self._current_session_messages = list(self.session_messages)

    def cancel(self):
        self._is_cancelled = True
        self._tool_execution_cancelled = True
        self._answer_event.set()
        if self._question_pending:
            self._question_pending = None
        if self._permission_pending:
            self._permission_pending = None

    def get_interrupted_messages(self) -> List[Dict]:
        snapshot = list(self._current_session_messages or self.session_messages or [])
        partial_sequence = self._build_response_message_sequence()
        if partial_sequence:
            snapshot = snapshot + partial_sequence
        return consolidate_messages(snapshot)

    def _clear_pending_response_state(self):
        self._current_tool_calls = []
        self._tool_calls_buffer = {}
        self._invalid_tool_calls = []
        self._response_content_blocks = []
        self._previewed_tool_call_ids = set()

    def _parse_tool_arguments_json(self, raw_arguments: Any):
        if isinstance(raw_arguments, dict):
            return raw_arguments, ""

        text = str(raw_arguments or "")
        if not text.strip():
            return {}, ""

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            return None, str(exc)

        if not isinstance(parsed, dict):
            return None, f"expected JSON object, got {type(parsed).__name__}"

        return parsed, ""

    def _append_valid_tool_call(self, buffer: Dict[str, Any]) -> bool:
        parsed_args, error = self._parse_tool_arguments_json(
            buffer.get("function", {}).get("arguments", "")
        )
        if parsed_args is None:
            tool_name = buffer.get("function", {}).get("name", "") or "unknown"
            tool_call_id = str(buffer.get("id") or "")
            raw_args = buffer.get("function", {}).get("arguments", "")
            self._invalid_tool_calls.append(
                {
                    "id": tool_call_id,
                    "name": tool_name,
                    "arguments": raw_args,
                    "error": error,
                }
            )
            logger.error(
                f"[ToolCall] Dropping invalid tool arguments for tool_call {tool_call_id} "
                f"({tool_name}): {error}; raw_len={len(str(raw_args or ''))}"
            )
            return False

        serialized_args = json.dumps(parsed_args, ensure_ascii=False)
        self._current_tool_calls.append(
            {
                "id": buffer["id"],
                "type": buffer["type"],
                "function": {
                    "name": buffer["function"]["name"],
                    "arguments": serialized_args,
                },
            }
        )
        return True

    def provide_answer(self, answer: str):
        self._pending_answer = answer
        self._answer_event.set()

    def approve_permission(self, tool_call_id: str, auto_allow: bool = False):
        if (
            self._permission_pending
            and self._permission_pending.get("tool_call_id") == tool_call_id
        ):
            if auto_allow:
                tool_name = self._permission_pending.get("tool_name", "")
                self._round_permission_cache[tool_name] = True
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
            current_messages = self.messages.copy()
            current_session_messages = list(self.session_messages)
            self._current_session_messages = list(current_session_messages)
            self._emit_compaction_status(self._last_compaction_state)
            compacted_messages, compaction_state = self._maybe_compact_messages(
                current_messages
            )
            self._emit_compaction_status(compaction_state)
            current_messages = compacted_messages

            self.full_response = ""

            while not self._is_cancelled:
                if self._is_cancelled:
                    return
                tool_calls_found = self._make_api_call(current_messages)

                if self._is_cancelled:
                    return

                if not tool_calls_found:
                    response_sequence = self._build_response_message_sequence()
                    current_messages.extend(response_sequence)
                    current_session_messages.extend(response_sequence)
                    self._current_session_messages = list(current_session_messages)
                    self.finished_with_messages.emit(current_session_messages)
                    self._clear_pending_response_state()
                    self.finished_with_content.emit(self.full_response)
                    return

                tool_results = self._execute_all_tools()

                if tool_results is None:
                    self._answer_event.clear()
                    while self._pending_answer is None and not self._is_cancelled:
                        if self._answer_event.wait(timeout=1.0):
                            break

                    if self._is_cancelled:
                        return

                    q = self._question_pending
                    response_sequence = self._build_response_message_sequence()
                    current_messages.extend(response_sequence)
                    current_session_messages.extend(response_sequence)
                    question_result = {
                        "role": "tool",
                        "tool_call_id": q["tool_call_id"],
                        "content": self._pending_answer,
                    }
                    current_messages.append(question_result)
                    current_session_messages.append(question_result)
                    self._current_session_messages = list(current_session_messages)
                    self.finished_with_messages.emit(current_session_messages)
                    self._clear_pending_response_state()
                    self._question_pending = None
                    self._pending_answer = None
                    self._answer_event.clear()
                    continue

                response_sequence = self._build_response_message_sequence(tool_results)
                current_messages.extend(response_sequence)
                current_session_messages.extend(response_sequence)
                self._current_session_messages = list(current_session_messages)
                self.finished_with_messages.emit(current_session_messages)
                self._clear_pending_response_state()

                self._check_and_notify_stage_change()

                QCoreApplication.processEvents()
                time.sleep(0.2)

        except Exception as e:
            logger.exception("请求失败!")
            self._handle_error(e)

    def _build_response_message_sequence(self, tool_results=None) -> List[Dict]:
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tool_call_map = {}
        for tc in self._current_tool_calls or []:
            if not isinstance(tc, dict):
                continue
            tool_call_id = str(tc.get("id") or "")
            if not tool_call_id:
                continue
            function = tc.get("function", {}) or {}
            normalized_tc = {
                "id": tool_call_id,
                "type": tc.get("type", "function"),
                "function": {
                    "name": function.get("name"),
                    "arguments": function.get("arguments", "{}"),
                },
            }
            tool_call_map[tool_call_id] = normalized_tc

        tool_result_map = {}
        for item in tool_results or []:
            if not isinstance(item, dict):
                continue
            tool_call_id = str(item.get("tool_call_id") or "")
            if not tool_call_id:
                continue
            tool_result_map[tool_call_id] = {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": item.get("name", "tool"),
                "arguments": item.get("arguments", {}),
                "content": item.get("content", ""),
                "success": item.get("success", True),
                "round_id": item.get("round_id"),
                "timestamp": item.get("timestamp", now_ts),
            }

        sequence: List[Dict] = []
        pending_text_blocks = []

        for block in self._response_content_blocks or []:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text":
                text = str(block.get("text", ""))
                if text:
                    pending_text_blocks = append_text_block(pending_text_blocks, text)
                continue

            if block_type != "tool_call_marker":
                continue

            tool_call_id = str(block.get("tool_call_id") or "")
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "timestamp": now_ts,
            }
            if pending_text_blocks:
                assistant_msg["content"] = pending_text_blocks[0].get("text")
            tool_call = tool_call_map.get(tool_call_id)
            if tool_call:
                assistant_msg["tool_calls"] = [tool_call]
            if assistant_msg.get("content") or assistant_msg.get("tool_calls"):
                sequence.append(assistant_msg)

            pending_text_blocks = []
            tool_result = tool_result_map.get(tool_call_id)
            if tool_result:
                sequence.append(tool_result)

        if pending_text_blocks:
            sequence.append(
                {
                    "role": "assistant",
                    "content": pending_text_blocks[0].get("text"),
                    "timestamp": now_ts,
                }
            )
        elif not sequence and self.full_response:
            sequence.append(
                {
                    "role": "assistant",
                    "content": append_text_block([], self.full_response)[0].get("text"),
                    "timestamp": now_ts,
                }
            )
        elif not sequence and not self._response_content_blocks:
            sequence.append({"role": "assistant", "content": [], "timestamp": now_ts})

        return sequence

    def _emit_compaction_status(self, state: Dict):
        normalized = {
            "active": bool((state or {}).get("active", False)),
            "source": (state or {}).get("source", "worker"),
            "kind": (state or {}).get("kind", ""),
            "original_count": int((state or {}).get("original_count", 0) or 0),
            "summarized_count": int((state or {}).get("summarized_count", 0) or 0),
            "kept_count": int((state or {}).get("kept_count", 0) or 0),
            "summary_count": int((state or {}).get("summary_count", 0) or 0),
            "note": str((state or {}).get("note", "") or ""),
        }
        if normalized == self._last_compaction_state:
            return
        self._last_compaction_state = normalized
        self.compaction_status_changed.emit(dict(normalized))

    def _make_api_call(self, messages: List[Dict]) -> bool:
        api_key = self.llm_config.get("API_KEY", "").strip()
        base_url = self.llm_config.get("API_URL") or None
        model = str(self.llm_config.get("模型名称", "gpt-4o"))

        sanitized = messages_to_api(messages)

        req_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": sanitized,
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

        skip_params = {
            "temperature",
            "top_p",
            "presence_penalty",
            "frequency_penalty",
            "reasoning_effort",
        }
        if model and (model.startswith("o1") or model.startswith("o3")):
            skip_params.update({"temperature", "top_p"})

        for cn_key, value in self.llm_config.items():
            if cn_key in ["API_KEY", "API_URL", "模型名称", "系统提示", "启用技能"]:
                continue

            en_key = mapping.get(cn_key)
            if not en_key and re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", cn_key):
                en_key = cn_key
            if not en_key:
                continue

            if en_key in skip_params:
                continue
            if en_key in ["max_tokens"]:
                req_kwargs[en_key] = value
            else:
                extra_body[en_key] = value

        if "max_tokens" in req_kwargs:
            req_kwargs["max_tokens"] = self._cap_max_output_tokens(
                model, req_kwargs["max_tokens"]
            )

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
            timeout=httpx.Timeout(300.0, connect=30.0),
        )

        if "o1-preview" in model or "o1-mini" in model:
            req_kwargs.pop("stream", None)
            self.stream = False

        max_retries = 15
        retry_delay = 5
        last_error = None

        # 需要重试的错误类型
        from openai import RateLimitError, APIError, APIConnectionError
        from httpx import ReadTimeout as HttpxReadTimeout
        import httpcore

        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(**req_kwargs)
                break
            except Exception as e:
                last_error = e
                error_str = str(e)
                error_type = type(e).__name__

                # 判断是否应该重试
                is_rate_limit = isinstance(e, RateLimitError)
                is_server_overload = isinstance(e, APIError) and ("2064" in error_str or "overload" in error_str.lower())
                is_read_timeout = isinstance(e, (httpcore.ReadTimeout, HttpxReadTimeout))
                is_conn_error = isinstance(e, (httpcore.ConnectError, httpcore.ConnectTimeout, APIConnectionError))

                should_retry = (
                    is_rate_limit or is_server_overload or is_read_timeout or is_conn_error
                )

                if should_retry and attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    retry_reason = "RateLimit" if is_rate_limit else ("ServerOverload" if is_server_overload else "ReadTimeout" if is_read_timeout else "ConnectionError")
                    logger.warning(
                        f"[API] {retry_reason} error, retrying in {wait_time}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait_time)
                    continue

                if hasattr(e, "response") and e.response is not None:
                    resp_body = getattr(e.response, "text", "") or ""
                    logger.error(f"[API] Error response body: {resp_body[:500]}")
                raise

        return self._process_response(response)

    def _estimate_message_tokens(self, messages: List[Dict]) -> int:
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    for value in block.values():
                        if isinstance(value, str):
                            total_chars += len(value)
            for tc in msg.get("tool_calls", []):
                if not isinstance(tc, dict):
                    continue
                for value in tc.values():
                    if isinstance(value, str):
                        total_chars += len(value)
        return int(total_chars / 3.5)

    def _infer_context_limit(self, model: str) -> int:
        profile = get_provider_profile(self.llm_config)
        return int(profile.get("context_limit", 128000))

    def _cap_max_output_tokens(self, model: str, requested: int) -> int:
        try:
            requested_int = int(requested)
        except Exception:
            return requested
        profile = get_provider_profile(self.llm_config)
        cap = int(profile.get("max_output_tokens", requested_int))
        if profile.get("family") == "openai":
            model_name = (model or "").lower()
            if "gpt-4-turbo" in model_name:
                cap = min(cap, 4096)
            elif "o1" in model_name or "o3" in model_name:
                cap = max(cap, min(requested_int, 32768))
        return min(requested_int, cap)

    def _build_compaction_messages(
        self, old_messages: List[Dict], recent_messages: List[Dict]
    ) -> List[Dict]:
        def extract_text(content: Any, max_len: int) -> str:
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                content = "\n".join(text_parts)
            return str(content)[:max_len]

        transcript_lines = []
        for msg in old_messages:
            role = msg.get("role", "unknown")
            transcript_lines.append(
                f"[{role}] {extract_text(msg.get('content', ''), 1800)}"
            )

        recent_hint = []
        for msg in recent_messages[-4:]:
            role = msg.get("role", "unknown")
            recent_hint.append(f"[{role}] {extract_text(msg.get('content', ''), 400)}")

        prompt = (
            "请压缩较早的对话上下文，生成一个后续可继续执行编码任务的摘要。\n\n"
            "要求：\n"
            "1. 保留任务目标、已做决定、相关文件、关键工具结果、未完成事项。\n"
            "2. 删除重复探索和无关寒暄。\n"
            "3. 输出简洁 Markdown，不要使用 JSON。\n"
            "4. 如果最近消息与旧消息有潜在冲突，请明确标出。\n\n"
            "【较早对话】\n"
            + "\n".join(transcript_lines)
            + "\n\n【最近保留消息提示】\n"
            + "\n".join(recent_hint)
        )

        return [
            {
                "role": "system",
                "content": self.compaction_prompt
                or "你是一个上下文压缩助手，负责提炼编码任务继续执行所需的摘要。",
            },
            {"role": "user", "content": prompt},
        ]

    def _summarize_old_messages(
        self, old_messages: List[Dict], recent_messages: List[Dict]
    ) -> str:
        api_key = self.llm_config.get("API_KEY", "").strip()
        base_url = self.llm_config.get("API_URL") or None
        model = str(
            self.compaction_config.get("model")
            or self.llm_config.get("模型名称", "gpt-4o")
        )

        client = OpenAI(
            api_key=api_key
            if api_key and self.llm_config.get("认证方式", "bearer") != "none"
            else "dummy",
            base_url=base_url,
            timeout=60.0,
        )

        req_kwargs = {
            "model": model,
            "messages": self._build_compaction_messages(old_messages, recent_messages),
            "stream": False,
            "max_tokens": self._cap_max_output_tokens(model, 1800),
            "temperature": self.compaction_config.get("temperature", 0.1),
        }
        top_p = self.compaction_config.get("top_p")
        if top_p is not None:
            req_kwargs["top_p"] = top_p

        from .retry_helper import create_api_call_with_retry

        def create_task():
            return client.chat.completions.create(**req_kwargs)

        resp = create_api_call_with_retry(client, create_task)
        return (resp.choices[0].message.content or "").strip()

    def _maybe_compact_messages(self, messages: List[Dict]) -> tuple[List[Dict], Dict]:
        inactive_state = {
            "active": False,
            "source": "worker",
            "kind": "",
            "original_count": len(messages or []),
            "summarized_count": 0,
            "kept_count": len(messages or []),
            "summary_count": 0,
            "note": "",
        }
        return messages, inactive_state

    def _process_response(self, response):
        self._response_content_blocks = []
        self._current_tool_calls = []
        self._tool_calls_buffer = {}
        self._invalid_tool_calls = []
        tool_calls_found = False

        for chunk in response:
            if self._is_cancelled:
                return False

            # 定期处理 UI 事件，让 tool_call_started 信号有机会触发弹窗显示
            QCoreApplication.processEvents()

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
                        self._response_content_blocks.append(
                            {
                                "type": "tool_call_marker",
                                "tool_call_id": tc_id,
                            }
                        )

                    buffer = self._tool_calls_buffer[tc_id]
                    # 收到 tool name 时立即触发弹窗，让用户感知到正在执行工具
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

                    # 当参数累积后，尝试解析并修复不完整的 JSON
                    if buffer["function"]["name"] and buffer["function"]["arguments"]:
                        raw_args = buffer["function"]["arguments"]
                        parsed_args, error = self._parse_tool_arguments_json(raw_args)
                        
                        # 如果解析失败，尝试修复不完整的 JSON
                        if parsed_args is None:
                            fixed_args = _fix_incomplete_json(raw_args)
                            if fixed_args:
                                try:
                                    parsed_args = json.loads(fixed_args)
                                    logger.warning(
                                        f"[ToolCall] Fixed incomplete JSON for tool_call {tc_id}: "
                                        f"original_len={len(raw_args)}, fixed_len={len(fixed_args)}"
                                    )
                                except Exception:
                                    parsed_args = None
                        
                        if parsed_args is not None:
                            self._append_valid_tool_call(buffer)
                        else:
                            # 解析/修复都失败，记录到 invalid（但仍尝试添加到 current）
                            tool_name = buffer["function"]["name"]
                            logger.error(
                                f"[ToolCall] Invalid JSON for tool_call {tc_id} ({tool_name}): {error}; "
                                f"raw_len={len(raw_args)}"
                            )
                            self._invalid_tool_calls.append({
                                "id": tc_id,
                                "name": tool_name,
                                "arguments": raw_args,
                                "error": error,
                            })
                        
                        # 无论成功失败，都从 buffer 中移除
                        self._tool_calls_buffer.pop(tc_id, None)

            if content:
                self.full_response += content
                self._response_content_blocks = append_text_block(
                    self._response_content_blocks, content
                )
                self.content_received.emit(content)

        # 二次处理剩余 buffer，也需要 JSON 修复逻辑
        for tc_id, buffer in list(self._tool_calls_buffer.items()):
            if buffer["function"]["name"] and buffer["function"]["arguments"]:
                raw_args = buffer["function"]["arguments"]
                parsed_args, error = self._parse_tool_arguments_json(raw_args)
                
                if parsed_args is None:
                    fixed_args = _fix_incomplete_json(raw_args)
                    if fixed_args:
                        try:
                            parsed_args = json.loads(fixed_args)
                            logger.warning(
                                f"[ToolCall] Fixed incomplete JSON for tool_call {tc_id}: "
                                f"original_len={len(raw_args)}, fixed_len={len(fixed_args)}"
                            )
                        except Exception:
                            parsed_args = None
                
                if parsed_args is not None:
                    self._append_valid_tool_call(buffer)
                else:
                    tool_name = buffer["function"]["name"]
                    logger.error(
                        f"[ToolCall] Invalid JSON for tool_call {tc_id} ({tool_name}): {error}"
                    )
                    self._invalid_tool_calls.append({
                        "id": tc_id,
                        "name": tool_name,
                        "arguments": raw_args,
                        "error": error,
                    })
            
            self._tool_calls_buffer.pop(tc_id, None)

        if self._invalid_tool_calls:
            invalid_count = len(self._invalid_tool_calls)
            summary = ", ".join(
                f"{item['name']}({item['id']})" for item in self._invalid_tool_calls[:3]
            )
            self.error_occurred.emit(
                f"[工具参数解析失败] 已丢弃 {invalid_count} 个无效工具调用，"
                f"避免其进入历史并触发后续 400 错误: {summary}"
            )

        return bool(self._current_tool_calls)

    def _execute_all_tools(self):
        if not self._current_tool_calls or not self.tool_executor:
            return []

        # 重置工具执行取消标志，开始新的执行周期
        self._tool_execution_cancelled = False

        results = []
        for tc in self._current_tool_calls:
            if self._is_cancelled or self._tool_execution_cancelled:
                cancelled_tc_id = tc["id"]
                tool_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except:
                    args = {}
                self.tool_result_received.emit(
                    cancelled_tc_id,
                    tool_name,
                    args,
                    type(
                        "ToolResult",
                        (),
                        {"success": False, "content": None, "error": "用户中止"},
                    )(),
                )
                QApplication.processEvents()
                self._is_cancelled = True
                return None

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
                if tool_name in self._round_permission_cache:
                    permission_result = "allow"
                else:
                    permission_result = self.permission_check_callback(
                        tool_name, arguments
                    )
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
                        self._permission_pending is not None
                        and not self._is_cancelled
                        and not self._tool_execution_cancelled
                    ):
                        QApplication.processEvents()
                        time.sleep(0.1)

                    if self._is_cancelled or self._tool_execution_cancelled:
                        cancelled_tc_id = tool_call_id
                        self.tool_result_received.emit(
                            cancelled_tc_id,
                            tool_name,
                            arguments,
                            type(
                                "ToolResult",
                                (),
                                {
                                    "success": False,
                                    "content": None,
                                    "error": "用户中止",
                                },
                            )(),
                        )
                        QApplication.processEvents()
                        self._is_cancelled = True
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

            try:
                # 设置当前调用的 call_id（用于文件操作记录）
                if hasattr(self.tool_executor, "set_call_id"):
                    self.tool_executor.set_call_id(tool_call_id)

                # 传递取消标志引用，以便异步工具可以检测取消
                cancelled_ref = [self._is_cancelled or self._tool_execution_cancelled]
                result = self.tool_executor.execute(tool_name, arguments, cancelled_ref)
                # 更新取消标志引用
                cancelled_ref[0] = self._is_cancelled or self._tool_execution_cancelled
            except Exception as e:
                logger.error(f"[Tool] Tool '{tool_name}' execution failed: {e}")
                result = None
                result_content = f"Tool execution error: {str(e)}"
                success = False
            else:
                result_content = str(result) if result else ""
                success = bool(getattr(result, "success", True)) if result else False

            if self._is_cancelled or self._tool_execution_cancelled:
                cancelled_result = type(
                    "ToolResult",
                    (),
                    {
                        "success": False,
                        "content": None,
                        "error": "用户中止",
                    },
                )()
                self.tool_result_received.emit(
                    tool_call_id, tool_name, arguments, cancelled_result
                )
                QApplication.processEvents()
                self._is_cancelled = True
                return None

            self.tool_result_received.emit(tool_call_id, tool_name, arguments, result)
            QApplication.processEvents()
            results.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": tool_name,
                    "arguments": arguments or {},
                    "content": result_content,
                    "success": success,
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

        if (
            "peer closed connection" in error_msg.lower()
            or "incomplete chunked read" in error_msg.lower()
        ):
            self.error_occurred.emit(
                f"[连接中断] 服务器在响应中途关闭了连接，可能是服务器过载或网络不稳定。请稍后重试。"
            )
            return
        if "ProtocolError" in error_msg or "RemoteProtocolError" in error_msg:
            self.error_occurred.emit(
                f"[连接错误] 网络协议错误，可能是服务器关闭了连接。请稍后重试。"
            )
            return

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
                f"[超时] 请求超时（300秒），请检查网络或模型负载。详情: {error_msg}"
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
