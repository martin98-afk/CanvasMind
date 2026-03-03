# -*- coding: utf-8 -*-
"""
聊天引擎模块 - 处理 LLM 对话的核心逻辑
"""

import json
import re
from typing import Dict, List, Optional, Any, Callable
from loguru import logger

from app.widgets.side_dock_area.plugins.llm_chatter.utils.chat_session import (
    SessionManager,
    ChatSession,
)
from app.widgets.side_dock_area.plugins.llm_chatter.utils.builtin_tools import (
    get_builtin_tools_schema,
)
from app.widgets.side_dock_area.plugins.llm_chatter.utils.worker import OpenAIChatWorker


class ChatEngine:
    """聊天引擎 - 负责消息发送、接收等核心逻辑"""

    def __init__(
        self,
        session_manager: SessionManager,
        get_model_config: Callable[[], Dict[str, Any]],
        get_context_provider: Any,
        tool_executor: Optional[Any] = None,
    ):
        self._session_manager = session_manager
        self._get_model_config = get_model_config
        self._get_context_provider = get_context_provider
        self._tool_executor = tool_executor

        self._current_worker: Optional[OpenAIChatWorker] = None
        self._is_streaming = False

        self._callbacks: Dict[str, Callable] = {}

        self._current_agent: Optional[str] = None
        self._agent_manager = None

    def _get_agent_manager(self):
        if self._agent_manager is None:
            from app.widgets.side_dock_area.plugins.llm_chatter.core.agent import (
                create_agent_manager,
            )

            self._agent_manager = create_agent_manager()
        return self._agent_manager

    def set_callback(self, event: str, callback: Callable):
        self._callbacks[event] = callback

    def _emit(self, event: str, *args, **kwargs):
        if event in self._callbacks:
            self._callbacks[event](*args, **kwargs)

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
        """切换智能体"""
        agent_manager = self._get_agent_manager()

        if agent_name is None or agent_name.lower() in ("default", "general", "通用"):
            self._current_agent = None
            logger.info("[ChatEngine] Switched to default mode")
            self._emit("agent_switched", "通用模式")
            return

        agent = agent_manager.get_agent(agent_name)
        if agent:
            self._current_agent = agent_name
            logger.info(f"[ChatEngine] Switched to agent: {agent_name}")
            self._emit("agent_switched", agent_name)
        else:
            logger.warning(f"[ChatEngine] Agent not found: {agent_name}")

    def send_message(
        self,
        user_text: str,
        context_params: Optional[Dict] = None,
    ) -> bool:
        if self._is_streaming:
            logger.warning("[ChatEngine] Already streaming, ignoring new message")
            return False

        self._is_streaming = True

        session = self._session_manager.get_current_session()
        if not session:
            logger.error("[ChatEngine] No current session")
            return False

        llm_config = self._get_model_config()
        if not llm_config:
            logger.error("[ChatEngine] No LLM config available")
            self._emit("error", "配置无效，请检查模型设置")
            return False

        session.add_user_message(
            content=user_text,
            params=context_params or {},
        )

        self._emit("user_message_added", user_text)

        messages = self._build_messages(session, llm_config)
        available_tools = get_builtin_tools_schema()

        self._start_worker(messages, llm_config, available_tools)
        return True

    def _build_messages(self, session: ChatSession, llm_config: Dict) -> List[Dict]:
        messages = []

        if self._current_agent:
            full_system_prompt = self._get_agent_manager().get_agent_system_prompt(
                self._current_agent
            )
        else:
            full_system_prompt = self._get_agent_manager().get_unified_system_prompt()
        print(self._current_agent)
        print(full_system_prompt)
        custom_prompt = llm_config.get("系统提示", "").strip()
        if custom_prompt:
            full_system_prompt += f"\n\n{custom_prompt}"

        messages.append({"role": "system", "content": full_system_prompt})

        for msg in session.messages[:-1]:
            role = msg.get("role")
            content = msg.get("content", "")

            if "tool_calls" in msg:
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.get("content", ""),
                        "tool_calls": msg.get("tool_calls", []),
                    }
                )
            elif role == "tool":
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.get("tool_call_id"),
                        "content": content,
                    }
                )
            else:
                if isinstance(content, list):
                    content = "\n".join(
                        [item["text"] for item in content if item.get("type") == "text"]
                    )
                messages.append({"role": role, "content": content})

        context_provider = self._get_context_provider()
        user_text = session.messages[-1].get("content", "")

        model_name = str(llm_config.get("模型名称", "")).lower()
        supports_vision = any(
            x in model_name for x in ["4o", "vision", "vl", "gemini", "claude-3"]
        )

        if supports_vision and context_provider:
            has_image = any(
                [item[-1] for item in getattr(context_provider, "_context_cache", [])]
            )
            if has_image:
                user_content = context_provider.get_multimodal_context_items()
                user_content.append({"type": "text", "text": user_text})
                messages.append({"role": "user", "content": user_content})
                return messages

        if context_provider:
            context_text = context_provider.get_text_context()
            messages.append({"role": "user", "content": context_text + user_text})
        else:
            messages.append({"role": "user", "content": user_text})

        return messages

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
        )

        self._current_worker.content_received.connect(self._on_content_received)
        self._current_worker.tool_call_started.connect(self._on_tool_call_started)
        self._current_worker.tool_result_received.connect(self._on_tool_result_received)
        self._current_worker.error_occurred.connect(self._on_error)
        self._current_worker.finished_with_content.connect(self._on_worker_finished)
        self._current_worker.question_asked.connect(self._on_question_asked)

        self._current_worker.start()
        self._emit("stream_started")

    def _on_content_received(self, content_piece: str):
        self._emit("content_received", content_piece)

    def _on_tool_call_started(
        self, tool_call_id: str, tool_name: str, arguments: dict, round_id: str
    ):
        self._emit("tool_call_started", tool_call_id, tool_name, arguments, round_id)

    def _on_question_asked(self, tool_call_id: str, question: str, options: list):
        self._emit("question_asked", tool_call_id, question, options)

    def _on_tool_result_received(
        self, tool_call_id: str, tool_name: str, arguments: dict, result: Any
    ):
        self._emit("tool_result_received", tool_call_id, tool_name, arguments, result)

    def _on_worker_finished(self, response: str):
        self._is_streaming = False

        session = self._session_manager.get_current_session()
        if session:
            session.add_assistant_message(content=response)

        self._emit("stream_finished", response)

    def _on_error(self, error: str):
        self._is_streaming = False
        self._emit("error", error)

    def stop(self):
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.cancel()
        self._current_worker = None
        self._is_streaming = False

    def provide_question_answer(self, answer: str):
        if self._current_worker and hasattr(self._current_worker, "provide_answer"):
            self._current_worker.provide_answer(answer)
