# -*- coding: utf-8 -*-
"""
LLM Chatter HTTP API 服务
提供远程调用接口，复用 UI 对话逻辑

核心设计：
- API 调用直接复用 UI 的 ChatEngine 和 SessionManager
- 通过 SSE 流式推送响应
- 会话管理完全复用

接口列表：
- GET  /health                      - 健康检查
- GET  /docs                        - 打开 API 文档页面

会话管理：
- GET  /sessions                    - 获取所有会话列表
- POST /sessions                    - 创建新会话
- GET  /sessions/{id}               - 获取指定会话详情
- DELETE /sessions/{id}             - 删除会话

对话接口：
- POST /sessions/{id}/chat/stream    - 在指定会话中对话（流式 SSE）
- POST /chat/stop                   - 停止当前流式请求
"""

import asyncio
import json
import threading
from typing import Optional, Dict, Any, List, Callable

# 注册 QProcess::ExitStatus 元类型，解决跨线程信号连接问题
# PyInstaller 打包后必须注册，否则 QProcess::finished 信号跨线程连接会失败
from PyQt5.QtCore import QProcess
try:
    qRegisterMetaType("QProcess::ExitStatus")
except NameError:
    # PyQt5 中 qRegisterMetaType 是内置函数，不需要导入
    pass

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger

# 全局服务实例
_llm_api_service: Optional["LLMAPIService"] = None
_api_starting = False
_api_start_lock = threading.Lock()


def get_llm_api_service() -> "LLMAPIService":
    """获取 LLM API 服务实例（单例）"""
    global _llm_api_service, _api_starting
    if _llm_api_service is None:
        with _api_start_lock:
            if _llm_api_service is None:
                _llm_api_service = LLMAPIService()
    return _llm_api_service


def ensure_service_running() -> "LLMAPIService":
    """确保服务正在运行，自动启动"""
    global _api_starting
    service = get_llm_api_service()
    if not service._running:
        with _api_start_lock:
            if not service._running and not _api_starting:
                _api_starting = True
                service.start(background=True)
                _api_starting = False
    return service


class LLMAPIService:
    """LLM API 服务（单例）
    
    复用 UI 对话逻辑的完整实现，包括：
    - ChatEngine（对话引擎）
    - SessionManager（会话管理）
    - ToolExecutor（工具执行）
    - AgentManager（Agent 管理）
    """

    # 会话处理器引用
    _session_handler: Optional[Any] = None

    @classmethod
    def set_session_handler(cls, handler):
        """设置会话处理器"""
        cls._session_handler = handler

    @classmethod
    def get_session_handler(cls):
        """获取会话处理器"""
        return cls._session_handler

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.app = FastAPI(
            title="LLM Chatter API",
            description="复用 UI 对话逻辑的远程 API 接口",
            version="2.0.0",
        )
        self.server = None
        self._running = False
        self._setup_routes()

    def _setup_routes(self):
        """设置所有路由"""
        
        # ==================== 健康检查 ====================
        @self.app.get("/health")
        async def health_check():
            """健康检查"""
            handler = self.get_session_handler()
            return {
                "status": "ok" if self._running else "stopped",
                "service": "llm_chatter_api",
                "version": "2.0.0",
                "running": self._running,
                "address": f"http://{self.host}:{self.port}" if self._running else None,
                "ui_linked": handler is not None,
            }

        # ==================== 会话管理 ====================
        @self.app.get("/sessions", response_model=Dict[str, Any])
        async def list_sessions():
            """获取所有会话列表"""
            handler = self.get_session_handler()
            if not handler:
                raise HTTPException(
                    status_code=503,
                    detail="会话处理器未初始化，请确保 LLMChatter 窗口已打开"
                )
            
            sessions = handler.list_sessions()
            return {"success": True, "sessions": sessions}

        @self.app.post("/sessions", response_model=Dict[str, Any])
        async def create_session(request: Optional[Dict[str, Any]] = None):
            """创建新会话
            
            Request Body (可选):
                {"title": "会话标题"}
            """
            handler = self.get_session_handler()
            if not handler:
                raise HTTPException(
                    status_code=503,
                    detail="会话处理器未初始化"
                )
            
            title = ""
            if request:
                title = request.get("title", "")
            
            session = handler.create_session(title=title)
            if not session:
                raise HTTPException(status_code=500, detail="创建会话失败")
            
            return {"success": True, "session": session}

        @self.app.get("/sessions/{session_id}", response_model=Dict[str, Any])
        async def get_session(session_id: str):
            """获取指定会话详情"""
            handler = self.get_session_handler()
            if not handler:
                raise HTTPException(status_code=503, detail="会话处理器未初始化")
            
            session = handler.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")
            
            return {"success": True, "session": session}

        @self.app.delete("/sessions/{session_id}", response_model=Dict[str, Any])
        async def delete_session(session_id: str):
            """删除会话"""
            handler = self.get_session_handler()
            if not handler:
                raise HTTPException(status_code=503, detail="会话处理器未初始化")
            
            if handler.delete_session(session_id):
                return {"success": True, "message": f"会话 {session_id} 已删除"}
            else:
                raise HTTPException(status_code=500, detail="删除会话失败")

        # ==================== 对话接口（核心，支持并发） ====================
        @self.app.post("/sessions/{session_id}/chat/stream")
        async def chat_stream(session_id: str, request: Dict[str, Any]):
            """在指定会话中对话（流式 SSE，支持并发）
            
            特性：
            - 每个请求创建独立的 ChatEngine 实例，并发安全
            - 自动复用 UI 的 ToolExecutor、SessionManager、AgentManager
            - 会话自动保存
            
            Request Body:
            {
                "message": "用户消息",
                "context": {}  // 可选，上下文参数
            }
            
            SSE 事件：
            - started: 流开始，包含 stream_id
            - content: 收到的内容片段
            - tool_call_started: 工具调用开始
            - tool_result: 工具执行结果
            - error: 错误
            - stream_finished: 流结束
            - complete: 完整响应
            """
            handler = self.get_session_handler()
            if not handler:
                raise HTTPException(
                    status_code=503,
                    detail="会话处理器未初始化"
                )

            message = request.get("message", "")
            if not message:
                raise HTTPException(status_code=400, detail="message 是必填项")

            context_params = request.get("context", {})

            async def event_generator():
                try:
                    async for event in handler.chat_stream(
                        session_id=session_id,
                        message=message,
                        context_params=context_params,
                    ):
                        yield event
                except Exception as e:
                    logger.exception(f"[API] chat_stream 错误: {e}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        @self.app.post("/chat/stop")
        async def stop_chat(request: Optional[Dict[str, Any]] = None):
            """停止当前流式请求"""
            handler = self.get_session_handler()
            if not handler:
                raise HTTPException(status_code=503, detail="会话处理器未初始化")
            
            stream_id = request.get("stream_id") if request else None
            handler.stop_stream(stream_id)
            
            return {"success": True, "message": "已停止流式请求"}

        # ==================== 保留旧接口（简单测试用） ====================
        @self.app.get("/providers")
        async def get_providers():
            """获取所有服务商列表（兼容旧接口）"""
            handler = self.get_session_handler()
            if handler and handler._main_widget:
                try:
                    # 从 UI 获取服务商列表
                    config_popup = handler._main_widget._settings_popup
                    if config_popup and hasattr(config_popup, '_providers'):
                        providers = config_popup._providers
                        return {"success": True, "providers": providers}
                except Exception as e:
                    logger.error(f"[API] get_providers 失败: {e}")
            
            return {"success": True, "providers": []}

        @self.app.get("/config")
        async def get_config():
            """获取当前 LLM 配置（自动使用 LLMChatter 选中配置）"""
            handler = self.get_session_handler()
            if handler and handler._main_widget:
                try:
                    config = handler._main_widget._get_current_model_config()
                    if config:
                        safe_config = {**config}
                        if safe_config.get("API_KEY"):
                            safe_config["API_KEY"] = "***" + safe_config["API_KEY"][-4:]
                        return {"config": safe_config}
                except Exception as e:
                    logger.error(f"[API] get_config 失败: {e}")
            
            raise HTTPException(status_code=503, detail="配置不可用")

    def start(self, background: bool = True):
        """启动服务"""
        if self._running:
            logger.info("[LLMAPI] 服务已在运行")
            return

        if background:
            self._running = True
            thread = threading.Thread(target=self._run_server, daemon=True)
            thread.start()
            logger.info(f"[LLMAPI] 服务已启动: http://{self.host}:{self.port}")
            logger.info("[LLMAPI] API 文档: http://localhost:{}/docs".format(self.port))
        else:
            self._run_server()

    def _run_server(self):
        """运行服务器"""
        import uvicorn
        
        # 强制单进程模式，避免 PyInstaller 打包后 uvicorn 启动多 worker 进程
        # 导致 QProcess::ExitStatus 跨线程错误
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
            workers=1,                    # 强制单 worker 进程
            loop="asyncio",               # 强制使用 asyncio 循环
            lifespan="off",               # 禁用 lifespan 事件，避免启动时的进程检测
        )
        
        # 禁用 uvicorn 的 autoreload 等可能创建子进程的功能
        config.autoreload = False
        config.reload = False
        config.use_colors = False
        
        server = uvicorn.Server(config)
        self._running = True
        
        # 确保在主线程的事件循环中运行
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(server.serve())
        except Exception as e:
            logger.error(f"[LLMAPI] Server error: {e}")
        finally:
            self._running = False

    def stop(self):
        """停止服务"""
        self._running = False
        logger.info("[LLMAPI] 服务已停止")


def start_llm_api_service(host: str = "0.0.0.0", port: int = 8765):
    """启动 LLM API 服务（确保单例）"""
    service = get_llm_api_service()
    service.host = host
    service.port = port
    service.start(background=True)
    return service


def stop_llm_api_service():
    """停止 LLM API 服务"""
    global _llm_api_service
    if _llm_api_service:
        _llm_api_service.stop()
        _llm_api_service = None


def is_service_running() -> bool:
    """检查服务是否在运行"""
    global _llm_api_service
    return _llm_api_service is not None and _llm_api_service._running


def open_docs():
    """打开 API 文档页面"""
    if _llm_api_service and _llm_api_service._running:
        import webbrowser
        webbrowser.open(f"http://localhost:{_llm_api_service.port}/docs")
    else:
        start_llm_api_service()
        import time
        time.sleep(1)
        import webbrowser
        webbrowser.open(f"http://localhost:{_llm_api_service.port}/docs")
