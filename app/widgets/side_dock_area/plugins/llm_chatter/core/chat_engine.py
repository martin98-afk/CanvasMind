# -*- coding: utf-8 -*-
"""
聊天引擎模块 - 处理 LLM 对话的核心逻辑
"""

import re
from loguru import logger
from typing import Dict, List, Optional, Any, Callable

from app.widgets.side_dock_area.plugins.llm_chatter.utils.worker import OpenAIChatWorker
from app.widgets.side_dock_area.plugins.llm_chatter.core.task_state import (
    CODING_STAGES,
    get_stage_prompt as resolve_stage_prompt,
)
from app.widgets.side_dock_area.plugins.llm_chatter.utils.builtin_tools import (
    get_builtin_tools_schema,
)
from app.widgets.side_dock_area.plugins.llm_chatter.utils.chat_session import (
    ChatSession,
    SessionManager,
)
from app.widgets.side_dock_area.plugins.llm_chatter.core.provider_profile import (
    get_provider_profile,
    supports_vision as provider_supports_vision,
)


TOKEN_ESTIMATION_RATIO = 0.25
MAX_HISTORY_SNIPPET_CHARS = 1200
RECENT_HISTORY_MIN_MESSAGES = 6


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return int(len(text) * TOKEN_ESTIMATION_RATIO) + len(re.findall(r"\w+", text))


def estimate_tokens_from_messages(messages: List[Dict]) -> int:
    total = 0
    for msg in messages:
        total += 4
        if "role" in msg:
            total += len(msg["role"])
        content = msg.get("content", "")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    total += len(item.get("text", ""))
        elif isinstance(content, str):
            total += estimate_tokens(content)
        for tool_call in msg.get("tool_calls", []):
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function", {})
            total += estimate_tokens(str(function.get("name", "")))
            total += estimate_tokens(str(function.get("arguments", "")))
        total += estimate_tokens(str(msg.get("tool_call_id", "")))
    return total


def _normalize_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                text = str(item.get("text", "")).strip()
                if text:
                    texts.append(text)
        return "\n".join(texts).strip()
    return str(content or "").strip()


class ChatEngine:
    """聊天引擎，负责组装上下文并驱动 worker。"""

    def __init__(
        self,
        session_manager: SessionManager,
        get_model_config: Callable[[], Dict[str, Any]],
        get_context_provider: Any,
        tool_executor: Optional[Any] = None,
        agent_manager: Any = None,
        get_chat_cards: Callable[[], List[Any]] = None,
        get_memory_context: Optional[Callable[[], str]] = None,
    ):
        self._session_manager = session_manager
        self._get_model_config = get_model_config
        self._get_context_provider = get_context_provider
        self._tool_executor = tool_executor
        self._agent_manager = agent_manager
        self._get_chat_cards = get_chat_cards
        self._get_memory_context = get_memory_context

        self._current_worker: Optional[OpenAIChatWorker] = None
        self._is_streaming = False
        self._callbacks: Dict[str, Callable] = {}
        self._current_agent: Optional[str] = "plan"

    def _get_agent_manager(self):
        return self._agent_manager

    def _check_tool_permission(self, tool_name: str, arguments: dict) -> str:
        agent_manager = self._get_agent_manager()
        if not agent_manager or not self._current_agent:
            return "allow"

        try:
            from app.widgets.side_dock_area.plugins.llm_chatter.core.agent import (
                PermissionResolver,
            )

            agent = agent_manager.get_agent(self._current_agent)
            if not agent:
                return "allow"

            perm_resolver = PermissionResolver(agent.permission, {}, agent.tools)

            if tool_name == "bash":
                command = arguments.get("command", "")
                return perm_resolver.resolve(tool_name, command)
            elif tool_name in ("read", "edit", "write", "patch"):
                file_path = arguments.get("filePath", "")
                return perm_resolver.resolve(tool_name, file_path)
            elif tool_name == "webfetch":
                url = arguments.get("url", "")
                return perm_resolver.resolve(tool_name, url)
            elif tool_name == "websearch":
                query = arguments.get("query", "")
                return perm_resolver.resolve(tool_name, query)
            elif tool_name == "task":
                subagent = arguments.get("agent", "")
                return perm_resolver.resolve_task(subagent)
            elif tool_name == "skill":
                skill_name = arguments.get("name", "")
                return perm_resolver.resolve(tool_name, skill_name)
            else:
                return perm_resolver.resolve(tool_name)

        except Exception as e:
            logger.warning(f"[ChatEngine] Permission check error: {e}")
            return "allow"

    def _on_permission_approval_requested(
        self, tool_call_id: str, tool_name: str, arguments: dict
    ):
        self._emit("permission_approval_requested", tool_call_id, tool_name, arguments)

    def approve_tool_permission(self, tool_call_id: str):
        if self._current_worker:
            self._current_worker.approve_permission(tool_call_id)

    def deny_tool_permission(self, tool_call_id: str):
        if self._current_worker:
            self._current_worker.deny_permission(tool_call_id)

    def _get_token_budget(self, llm_config: Dict) -> int:
        max_tokens = llm_config.get("最大Token", 4096)
        model_name = str(llm_config.get("模型名称", "")).lower()
        reserved = 800
        if "o1" in model_name or "o3" in model_name:
            reserved = 32000
        return max(500, max_tokens - reserved)

    def _smart_trim_messages(self, cards: List[Any], max_tokens: int) -> List[Any]:
        pass

    def _get_token_budget(self, llm_config: Dict) -> int:
        profile = get_provider_profile(llm_config)
        context_limit = profile.get("context_limit", 128000)
        for key in (
            "context_limit",
            "context_window",
            "max_context_tokens",
            "涓婁笅鏂囬暱搴?",
            "涓婁笅鏂囩獥鍙?",
        ):
            value = llm_config.get(key)
            if value in (None, ""):
                continue
            try:
                context_limit = int(value)
                break
            except Exception:
                continue

        max_tokens = llm_config.get("鏈€澶oken", profile.get("max_output_tokens", 4096))
        try:
            max_tokens = int(max_tokens)
        except Exception:
            max_tokens = int(profile.get("max_output_tokens", 4096))

        model_name = str(llm_config.get("妯″瀷鍚嶇О", "")).lower()
        reserved = min(800, max_tokens)
        if "o1" in model_name or "o3" in model_name:
            reserved = min(max_tokens, 32000)
        return max(500, int(context_limit) - reserved)

    def _smart_trim_messages(self, cards: List[Any], max_tokens: int) -> List[Any]:
        if not cards:
            return []
        system_tokens = 0
        for part in [
            self._session_manager.get_current_session().task_state.build_context_block(),
            self._session_manager.get_current_session().task_state.build_event_digest(),
        ]:
            system_tokens += estimate_tokens(part) if part else 0
        available_tokens = max_tokens - system_tokens - 200
        if available_tokens <= 0:
            return []
        selected = []
        total_tokens = 0
        recent_cards = list(cards[-20:])
        for i, card in enumerate(recent_cards):
            role = getattr(card, "role", None)
            if not role or role == "system":
                continue
            content = ""
            if hasattr(card, "viewer") and hasattr(card.viewer, "get_plain_text"):
                content = card.viewer.get_plain_text()
            if not content:
                continue
            card_tokens = estimate_tokens(content) + 20
            if total_tokens + card_tokens <= available_tokens:
                selected.append(card)
                total_tokens += card_tokens
            elif i < 3:
                truncated = content[: available_tokens - total_tokens * 4]
                if truncated:
                    selected.append(card)
                    break
        return selected

    def _trim_message_content(self, content: str, hard_limit: int) -> str:
        text = (content or "").strip()
        if len(text) <= hard_limit:
            return text
        head = text[: int(hard_limit * 0.65)].rstrip()
        tail = text[-int(hard_limit * 0.2) :].lstrip()
        omitted = len(text) - len(head) - len(tail)
        return (
            f"{head}\n\n[... 已省略 {omitted} 个字符的较早内容以控制上下文长度 ...]\n\n{tail}"
        )

    def _summarize_compacted_messages(self, messages: List[Dict[str, str]]) -> str:
        if not messages:
            return ""

        summary_lines = [
            "## Earlier Conversation Summary",
            "以下是为节省上下文窗口而压缩的较早对话，请把它当作已确认的历史上下文继续工作。",
        ]

        user_points = []
        assistant_points = []
        for msg in messages:
            role = msg.get("role")
            content = _normalize_message_content(msg.get("content", ""))
            if not content:
                continue
            single_line = " ".join(content.split())
            snippet = self._trim_message_content(single_line, 220)
            if role == "user":
                user_points.append(snippet)
            elif role == "assistant":
                assistant_points.append(snippet)

        if user_points:
            summary_lines.append("### User Requests")
            for idx, item in enumerate(user_points[-6:], 1):
                summary_lines.append(f"{idx}. {item}")

        if assistant_points:
            summary_lines.append("### Assistant Progress")
            for idx, item in enumerate(assistant_points[-6:], 1):
                summary_lines.append(f"{idx}. {item}")

        summary_lines.append(
            "### Compression Note\n如果后续细节与当前上下文冲突，以最近保留的原始消息和最新任务状态为准。"
        )
        return "\n".join(summary_lines)

    def _normalize_history_messages(
        self, history_messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for msg in history_messages:
            role = msg.get("role")
            if role not in ("user", "assistant", "tool"):
                continue

            content = _normalize_message_content(msg.get("content", ""))
            normalized_msg: Dict[str, Any] = {"role": role, "content": content}

            if role == "assistant":
                tool_calls = msg.get("tool_calls", [])
                tool_results = msg.get("tool_results", [])
                if tool_calls:
                    normalized_msg["tool_calls"] = tool_calls
                if not content and not tool_calls:
                    continue
                normalized.append(normalized_msg)

                if tool_calls and tool_results:
                    for result in tool_results:
                        if not isinstance(result, dict):
                            continue
                        tool_call_id = result.get("tool_call_id")
                        result_content = _normalize_message_content(
                            result.get("content", "")
                        )
                        if not tool_call_id or not result_content:
                            continue
                        tool_msg: Dict[str, Any] = {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": result_content,
                        }
                        if result.get("name"):
                            tool_msg["name"] = result.get("name")
                        normalized.append(tool_msg)
                continue
            elif role == "tool":
                tool_call_id = msg.get("tool_call_id")
                if not tool_call_id or not content:
                    continue
                normalized_msg["tool_call_id"] = tool_call_id
                if msg.get("name"):
                    normalized_msg["name"] = msg.get("name")
            else:
                if not content:
                    continue

            normalized.append(normalized_msg)

        return normalized

    def _has_structured_tool_history(self, history_messages: List[Dict[str, Any]]) -> bool:
        for msg in history_messages:
            if msg.get("role") == "tool":
                return True
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                return True
        return False

    def _compact_structured_history_messages(
        self,
        history_messages: List[Dict[str, Any]],
        history_budget: int,
    ) -> List[Dict[str, Any]]:
        if not history_messages or history_budget <= 0:
            return []

        if estimate_tokens_from_messages(history_messages) <= history_budget:
            return history_messages

        recent_messages: List[Dict[str, Any]] = []
        recent_tokens = 0
        include_open_tool_exchange = False

        for msg in reversed(history_messages):
            msg_tokens = estimate_tokens_from_messages([msg])
            role = msg.get("role")
            has_tool_calls = role == "assistant" and bool(msg.get("tool_calls"))
            force_include = include_open_tool_exchange or role == "tool"

            if recent_messages and recent_tokens + msg_tokens > history_budget and not force_include:
                break

            recent_messages.insert(0, msg)
            recent_tokens += msg_tokens

            if role == "tool":
                include_open_tool_exchange = True
            elif include_open_tool_exchange and has_tool_calls:
                include_open_tool_exchange = False

        return recent_messages

    def _compact_history_messages(
        self,
        history_messages: List[Dict[str, Any]],
        history_budget: int,
    ) -> List[Dict[str, Any]]:
        if not history_messages or history_budget <= 0:
            return []

        normalized = self._normalize_history_messages(history_messages)

        if not normalized:
            return []

        if self._has_structured_tool_history(normalized):
            return self._compact_structured_history_messages(normalized, history_budget)

        for item in normalized:
            item["content"] = self._trim_message_content(
                item["content"], MAX_HISTORY_SNIPPET_CHARS
            )

        if estimate_tokens_from_messages(normalized) <= history_budget:
            return normalized

        recent_messages: List[Dict[str, str]] = []
        recent_tokens = 0
        min_recent_tokens = int(history_budget * 0.55)
        for msg in reversed(normalized):
            msg_tokens = estimate_tokens_from_messages([msg])
            if recent_messages and recent_tokens + msg_tokens > history_budget:
                break
            recent_messages.insert(0, msg)
            recent_tokens += msg_tokens
            if (
                len(recent_messages) >= RECENT_HISTORY_MIN_MESSAGES
                and recent_tokens >= min_recent_tokens
            ):
                break

        if len(recent_messages) == len(normalized):
            return recent_messages

        compacted = normalized[: len(normalized) - len(recent_messages)]
        compact_summary = self._summarize_compacted_messages(compacted)
        if not compact_summary:
            return recent_messages

        summary_message = {
            "role": "assistant",
            "content": compact_summary,
        }
        result_messages = [summary_message] + recent_messages

        while (
            len(result_messages) > 1
            and estimate_tokens_from_messages(result_messages) > history_budget
        ):
            if len(recent_messages) > 1:
                recent_messages.pop(0)
                result_messages = [summary_message] + recent_messages
                continue

            summary_message["content"] = self._trim_message_content(
                summary_message["content"], 800
            )
            result_messages = [summary_message]
            break

        return result_messages

    def set_callback(self, event: str, callback: Callable):
        self._callbacks[event] = callback

    def _emit(self, event: str, *args, **kwargs):
        callback = self._callbacks.get(event)
        if callback:
            callback(*args, **kwargs)

    @property
    def is_streaming(self) -> bool:
        return self._is_streaming

    @property
    def session_manager(self) -> SessionManager:
        return self._session_manager

    @property
    def current_agent(self) -> Optional[str]:
        return self._current_agent

    def switch_agent(self, agent_name: Optional[str]):
        agent_manager = self._get_agent_manager()
        session = self._session_manager.get_current_session()

        if agent_name is None or agent_name.lower() in ("default", "通用"):
            self._current_agent = "plan"
            if session:
                session.task_state.switch_agent("plan")
            logger.info("[ChatEngine] Switched to default agent: plan")
            self._emit("agent_switched", "plan")
            self._emit("task_state_changed", session.task_state if session else None)
            return

        agent = agent_manager.get_agent(agent_name)
        if not agent:
            logger.warning(f"[ChatEngine] Agent not found: {agent_name}")
            return

        self._current_agent = agent_name
        if session:
            session.task_state.switch_agent(agent_name)
        logger.info(f"[ChatEngine] Switched to agent: {agent_name}")
        self._emit("agent_switched", agent_name)
        self._emit("task_state_changed", session.task_state if session else None)

    def send_message(
        self,
        user_text: str,
        context_params: Optional[Dict] = None,
    ) -> bool:
        if self._is_streaming:
            logger.warning("[ChatEngine] Already streaming, ignoring new message")
            return False

        session = self._session_manager.get_current_session()
        if not session:
            logger.error("[ChatEngine] No current session")
            return False

        llm_config = self._get_model_config()
        if not llm_config:
            logger.error("[ChatEngine] No LLM config available")
            self._emit("error", "配置无效，请检查模型设置")
            return False

        self._is_streaming = True
        session.add_user_message(content=user_text, params=context_params or {})
        session.task_state.set_goal(user_text)
        session.task_state.switch_agent(self._current_agent or "plan")
        session.task_state.infer_stage_from_turn(user_text)
        if session.task_state.stage == "verify":
            session.task_state.update_verification("running", "Verification requested")

        self._emit("user_message_added", user_text)
        self._emit("task_state_changed", session.task_state)

        messages = self._build_messages(session, llm_config)

        if self._current_agent:
            available_tools = self._get_agent_manager().get_agent_tools_schema(
                self._current_agent
            )
        else:
            available_tools = get_builtin_tools_schema()

        self._start_worker(messages, llm_config, available_tools)
        return True

    def _build_messages(self, session: ChatSession, llm_config: Dict) -> List[Dict]:
        messages: List[Dict[str, Any]] = []
        task_state = session.task_state

        if self._current_agent:
            full_system_prompt = self._get_agent_manager().get_agent_system_prompt(
                self._current_agent
            )
        else:
            full_system_prompt = self._get_agent_manager().get_unified_system_prompt()

        prompt_parts = [
            full_system_prompt,
            task_state.build_context_block(),
            task_state.build_event_digest(),
        ]

        custom_prompt = llm_config.get("系统提示", "").strip()
        if custom_prompt:
            prompt_parts.append(custom_prompt)

        messages.append(
            {
                "role": "system",
                "content": "\n\n".join(part for part in prompt_parts if part),
            }
        )

        max_context_tokens = self._get_context_budget(llm_config)
        normalized_session_messages = self._normalize_history_messages(
            session.get_context_messages()
        )

        context_provider = self._get_context_provider()
        latest_user_message = ""
        history_messages = normalized_session_messages
        if history_messages and history_messages[-1].get("role") == "user":
            latest_user_message = history_messages[-1].get("content", "")
            history_messages = history_messages[:-1]

        if self._get_memory_context:
            memory_query = "\n".join(
                part
                for part in [task_state.current_goal or "", latest_user_message]
                if part.strip()
            ).strip()
            try:
                memory_context = self._get_memory_context(memory_query)
            except TypeError:
                memory_context = self._get_memory_context()
            if memory_context:
                messages[0]["content"] = messages[0]["content"] + "\n\n" + memory_context

        task_prelude = self._build_user_task_prelude(task_state)

        supports_vision = provider_supports_vision(llm_config)

        context_text = context_provider.get_text_context() if context_provider else ""
        final_user_text = task_prelude + context_text + latest_user_message

        available_history_budget = max_context_tokens - estimate_tokens(final_user_text) - 200
        history_for_api = self._compact_history_messages(
            history_messages, available_history_budget
        )
        messages.extend(history_for_api)

        if supports_vision and context_provider:
            has_image = any(
                item[-1] for item in getattr(context_provider, "_context_cache", [])
            )
            if has_image:
                user_content = context_provider.get_multimodal_context_items()
                user_content.append({"type": "text", "text": final_user_text})
                messages.append({"role": "user", "content": user_content})
                return messages

        messages.append({"role": "user", "content": final_user_text})

        return messages

    def _build_user_task_prelude(self, task_state) -> str:
        return (
            f"[Task Stage: {task_state.stage}]\n"
            f"[Current Goal: {task_state.current_goal or 'N/A'}]\n"
            f"[Verification: {task_state.verification_status}]\n\n"
        )

    def _get_context_budget(self, llm_config: Dict) -> int:
        profile = get_provider_profile(llm_config)
        context_limit = int(profile.get("context_limit", 128000))

        for key in ("context_limit", "context_window", "max_context_tokens", "max_input_tokens"):
            value = llm_config.get(key)
            if value in (None, ""):
                continue
            try:
                context_limit = int(value)
                break
            except Exception:
                continue

        max_tokens = llm_config.get(
            "max_tokens",
            llm_config.get("最大Token", llm_config.get("鏈€澶oken", profile.get("max_output_tokens", 4096))),
        )
        try:
            max_tokens = int(max_tokens)
        except Exception:
            max_tokens = int(profile.get("max_output_tokens", 4096))

        model_name = str(
            llm_config.get("model", llm_config.get("模型名称", llm_config.get("妯″瀷鍚嶇О", "")))
        ).lower()
        profile_max_output = int(profile.get("max_output_tokens", 4096))

        if max_tokens > profile_max_output * 2:
            context_limit = min(context_limit, max_tokens)

        reserved = min(800, max_tokens)
        if "o1" in model_name or "o3" in model_name:
            reserved = min(max_tokens, 32000)

        return max(500, context_limit - reserved)
    def _get_token_budget(self, llm_config: Dict) -> int:
        profile = get_provider_profile(llm_config)
        context_limit = profile.get("context_limit", 128000)
        for key in ("context_limit", "context_window", "max_context_tokens", "max_input_tokens"):
            value = llm_config.get(key)
            if value in (None, ""):
                continue
            try:
                context_limit = int(value)
                break
            except Exception:
                continue

        max_tokens = llm_config.get(
            "max_tokens",
            llm_config.get("鏈€澶oken", profile.get("max_output_tokens", 4096)),
        )
        try:
            max_tokens = int(max_tokens)
        except Exception:
            max_tokens = int(profile.get("max_output_tokens", 4096))

        model_name = str(
            llm_config.get("model", llm_config.get("妯″瀷鍚嶇О", ""))
        ).lower()
        reserved = min(800, max_tokens)
        if "o1" in model_name or "o3" in model_name:
            reserved = min(max_tokens, 32000)
        return max(500, int(context_limit) - reserved)

    def get_context_usage_snapshot(
        self, session: Optional[ChatSession] = None, llm_config: Optional[Dict] = None
    ) -> Dict[str, int]:
        session = session or self._session_manager.get_current_session()
        llm_config = llm_config or self._get_model_config()
        if not session or not llm_config:
            return {"used_tokens": 0, "budget_tokens": 0, "percent": 0}

        messages = self._build_messages(session, llm_config)
        budget_tokens = max(1, self._get_context_budget(llm_config))
        used_tokens = estimate_tokens_from_messages(messages)
        percent = max(0, min(100, int((used_tokens / budget_tokens) * 100)))
        return {
            "used_tokens": used_tokens,
            "budget_tokens": budget_tokens,
            "percent": percent,
        }

    def _start_worker(
        self,
        messages: List[Dict],
        llm_config: Dict,
        tools: List[Dict],
    ):
        def build_stage_prompt():
            session = self._session_manager.get_current_session()
            if session:
                return resolve_stage_prompt(session.task_state.stage)
            return resolve_stage_prompt("discover")

        def on_stage_changed(new_stage: str):
            session = self._session_manager.get_current_session()
            if session and new_stage in CODING_STAGES:
                session.task_state.set_stage(new_stage, "model-requested")
                self._emit("task_state_changed", session.task_state)

        if self._tool_executor:
            self._tool_executor.set_stage_callback(on_stage_changed)

        compaction_prompt = ""
        compaction_config = {}
        if self._agent_manager and self._agent_manager.get_agent("compaction"):
            compaction_prompt = self._agent_manager.get_agent_system_prompt(
                "compaction"
            )
            compaction_config = self._agent_manager.get_agent_config("compaction")

        self._current_worker = OpenAIChatWorker(
            messages=messages,
            llm_config=llm_config,
            tools=tools,
            tool_executor=self._tool_executor,
            tool_start_callback=self._callbacks.get("tool_call_sync_requested"),
            get_stage_prompt=build_stage_prompt,
            stage_changed_callback=on_stage_changed,
            permission_check_callback=self._check_tool_permission,
            compaction_prompt=compaction_prompt,
            compaction_config=compaction_config,
        )

        self._current_worker.content_received.connect(self._on_content_received)
        self._current_worker.tool_call_started.connect(self._on_tool_call_started)
        self._current_worker.tool_result_received.connect(self._on_tool_result_received)
        self._current_worker.error_occurred.connect(self._on_error)
        self._current_worker.finished_with_content.connect(self._on_worker_finished)
        self._current_worker.finished_with_messages.connect(
            self._on_worker_messages_updated
        )
        self._current_worker.question_asked.connect(self._on_question_asked)
        self._current_worker.permission_approval_requested.connect(
            self._on_permission_approval_requested
        )

        self._current_worker.start()
        self._emit("stream_started")

    def _on_content_received(self, content_piece: str):
        self._emit("content_received", content_piece)

    def _on_tool_call_started(
        self, tool_call_id: str, tool_name: str, arguments: dict, round_id: str
    ):
        self._emit("tool_call_started", tool_call_id, tool_name, arguments, round_id)

    def _on_question_asked(
        self, tool_call_id: str, question: str, options: list, multiple: bool
    ):
        self._emit("question_asked", tool_call_id, question, options, multiple)

    def _on_tool_result_received(
        self, tool_call_id: str, tool_name: str, arguments: dict, result: Any
    ):
        session = self._session_manager.get_current_session()
        if session:
            success = result.success if hasattr(result, "success") else True
            session.task_state.update_tool_result(
                tool_name, arguments or {}, str(result), success
            )

            if tool_name == "run_verify":
                session.task_state.update_verification(
                    "passed" if success else "failed", str(result)
                )
            elif tool_name == "bash":
                command = (arguments or {}).get("command", "")
                if any(
                    token in command.lower() for token in ["pytest", "test", "compile"]
                ):
                    session.task_state.update_verification(
                        "passed" if success else "failed", str(result)
                    )
            if tool_name in ("todowrite", "todoread") and self._tool_executor:
                session.task_state.update_todos(self._tool_executor.todo_list)
            if tool_name == "task":
                session.task_state.set_stage("summarize", "sub-agent-result")
            if tool_name == "switch_stage" and success:
                new_stage = (arguments or {}).get("stage", "")
                if new_stage:
                    session.task_state.set_stage(new_stage, "tool-requested")
            self._emit("task_state_changed", session.task_state)

        self._emit("tool_result_received", tool_call_id, tool_name, arguments, result)

    def _on_worker_finished(self, response: str):
        self._is_streaming = False
        self._emit("stream_finished", response)

    def _on_worker_messages_updated(self, messages: List[Dict]):
        self._emit("messages_updated", messages)

    def _on_error(self, error: str):
        self._is_streaming = False
        session = self._session_manager.get_current_session()
        if session:
            session.task_state.record_error(error)
            self._emit("task_state_changed", session.task_state)
        self._emit("error", error)

    def stop(self):
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.cancel()
        self._current_worker = None
        self._is_streaming = False

    def provide_question_answer(self, answer: str):
        if self._current_worker and hasattr(self._current_worker, "provide_answer"):
            self._current_worker.provide_answer(answer)

