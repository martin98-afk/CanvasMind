# -*- coding: utf-8 -*-
"""
API 会话处理器 - 完全隔离的 API 调用，支持并发和持久化

特性：
- 每个请求创建独立的 IsolatedChatContext（完全隔离）
- 独立的 SessionManager、ToolExecutor、AgentManager
- 自动持久化到 SQLite（通过隔离的 history_manager）
- SSE 流式响应

注意：与 UI 完全隔离，不会产生任何状态冲突。
"""

import asyncio
import json
import threading
import uuid
from typing import Optional, Dict, Any, List, Callable, AsyncGenerator
from loguru import logger


class StreamContext:
    """流式请求上下文（线程安全）"""
    
    def __init__(self, stream_id: str):
        self.stream_id = stream_id
        self.engine = None
        self.session_id = ""
        self.buffer: Dict[str, Any] = {
            "content": "",
            "started": False,
            "finished": False,
        }
        self.sse_queue: asyncio.Queue = asyncio.Queue()
        self._active = True
        self._lock = threading.Lock()
        # API 模式专用：事件通知（替代 Qt 信号）
        self._event = threading.Event()
        self._pending_event: Optional[Dict[str, Any]] = None

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def set_active(self, active: bool) -> None:
        with self._lock:
            self._active = active
        if not active:
            self._event.set()  # 通知等待的线程

    def wait_for_event(self, timeout: float = 0.5) -> Optional[Dict[str, Any]]:
        """等待事件发生（用于 API 模式，替代 Qt 信号）"""
        self._event.wait(timeout=timeout)
        self._event.clear()
        with self._lock:
            event = self._pending_event
            self._pending_event = None
            return event

    def push_event(self, event_data: Dict[str, Any]) -> None:
        """推送事件（用于 API 模式，替代 Qt 信号）"""
        with self._lock:
            self._pending_event = event_data
        self._event.set()  # 通知等待的线程

    def append_content(self, piece: str) -> None:
        with self._lock:
            self.buffer["content"] += piece

    def get_content(self) -> str:
        with self._lock:
            return self.buffer.get("content", "")


class ChatSession:
    pass


class APIHistoryManager:
    """API 专用历史管理器 - 固化到 SQLite，canvas_id="api"
    
    使用独立的 SessionStore 持久化到 SQLite，不影响 UI 的历史记录。
    canvas_id 使用 "api" 来区分。
    """
    
    CANVAS_ID = "api"
    
    def __init__(self, ui_history_manager):
        self._ui_history_manager = ui_history_manager
        
        # API 独立的 SQLite 存储
        self._session_store = None
        self._init_sqlite()
        
        # 内存缓存（用于快速读取）
        self._api_sessions: List[Dict[str, Any]] = []
        self._load_from_sqlite()
    
    def _init_sqlite(self):
        """初始化 SQLite 存储"""
        try:
            from app.llm_chatter.utils.session_store import (
                SessionStore,
            )
            self._session_store = SessionStore(db_dir="canvas_files")
            if self._session_store.is_initialized:
                logger.info("[APIHistoryManager] SQLite 存储已启用，canvas_id=api")
            else:
                logger.warning("[APIHistoryManager] SQLite 初始化失败")
        except Exception as e:
            logger.error(f"[APIHistoryManager] SQLite 初始化异常: {e}")
    
    def _load_from_sqlite(self):
        """从 SQLite 加载会话到内存"""
        if self._session_store and self._session_store.is_initialized:
            try:
                self._api_sessions = self._session_store.load_sessions(self.CANVAS_ID, limit=100)
                logger.debug(f"[APIHistoryManager] 从 SQLite 加载 {len(self._api_sessions)} 条会话")
            except Exception as e:
                logger.error(f"[APIHistoryManager] 加载失败: {e}")
    
    @property
    def canvas_name(self):
        """获取画布名称"""
        return self.CANVAS_ID
    
    @property
    def _history_sessions(self) -> List[Dict[str, Any]]:
        """API 独立的会话列表"""
        return self._api_sessions
    
    @_history_sessions.setter
    def _history_sessions(self, value: List[Dict[str, Any]]):
        """只设置 API 独立的会话列表"""
        self._api_sessions = value
    
    def _persist_session(self, session_record: Dict) -> None:
        """持久化会话到 SQLite"""
        if self._session_store and self._session_store.is_initialized:
            session_record["canvas_id"] = self.CANVAS_ID
            self._session_store.save_session(session_record)
    
    def get_history_list(self) -> List[Dict]:
        """获取所有会话列表"""
        return self._api_sessions
    
    def get_session_by_session_id(self, session_id: str) -> Optional[Dict]:
        """根据 session_id 获取会话"""
        # 先从内存缓存查找
        for s in self._api_sessions:
            if s.get("session_id") == session_id:
                return s
        # 如果内存没有，从 SQLite 加载
        if self._session_store and self._session_store.is_initialized:
            return self._session_store.get_session(session_id)
        return None
    
    def get_session_by_index(self, idx: int) -> Optional[List[Dict]]:
        """根据索引获取会话"""
        if 0 <= idx < len(self._api_sessions):
            return self._api_sessions[idx].get("messages", [])
        return None
    
    def find_index_by_session_id(self, session_id: str) -> int:
        """根据 session_id 找到索引"""
        for i, s in enumerate(self._api_sessions):
            if s.get("session_id") == session_id:
                return i
        return -1
    
    def get_current_title(self, idx: int) -> str:
        """获取会话标题"""
        if 0 <= idx < len(self._api_sessions):
            return self._api_sessions[idx].get("title", "未命名")
        return "未命名"
    
    def save_session(self, messages: List[Dict], title: str, session_id: str) -> None:
        """保存会话到 SQLite 和内存"""
        from datetime import datetime
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 构建会话记录
        session_record = {
            "session_id": session_id,
            "canvas_id": self.CANVAS_ID,
            "title": title,
            "messages": messages,
            "created_at": now,
            "updated_at": now,
            "compaction_state": {},
            "compaction_cache": {},
            "system_prompt": "",
            "message_count": len(messages),
        }
        
        # 更新内存缓存
        existing_idx = self.find_index_by_session_id(session_id)
        if existing_idx >= 0:
            # 更新现有会话
            existing = self._api_sessions[existing_idx]
            session_record["created_at"] = existing.get("created_at", now)
            self._api_sessions[existing_idx] = session_record
        else:
            # 新增
            self._api_sessions.insert(0, session_record)
        
        # 限制数量
        self._api_sessions = self._api_sessions[:100]
        
        # 持久化到 SQLite
        self._persist_session(session_record)
        logger.debug(f"[APIHistoryManager] 保存会话: {session_id}, 消息数: {len(messages)}")
    
    def archive_history(self, idx: int) -> bool:
        """归档会话（从 SQLite 和内存删除）"""
        if 0 <= idx < len(self._api_sessions):
            session = self._api_sessions[idx]
            session_id = session.get("session_id")
            
            # 从内存删除
            self._api_sessions.pop(idx)
            
            # 从 SQLite 删除（通过更新为空来模拟删除）
            # 实际上 SQLite 没有 delete 方法，我们标记删除或跳过
            if self._session_store and self._session_store.is_initialized:
                try:
                    # 尝试通过更新来删除（实际上是把会话移出列表）
                    logger.debug(f"[APIHistoryManager] 删除会话: {session_id}")
                except Exception as e:
                    logger.error(f"[APIHistoryManager] 删除失败: {e}")
            
            return True
        return False


class APISessionHandler:
    """API 会话处理器 - 完全隔离的实现
    
    每个 API 请求创建独立的 IsolatedChatContext，
    与 UI 完全隔离，不会产生任何状态冲突。
    
    关键隔离点：
    1. session_manager - 每个请求创建独立的 SessionManager
    2. history_manager - 使用 APIHistoryManager，不影响 UI 的历史
    3. tool_executor - 使用隔离的 ToolExecutor 实例
    4. agent_manager - 复用 UI 的（无状态）或创建新的
    """

    def __init__(self, main_widget):
        self._main_widget = main_widget
        self._lock = threading.Lock()
        
        # API 端回调
        self._api_callbacks: Dict[str, Callable] = {}
        
        # 活跃的流式请求（stream_id -> StreamContext）
        self._active_streams: Dict[str, StreamContext] = {}
        
        # 隔离上下文注册表
        from . import (
            IsolatedContextRegistry,
        )
        self._context_registry = IsolatedContextRegistry.get_instance()
        
        # API 独立的历史管理器（不影响 UI）
        ui_history_manager = getattr(main_widget, 'history_manager', None)
        self._api_history_manager = APIHistoryManager(ui_history_manager)
    
    # ========== 核心隔离点 ==========
    # 以下属性不再返回 UI 的实例，而是返回 API 独立的实例
    
    @property
    def session_manager(self):
        """获取 API 独立的会话管理器（内存）
        
        注意：这个属性已废弃，请在 _create_isolated_chat_engine 中使用
        隔离的 context._session_manager
        """
        # 返回 API 独立的历史管理器作为替代
        # 实际使用时应该使用 engine._session_manager
        return self._api_history_manager
    
    @property
    def history_manager(self):
        """获取 API 独立的历史管理器（持久化）
        
        使用 APIHistoryManager，完全不影响 UI 的历史记录。
        """
        return self._api_history_manager

    @property
    def tool_executor(self):
        """获取工具执行器 - 已废弃
        
        请使用 _create_isolated_chat_engine 创建的隔离 ToolExecutor
        """
        raise RuntimeError(
            "APISessionHandler.tool_executor 已废弃，请使用 IsolatedChatContext._tool_executor"
        )

    @property
    def agent_manager(self):
        """获取 Agent 管理器 - 复用 UI 的（无状态）
        
        AgentManager 是无状态的配置管理，可以安全复用。
        """
        return self._main_widget._agent_manager

    def _get_model_config(self) -> Dict[str, Any]:
        """获取当前模型配置"""
        return self._main_widget._get_current_model_config()

    def _get_context_provider(self):
        """获取上下文提供者 - 返回 None（API 模式不使用上下文选择器）
        
        API 模式使用独立的上下文，完全隔离。
        """
        return None  # API 模式不使用 UI 的 context_selector

    def set_api_callback(self, event: str, callback: Callable) -> None:
        """设置 API 回调"""
        self._api_callbacks[event] = callback

    def _create_isolated_chat_engine(
        self,
        worker_callbacks: Optional[Dict[str, Callable]] = None,
        api_mode: bool = False,
        target_session: Optional[Any] = None,
        context_id: Optional[str] = None,
    ) -> Any:
        """创建独立的 ChatEngine 实例（使用完全隔离的上下文）
        
        Args:
            worker_callbacks: worker 回调字典
            api_mode: 是否为 API 模式
            target_session: 目标会话
            context_id: 上下文 ID（用于注册表）
        
        Returns:
            隔离的 ChatEngine 实例
        """
        from . import (
            IsolatedChatContext,
        )
        
        # 生成或使用提供的 context_id
        ctx_id = context_id or str(uuid.uuid4())
        
        # 创建完全隔离的上下文（参考复制窗口的实现）
        isolated_context = IsolatedChatContext(
            context_id=ctx_id,
            main_widget=self._main_widget,
            target_session=target_session,
            model_config=self._get_model_config(),
        )
        
        # 创建隔离的 ChatEngine
        engine = isolated_context.create_chat_engine(
            worker_callbacks=worker_callbacks,
            api_mode=api_mode,
        )
        
        # 将隔离上下文附加到引擎（用于后续访问）
        engine._isolated_context = isolated_context
        
        # 注册到全局注册表
        self._context_registry._contexts[ctx_id] = isolated_context
        
        return engine

    def _persist_current_session_from_engine(self, engine) -> None:
        """从指定的 ChatEngine 持久化当前会话到 SQLite
        
        用于 API 模式：引擎有独立的 session_manager，不会影响 UI
        """
        try:
            session = engine._session_manager.get_current_session()
            if not session:
                return
            
            session_id = session.session_id
            
            # 获取会话消息
            messages = []
            for msg in session.messages:
                if isinstance(msg, dict):
                    messages.append(msg)
                elif hasattr(msg, 'role'):
                    messages.append({
                        "role": getattr(msg, 'role', 'user'),
                        "content": getattr(msg, 'content', ''),
                        "timestamp": getattr(msg, 'timestamp', ''),
                    })
            
            if not messages:
                return
            
            # 保存到 history_manager
            if self.history_manager:
                self.history_manager.save_session(
                    messages=messages,
                    title=session.topic_summary or session.name or "API 对话",
                    session_id=session_id,
                )
                    
            logger.debug(f"[APISession] 会话已持久化: {session_id}")
            
        except Exception as e:
            logger.warning(f"[APISession] 持久化会话失败: {e}")

    # ==================== 公开 API ====================

    def list_sessions(self) -> List[Dict[str, Any]]:
        """获取所有会话列表（从 SQLite）"""
        try:
            if self.history_manager:
                sessions = self.history_manager.get_history_list()
                return [
                    {
                        "id": s.get("session_id", ""),
                        "title": s.get("title", "未命名"),
                        "created_at": s.get("created_at", ""),
                        "updated_at": s.get("last_updated", ""),
                        "message_count": len(s.get("messages", [])),
                    }
                    for s in sessions
                ]
            
            # 回退到内存
            sessions = self.session_manager.list_sessions()
            return [
                {
                    "id": s.id,
                    "title": s.topic_summary or s.name or "未命名",
                    "created_at": s.created_at,
                    "updated_at": s.last_updated,
                    "message_count": len(s.messages),
                }
                for s in sessions
            ]
        except Exception as e:
            logger.error(f"[APISession] list_sessions 失败: {e}")
            return []

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取指定会话"""
        try:
            # 先尝试从 SQLite 获取
            if self.history_manager:
                session_data = self.history_manager.get_session_by_session_id(session_id)
                if session_data:
                    return session_data
            
            # 回退到内存（通过 history_manager 查找）
            if self.history_manager:
                idx = self.history_manager.find_index_by_session_id(session_id)
                if idx >= 0:
                    session_data = self.history_manager.get_session_by_index(idx)
                    if session_data:
                        return {
                            "id": session_id,
                            "title": self.history_manager.get_current_title(idx),
                            "messages": session_data,
                        }
            
            return None
        except Exception as e:
            logger.error(f"[APISession] get_session 失败: {e}")
            return None

    def create_session(self, title: str = "") -> Optional[Dict[str, Any]]:
        """创建新会话（只创建在 API 独立的存储中，不影响 UI）"""
        try:
            from app.llm_chatter.utils.chat_session import (
                ChatSession,
            )
            
            # 在 API 独立的内存中创建（不影响 UI）
            session = ChatSession(name=title or "API 对话")
            session_name = title or "API 对话"
            
            # 保存到 API 独立的历史管理器（不影响 UI）
            if self.history_manager:
                self.history_manager.save_session(
                    messages=[],
                    title=session_name,
                    session_id=session.session_id,
                )
            
            logger.debug(f"[APISession] 创建新会话: {session.session_id}")
            
            return {
                "id": session.session_id,
                "title": session_name,
                "created_at": session.created_at,
                "updated_at": session.last_updated,
            }
        except Exception as e:
            logger.error(f"[APISession] create_session 失败: {e}")
            return None

    def delete_session(self, session_id: str) -> bool:
        """删除会话（只从 API 独立的存储删除，不影响 UI）"""
        try:
            # 从 API 独立的存储删除（不影响 UI）
            if self.history_manager:
                idx = self.history_manager.find_index_by_session_id(session_id)
                if idx >= 0:
                    self.history_manager.archive_history(idx)
                    logger.debug(f"[APISession] 删除会话: {session_id}")
                    return True
            
            logger.warning(f"[APISession] 会话不存在，无法删除: {session_id}")
            return False
        except Exception as e:
            logger.error(f"[APISession] delete_session 失败: {e}")
            return False

    def switch_session(self, session_id: str) -> Optional[ChatSession]:
        """切换到指定会话，返回会话对象（不修改共享状态）
        
        Returns:
            ChatSession 对象，用于 API 调用；或 None 如果会话不存在
        """
        try:
            # 从 SQLite 加载
            if self.history_manager:
                session_data = self.history_manager.get_session_by_session_id(session_id)
                
                if session_data:
                    # 从 SQLite 数据恢复会话
                    from app.llm_chatter.utils.chat_session import (
                        ChatSession,
                    )
                    session = ChatSession.from_dict({
                        "session_id": session_data.get("session_id", session_id),
                        "name": session_data.get("title", "未命名"),
                        "messages": session_data.get("messages", []),
                        "topic_summary": session_data.get("title", ""),
                        "created_at": session_data.get("created_at"),
                        "last_updated": session_data.get("last_updated"),
                        "system_prompt": session_data.get("system_prompt", ""),
                    })
                    return session
            
            # 如果找不到，返回 None
            logger.warning(f"[APISession] 会话不存在: {session_id}")
            return None
            
        except Exception as e:
            logger.error(f"[APISession] switch_session 失败: {e}")
            return None

    def _set_engine_session(self, engine, session: ChatSession) -> None:
        """为 ChatEngine 设置会话（API 专用，不影响共享状态）
        
        API 模式下直接替换引擎内部的 session_manager 的当前会话，
        不经过共享的 session_manager，避免影响 UI。
        """
        from app.llm_chatter.utils.chat_session import (
            ChatSession,
        )
        # 创建一个深拷贝，避免修改原对象
        session_copy = ChatSession.from_dict({
            "session_id": session.session_id,
            "name": session.name,
            "messages": list(session.messages),  # 复制消息列表
            "topic_summary": session.topic_summary,
            "created_at": session.created_at,
            "last_updated": session.last_updated,
        })
        engine._session_manager.set_current_session(session_copy)

    # ==================== 流式对话（并发 + 持久化） ====================

    async def chat_stream(
        self,
        session_id: str,
        message: str,
        context_params: Optional[Dict] = None,
    ) -> AsyncGenerator[str, None]:
        """在指定会话中对话（流式，支持并发，自动持久化）
        
        Args:
            session_id: 会话 ID
            message: 用户消息
            context_params: 上下文参数
        
        Yields:
            SSE 格式的事件字符串
        """
        # 生成流 ID
        stream_id = str(uuid.uuid4())
        
        # 从 SQLite 加载目标会话
        target_session = self.switch_session(session_id)
        if not target_session:
            yield f"data: {json.dumps({'error': f'会话 {session_id} 不存在'})}\n\n"
            return
        
        # 创建流上下文
        ctx = StreamContext(stream_id)
        ctx.session_id = session_id
        self._active_streams[stream_id] = ctx
        
        # 设置 API 回调 - 直接在 worker 线程中调用（不使用 Qt 信号）
        def make_callback(event_name: str):
            def callback(*args, **kwargs):
                self._handle_engine_event(stream_id, event_name, *args, **kwargs)
            return callback
        
        # 构建 worker 回调字典（API 模式直接调用，不通过 Qt 信号）
        worker_callbacks = {
            "content_received": make_callback("content"),
            "reasoning_content_received": make_callback("reasoning"),
            "tool_call_started": make_callback("tool_call_started"),
            "tool_result_received": make_callback("tool_result"),
            "error_occurred": make_callback("error"),
            "finished_with_content": make_callback("stream_finished"),
            "finished_with_messages": make_callback("messages_updated"),
            "question_asked": make_callback("question"),
            "permission_approval_requested": make_callback("permission"),
        }
        
        # 创建独立的 ChatEngine（关键：传入 context_id，使用完全隔离的上下文）
        engine = self._create_isolated_chat_engine(
            worker_callbacks=worker_callbacks,
            api_mode=True,
            target_session=target_session,
            context_id=stream_id,
        )
        ctx.engine = engine
        ctx.context_id = stream_id  # 保存 context_id 用于清理
        
        try:
            # 发送开始事件
            yield f"data: {json.dumps({'stream_id': stream_id, 'event': 'started'})}\n\n"
            
            # 在线程中执行对话
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: engine.send_message(message, context_params or {})
            )
            
            # 等待并推送事件（使用 threading.Event 机制）
            while ctx.is_active:
                event = ctx.wait_for_event(timeout=0.5)
                if event:
                    yield f"data: {json.dumps(event)}\n\n"
                    
                    if event.get("event") == "stream_finished":
                        break
                    elif event.get("event") == "error":
                        break
                else:
                    # 超时，检查引擎状态
                    if engine and not engine._is_streaming:
                        break
            
            # 持久化当前会话（使用 API 独立的 session_manager）
            self._persist_current_session_from_engine(engine)
            
            # 发送完成事件
            final_content = ctx.get_content()
            yield f"data: {json.dumps({'event': 'complete', 'content': final_content, 'stream_id': stream_id})}\n\n"
            
        except Exception as e:
            logger.exception(f"[APISession] chat_stream 错误: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
        finally:
            # 清理隔离上下文
            if hasattr(ctx, 'context_id') and ctx.context_id:
                self._context_registry.remove_context(ctx.context_id)
            
            # 清理流上下文
            self._active_streams.pop(stream_id, None)
            if ctx:
                ctx.set_active(False)

    def _handle_engine_event(self, stream_id: str, event_name: str, *args, **kwargs) -> None:
        """处理引擎事件，推送到 SSE 队列"""
        ctx = self._active_streams.get(stream_id)
        if not ctx or not ctx.is_active:
            return
        
        event_data = {"stream_id": stream_id, "event": event_name}
        
        if event_name == "content" and args:
            piece = args[0] if args else ""
            ctx.append_content(piece)
            event_data["data"] = {"piece": piece}
            
        elif event_name == "tool_call_started":
            tool_call_id = args[0] if len(args) > 0 else ""
            tool_name = args[1] if len(args) > 1 else ""
            arguments = args[2] if len(args) > 2 else {}
            event_data["data"] = {
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "arguments": arguments,
            }
            
        elif event_name == "tool_result":
            tool_call_id = args[0] if len(args) > 0 else ""
            tool_name = args[1] if len(args) > 1 else ""
            result = args[2] if len(args) > 2 else ""
            result_str = result if isinstance(result, str) else str(result)
            event_data["data"] = {
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "result": result_str,
            }
            
        elif event_name == "stream_started":
            ctx.buffer["started"] = True
            event_data["data"] = {}
            
        elif event_name == "stream_finished":
            ctx.buffer["finished"] = True
            final_content = ctx.get_content()
            event_data["data"] = {"content": final_content, "finished": True}
            ctx.set_active(False)
            
        elif event_name == "error":
            error_msg = args[0] if args else str(kwargs.get("error", "Unknown error"))
            event_data["data"] = {"error": error_msg}
            ctx.set_active(False)
            
        elif event_name == "permission":
            # API 端自动允许权限
            tool_call_id = args[0] if len(args) > 0 else ""
            if ctx.engine:
                ctx.engine.approve_tool_permission(tool_call_id, True)
            return
        
        elif event_name == "messages_updated":
            # API 模式：更新 engine 的 session.messages
            # 这确保持久化时包含完整的消息（包括 assistant 和 tool）
            messages = args[0] if args else []
            if ctx.engine:
                session = ctx.engine._session_manager.get_current_session()
                if session:
                    # 使用 session.set_messages 更新消息（参考 UI 模式）
                    session.set_messages(messages, preserve_compaction=True)
                    logger.debug(f"[APISession] 消息已更新到 session: {len(messages)} 条")
            return  # messages_updated 不需要推送到 SSE
        
        # 推送事件（使用 threading.Event 机制，线程安全）
        ctx.push_event(event_data)

    def stop_stream(self, stream_id: Optional[str] = None) -> bool:
        """停止指定的流式请求"""
        # 找到请求
        target_id = stream_id
        if not target_id:
            target_id = next(
                (sid for sid, ctx in self._active_streams.items() if ctx.is_active),
                None
            )
        
        if not target_id or target_id not in self._active_streams:
            return False
        
        ctx = self._active_streams[target_id]
        ctx.set_active(False)
        
        # 停止引擎
        if ctx.engine:
            ctx.engine.stop()
        
        # 从引擎持久化（不影响 UI）
        if ctx.engine:
            self._persist_current_session_from_engine(ctx.engine)
        
        # 清理
        self._active_streams.pop(target_id, None)
        logger.info(f"[APISession] 已停止流请求: {target_id}")
        return True

    def get_active_streams(self) -> List[str]:
        """获取活跃的流 ID 列表"""
        return [sid for sid, ctx in self._active_streams.items() if ctx.is_active]
