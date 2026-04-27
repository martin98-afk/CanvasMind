# -*- coding: utf-8 -*-
"""
API 会话处理器 - 复用 UI 对话逻辑，支持并发和持久化
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


class APISessionHandler:
    """API 会话处理器（支持并发和持久化）
    
    特性：
    - 每个请求创建独立的 ChatEngine 实例
    - 共享 UI 的 session_manager、tool_executor、agent_manager
    - 自动持久化到 SQLite（通过 history_manager）
    - SSE 流式响应
    """

    def __init__(self, main_widget):
        self._main_widget = main_widget
        self._lock = threading.Lock()
        
        # API 端回调
        self._api_callbacks: Dict[str, Callable] = {}
        
        # 活跃的流式请求（stream_id -> StreamContext）
        self._active_streams: Dict[str, StreamContext] = {}

    @property
    def session_manager(self):
        """获取会话管理器（内存）"""
        return self._main_widget.session_manager

    @property
    def history_manager(self):
        """获取历史管理器（持久化）"""
        return self._main_widget.history_manager

    @property
    def tool_executor(self):
        """获取工具执行器"""
        return self._main_widget._tool_executor

    @property
    def agent_manager(self):
        """获取 Agent 管理器"""
        return self._main_widget._agent_manager

    def _get_model_config(self) -> Dict[str, Any]:
        """获取当前模型配置"""
        return self._main_widget._get_current_model_config()

    def _get_context_provider(self):
        """获取上下文提供者"""
        return self._main_widget.context_selector

    def set_api_callback(self, event: str, callback: Callable) -> None:
        """设置 API 回调"""
        self._api_callbacks[event] = callback

    def _create_isolated_chat_engine(
        self,
        worker_callbacks: Optional[Dict[str, Callable]] = None,
        api_mode: bool = False,
    ) -> Any:
        """创建独立的 ChatEngine 实例
        
        Args:
            worker_callbacks: worker 回调字典（API 模式直接调用，不通过 Qt 信号）
            api_mode: 是否为 API 模式（API 模式下直接调用回调，跳过 Qt 信号）
        """
        from app.widgets.side_dock_area.plugins.llm_chatter.core.chat_engine import (
            ChatEngine,
        )
        
        engine = ChatEngine(
            session_manager=self.session_manager,
            get_model_config=self._get_model_config,
            get_context_provider=self._get_context_provider,
            tool_executor=self.tool_executor,
            agent_manager=self.agent_manager,
            get_chat_cards=None,
            get_memory_context=getattr(self._main_widget, '_get_memory_context', None),
            worker_signal_callbacks=worker_signal_callbacks,
        )
        
        return engine

    def _persist_current_session(self) -> None:
        """持久化当前会话到 SQLite"""
        try:
            session = self.session_manager.get_current_session()
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
        """创建新会话（同时在内存和 SQLite 中创建）"""
        try:
            # 在内存中创建
            session = self.session_manager.create_new_session()
            session_name = title or "API 对话"
            if title:
                session.name = title
            
            # 持久化到 SQLite（即使没有消息也要创建记录）
            if self.history_manager:
                session_record = {
                    "session_id": session.session_id,
                    "title": session_name,
                    "messages": [],
                    "created_at": session.created_at,
                    "last_updated": session.last_updated,
                    "compaction_state": {},
                    "compaction_cache": {},
                    "system_prompt": "",
                    "canvas_id": self.history_manager.canvas_name,
                }
                
                # 直接添加到列表开头
                self.history_manager._history_sessions.insert(0, session_record)
                self.history_manager._history_sessions = self.history_manager._history_sessions[:100]
                
                # 持久化
                self.history_manager._persist_session(session_record)
            
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
        """删除会话（同时从内存和 SQLite 删除）"""
        try:
            # 从 SQLite 删除（通过 session_id 找到 index）
            if self.history_manager:
                idx = self.history_manager.find_index_by_session_id(session_id)
                if idx >= 0:
                    self.history_manager.archive_history(idx)
            
            # 从内存删除（通过 index）
            # 需要先找到 index
            if self.history_manager:
                idx = self.history_manager.find_index_by_session_id(session_id)
                if idx >= 0:
                    self.session_manager.delete_session(idx)
            
            return True
        except Exception as e:
            logger.error(f"[APISession] delete_session 失败: {e}")
            return False

    def switch_session(self, session_id: str) -> bool:
        """切换到指定会话"""
        try:
            # 从 SQLite 加载
            if self.history_manager:
                session_data = self.history_manager.get_session_by_session_id(session_id)
                
                if session_data:
                    # 从 SQLite 数据恢复会话
                    from app.widgets.side_dock_area.plugins.llm_chatter.utils.chat_session import (
                        ChatSession,
                    )
                    session = ChatSession.from_dict({
                        "session_id": session_data.get("session_id", session_id),
                        "name": session_data.get("title", "未命名"),
                        "messages": session_data.get("messages", []),
                        "topic_summary": session_data.get("title", ""),
                        "created_at": session_data.get("created_at"),
                        "last_updated": session_data.get("last_updated"),
                    })
                    self.session_manager.set_current_session(session)
                    
                    # 关键修复：同步更新 UI 的 _current_session_id
                    self._main_widget._current_session_id = session.session_id
                    
                    # 同步工具执行器的会话上下文
                    if self._main_widget._tool_executor:
                        self._main_widget._tool_executor.set_session_context(session.session_id)
                    
                    return True
            
            # 如果找不到，返回 False
            logger.warning(f"[APISession] 会话不存在: {session_id}")
            return False
            
        except Exception as e:
            logger.error(f"[APISession] switch_session 失败: {e}")
            return False

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
        
        # 切换到指定会话（会从 SQLite 加载）
        if not self.switch_session(session_id):
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
            "tool_call_started": make_callback("tool_call_started"),
            "tool_result_received": make_callback("tool_result"),
            "error_occurred": make_callback("error"),
            "finished_with_content": make_callback("stream_finished"),
            "question_asked": make_callback("question"),
            "permission_approval_requested": make_callback("permission"),
        }
        
        # 创建独立的 ChatEngine（关键：隔离并发，并传入回调）
        # 传入 _api_mode=True 和 worker_callbacks，让 ChatEngine 直接调用回调
        engine = self._create_isolated_chat_engine(
            worker_callbacks=worker_callbacks,
            api_mode=True
        )
        ctx.engine = engine
        
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
            
            # 持久化当前会话
            self._persist_current_session()
            
            # 发送完成事件
            final_content = ctx.get_content()
            yield f"data: {json.dumps({'event': 'complete', 'content': final_content, 'stream_id': stream_id})}\n\n"
            
        except Exception as e:
            logger.exception(f"[APISession] chat_stream 错误: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
        finally:
            # 清理
            self._active_streams.pop(stream_id, None)
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
        
        # 先持久化再清理
        self._persist_current_session()
        
        # 清理
        self._active_streams.pop(target_id, None)
        logger.info(f"[APISession] 已停止流请求: {target_id}")
        return True

    def get_active_streams(self) -> List[str]:
        """获取活跃的流 ID 列表"""
        return [sid for sid, ctx in self._active_streams.items() if ctx.is_active]
