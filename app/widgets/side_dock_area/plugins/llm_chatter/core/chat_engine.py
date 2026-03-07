# -*- coding: utf-8 -*-
"""
聊天引擎模块 - 处理 LLM 对话的核心逻辑
"""

from typing import Dict, List, Optional, Any, Callable

from loguru import logger

from app.widgets.side_dock_area.plugins.llm_chatter.core.task_state import (
    CODING_STAGES,
)
from app.widgets.side_dock_area.plugins.llm_chatter.utils.builtin_tools import (
    get_builtin_tools_schema,
)
from app.widgets.side_dock_area.plugins.llm_chatter.utils.chat_session import (
    ChatSession,
    SessionManager,
)
from app.widgets.side_dock_area.plugins.llm_chatter.utils.worker import OpenAIChatWorker


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
    ):
        self._session_manager = session_manager
        self._get_model_config = get_model_config
        self._get_context_provider = get_context_provider
        self._tool_executor = tool_executor
        self._agent_manager = agent_manager
        self._get_chat_cards = get_chat_cards

        self._current_worker: Optional[OpenAIChatWorker] = None
        self._is_streaming = False
        self._callbacks: Dict[str, Callable] = {}
        self._current_agent: Optional[str] = "plan"

    def _get_agent_manager(self):
        return self._agent_manager

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
            self._build_stage_prompt(task_state.stage),
            task_state.build_context_block(),
            task_state.build_event_digest(),
        ]

        custom_prompt = llm_config.get("绯荤粺鎻愮ず", "").strip()
        if custom_prompt:
            prompt_parts.append(custom_prompt)

        messages.append(
            {"role": "system", "content": "\n\n".join(part for part in prompt_parts if part)}
        )

        cards = self._get_chat_cards() if self._get_chat_cards else []
        for card in cards[-8:]:
            role = getattr(card, "role", None)
            if not role or role == "system":
                continue

            content = ""
            if hasattr(card, "viewer") and hasattr(card.viewer, "get_plain_text"):
                content = card.viewer.get_plain_text()
            if not content:
                continue

            if role in ("user", "assistant"):
                messages.append({"role": role, "content": content})

        context_provider = self._get_context_provider()
        user_text = session.messages[-1].get("content", "") if session.messages else ""
        task_prelude = self._build_user_task_prelude(task_state)

        model_name = str(llm_config.get("妯″瀷鍚嶇О", "")).lower()
        supports_vision = any(
            marker in model_name
            for marker in ["4o", "vision", "vl", "gemini", "claude-3"]
        )

        if supports_vision and context_provider:
            has_image = any(
                item[-1] for item in getattr(context_provider, "_context_cache", [])
            )
            if has_image:
                user_content = context_provider.get_multimodal_context_items()
                user_content.append({"type": "text", "text": task_prelude + user_text})
                messages.append({"role": "user", "content": user_content})
                return messages

        if context_provider:
            context_text = context_provider.get_text_context()
            messages.append(
                {"role": "user", "content": task_prelude + context_text + user_text}
            )
        else:
            messages.append({"role": "user", "content": task_prelude + user_text})

        return messages

    def _build_stage_prompt(self, stage: str) -> str:
        if stage not in CODING_STAGES:
            stage = "discover"

        prompts = {
            "discover": "## Active Stage: Discover\nFocus on understanding project structure, constraints, and the smallest relevant context first.",
            "plan": "## Active Stage: Plan\nProduce an implementation path with concrete files, risks, and validation steps.",
            "edit": "## Active Stage: Edit\nMake focused changes, preserve local patterns, and keep edits easy to verify.",
            "verify": "## Active Stage: Verify\nPrefer targeted validation commands and explain failures concretely.",
            "review": "## Active Stage: Review\nInspect for regressions, missing tests, and weak assumptions before declaring completion.",
            "summarize": "## Active Stage: Summarize\nCompress the latest work into a concise handoff that supports the next coding step.",
        }
        return prompts[stage]

    def _build_user_task_prelude(self, task_state) -> str:
        return (
            f"[Task Stage: {task_state.stage}]\n"
            f"[Current Goal: {task_state.current_goal or 'N/A'}]\n"
            f"[Verification: {task_state.verification_status}]\n\n"
        )

    def _start_worker(
        self,
        messages: List[Dict],
        llm_config: Dict,
        tools: List[Dict],
    ):
        self._current_worker = OpenAIChatWorker(
            messages=messages,
            llm_config=llm_config,
            tools=tools,
            tool_executor=self._tool_executor,
            tool_start_callback=self._callbacks.get("tool_call_sync_requested"),
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
                if any(token in command.lower() for token in ["pytest", "test", "compile"]):
                    session.task_state.update_verification(
                        "passed" if success else "failed", str(result)
                    )
            if tool_name in ("todowrite", "todoread") and self._tool_executor:
                session.task_state.update_todos(self._tool_executor.todo_list)
            if tool_name == "task":
                session.task_state.set_stage("summarize", "sub-agent-result")
            self._emit("task_state_changed", session.task_state)

        self._emit("tool_result_received", tool_call_id, tool_name, arguments, result)

    def _on_worker_finished(self, response: str):
        self._is_streaming = False
        session = self._session_manager.get_current_session()
        if session:
            if session.task_state.stage in ("edit", "verify", "review"):
                session.task_state.set_stage("summarize", "turn-finished")
            self._emit("task_state_changed", session.task_state)
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
