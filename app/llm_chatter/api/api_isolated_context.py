# -*- coding: utf-8 -*-
"""
API 隔离上下文 - 为 API 调用创建完全独立的环境

参考复制窗口的实现，为每个 API 请求创建：
1. 独立的 SessionManager
2. 独立的 ToolExecutor（但复用 BuiltinTools）
3. 独立的 AgentManager
4. 独立的上下文状态

这样 API 调用与 UI 完全隔离，不会产生任何状态冲突。
"""

import uuid
import threading
from typing import Optional, Dict, Any, List, Callable, Any
from loguru import logger


class IsolatedChatContext:
    """API 隔离上下文 - 封装完全独立的组件实例
    
    每个 API 请求都会创建一个独立的上下文，
    与 UI 窗口完全隔离，互不影响。
    """

    def __init__(
        self,
        context_id: str,
        main_widget,
        target_session: Any = None,
        model_config: Dict[str, Any] = None,
    ):
        """
        Args:
            context_id: 上下文唯一标识（通常为 stream_id）
            main_widget: UI 主窗口（用于获取可复用的基础组件）
            target_session: 目标会话（从 SQLite 加载）
            model_config: 模型配置（可选，从 main_widget 获取）
        """
        self.context_id = context_id
        self._main_widget = main_widget
        self._model_config = model_config
        
        # 创建独立的 SessionManager
        self._session_manager = self._create_session_manager(target_session)
        
        # 创建独立的 ToolExecutor（使用隔离的 session 上下文）
        self._tool_executor = self._create_tool_executor()
        
        # 创建独立的 AgentManager
        self._agent_manager = self._create_agent_manager()
        
        # 独立的上下文提供者（可以是 UI 的上下文选择器的副本）
        self._context_provider = None
        
        # 线程锁，确保状态修改的线程安全
        self._lock = threading.Lock()
        
        # 设置初始 session
        if target_session:
            self._session_manager.set_current_session(target_session)

    def _create_session_manager(self, target_session) -> Any:
        """创建独立的 SessionManager"""
        from app.llm_chatter.utils.chat_session import (
            SessionManager,
            ChatSession,
        )
        
        manager = SessionManager()
        
        if target_session:
            # 创建一个深拷贝，避免共享引用
            session_copy = ChatSession.from_dict({
                "session_id": target_session.session_id,
                "name": target_session.name,
                "messages": list(target_session.messages) if target_session.messages else [],
                "topic_summary": target_session.topic_summary,
                "created_at": target_session.created_at,
                "last_updated": target_session.last_updated,
            })
            manager.sessions.append(session_copy)
            manager.current_index = 0
        else:
            # 创建新会话
            manager.create_new_session()
        
        return manager

    def _create_tool_executor(self) -> Any:
        """创建独立的 ToolExecutor
        
        ToolExecutor 的关键状态是 session_id 和 call_id，
        这些必须在每次 API 调用时独立设置。
        """
        from app.llm_chatter.core.tool_executor import (
            ToolExecutor,
        )
        
        # 获取 UI 的 ToolExecutor 以复用 BuiltinTools
        ui_tool_executor = getattr(self._main_widget, '_tool_executor', None)
        
        # 创建隔离的 ToolExecutor
        # 注意：这里传入 homepage 以保持 BuiltinTools 的功能
        homepage = getattr(self._main_widget, 'homepage', None)
        executor = ToolExecutor(homepage=homepage)
        
        # 复用 UI 的 BuiltinTools 实例（这是核心，只读共享）
        if ui_tool_executor and ui_tool_executor._builtin_tools:
            executor._builtin_tools = ui_tool_executor._builtin_tools
            
            # 复制其他可共享的配置
            if ui_tool_executor._canvas_tools_executor:
                executor._canvas_tools_executor = ui_tool_executor._canvas_tools_executor
        
        # 设置隔离的 session 上下文
        current_session = self._session_manager.get_current_session()
        session_id = current_session.session_id if current_session else str(uuid.uuid4())
        executor.set_session_context(session_id, call_id=None)
        
        # 设置隔离的会话消息获取器（使用隔离的 session_manager）
        executor.set_session_messages_getter(self._get_session_messages_for_tools)
        
        return executor
    
    def _get_session_messages_for_tools(self) -> List[Dict[str, Any]]:
        """获取当前会话消息（用于工具调用）"""
        session = self._session_manager.get_current_session()
        if not session:
            return []
        return list(session.messages or [])

    def _create_agent_manager(self) -> Any:
        """创建独立的 AgentManager
        
        AgentManager 通常是无状态的配置管理，
        可以复用 UI 的实例或创建新实例。
        """
        from app.llm_chatter.core.agent import AgentManager
        
        # 尝试复用 UI 的 AgentManager（如果可用）
        ui_agent_manager = getattr(self._main_widget, '_agent_manager', None)
        if ui_agent_manager:
            # AgentManager 通常是无状态的，可以复用
            return ui_agent_manager
        
        # 创建新的 AgentManager
        return AgentManager()

    def _get_model_config(self) -> Dict[str, Any]:
        """获取模型配置"""
        if self._model_config:
            return self._model_config
        
        # 从 main_widget 获取
        if hasattr(self._main_widget, '_get_current_model_config'):
            return self._main_widget._get_current_model_config()
        
        return {}

    def _get_context_provider(self):
        """获取上下文提供者
        
        API 模式返回 None，完全隔离。
        UI 的 context_selector 可能包含共享状态，不适合 API 模式使用。
        """
        # API 模式不使用上下文选择器，完全隔离
        return None

    def set_call_id(self, call_id: str) -> None:
        """设置当前调用 ID（用于文件操作记录）"""
        with self._lock:
            if self._tool_executor:
                self._tool_executor.set_call_id(call_id)

    def update_session_context(self) -> None:
        """更新 session 上下文（当切换会话时调用）"""
        with self._lock:
            current_session = self._session_manager.get_current_session()
            if current_session and self._tool_executor:
                self._tool_executor.set_session_context(
                    current_session.session_id, 
                    call_id=None
                )

    def create_chat_engine(
        self,
        worker_callbacks: Optional[Dict[str, Callable]] = None,
        api_mode: bool = True,
    ) -> Any:
        """创建隔离的 ChatEngine 实例
        
        Returns:
            配置好的 ChatEngine，已绑定到隔离的组件
        """
        from app.llm_chatter.core.chat_engine import (
            ChatEngine,
        )
        
        engine = ChatEngine(
            session_manager=self._session_manager,
            get_model_config=self._get_model_config,
            get_context_provider=self._get_context_provider,
            tool_executor=self._tool_executor,
            agent_manager=self._agent_manager,
            get_chat_cards=None,  # API 模式不需要 UI 卡片
            get_memory_context=getattr(self._main_widget, '_build_memory_context_for_engine', None),
            worker_callbacks=worker_callbacks,
            api_mode=api_mode,
        )
        
        return engine

    def get_current_session(self) -> Any:
        """获取当前会话"""
        return self._session_manager.get_current_session()

    def add_message(self, role: str, content: str) -> None:
        """添加消息到当前会话"""
        session = self._session_manager.get_current_session()
        if session:
            session.add_user_message(content) if role == "user" else session.add_assistant_message(content)

    def get_messages(self) -> List[Dict[str, Any]]:
        """获取当前会话的所有消息"""
        session = self._session_manager.get_current_session()
        if session:
            return list(session.messages or [])
        return []

    def cleanup(self) -> None:
        """清理资源"""
        with self._lock:
            # 清理 ToolExecutor 的状态
            if self._tool_executor:
                self._tool_executor._session_id = None
                self._tool_executor._call_id = None
                # 清空待办列表，避免影响 UI
                if self._tool_executor._builtin_tools:
                    self._tool_executor._builtin_tools.todo_clear()
            
            logger.debug(f"[IsolatedContext] 上下文已清理: {self.context_id}")


class IsolatedContextRegistry:
    """隔离上下文注册表 - 管理所有活跃的 API 隔离上下文"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._contexts: Dict[str, IsolatedChatContext] = {}
                    cls._instance._context_lock = threading.Lock()
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> "IsolatedContextRegistry":
        """获取单例实例"""
        return cls()
    
    def create_context(
        self,
        context_id: str,
        main_widget,
        target_session: Any = None,
        model_config: Dict[str, Any] = None,
    ) -> IsolatedChatContext:
        """创建新的隔离上下文
        
        Args:
            context_id: 上下文 ID（通常为 stream_id）
            main_widget: UI 主窗口
            target_session: 目标会话
            model_config: 模型配置
        
        Returns:
            新创建的隔离上下文
        """
        with self._context_lock:
            # 如果已存在，先清理
            if context_id in self._contexts:
                self._contexts[context_id].cleanup()
            
            ctx = IsolatedChatContext(
                context_id=context_id,
                main_widget=main_widget,
                target_session=target_session,
                model_config=model_config,
            )
            self._contexts[context_id] = ctx
            logger.debug(f"[ContextRegistry] 创建新上下文: {context_id}")
            return ctx
    
    def get_context(self, context_id: str) -> Optional[IsolatedChatContext]:
        """获取隔离上下文"""
        with self._context_lock:
            return self._contexts.get(context_id)
    
    def remove_context(self, context_id: str) -> None:
        """移除并清理隔离上下文"""
        with self._context_lock:
            if context_id in self._contexts:
                self._contexts[context_id].cleanup()
                del self._contexts[context_id]
                logger.debug(f"[ContextRegistry] 移除上下文: {context_id}")
    
    def get_active_count(self) -> int:
        """获取活跃上下文数量"""
        with self._context_lock:
            return len(self._contexts)
    
    def cleanup_all(self) -> None:
        """清理所有上下文"""
        with self._context_lock:
            for ctx in self._contexts.values():
                ctx.cleanup()
            self._contexts.clear()
            logger.info("[ContextRegistry] 所有上下文已清理")
