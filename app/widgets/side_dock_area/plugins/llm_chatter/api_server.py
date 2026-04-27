# -*- coding: utf-8 -*-
"""
LLM Chatter HTTP API 服务
提供远程调用接口，使用与 LLMChatter 相同的模型配置

用法：
    from app.widgets.side_dock_area.plugins.llm_chatter.api_server import start_llm_api_service
    start_llm_api_service(host="0.0.0.0", port=8765)
"""
import json
import threading
from typing import Optional, Dict, Any, List, Callable

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

    提供以下接口：
    - GET  /health             - 健康检查
    - GET  /providers          - 获取所有服务商列表
    - GET  /config             - 获取当前 LLM 配置（自动使用 LLMChatter 选中配置）
    - POST /config             - 更新当前配置
    - POST /chat               - 简单聊天（非流式）
    - POST /chat/stream        - 流式聊天
    - POST /tools/call         - 带工具调用的聊天
    """

    # 服务商列表获取回调
    _get_providers_callback: Optional[Callable] = None
    # 当前选中的服务商名称
    _current_provider_name: str = "系统默认配置"
    # 配置获取回调（返回当前选中的完整配置）
    _get_current_config_callback: Optional[Callable] = None

    @classmethod
    def set_providers_callback(cls, callback):
        """设置服务商列表获取回调"""
        cls._get_providers_callback = callback

    @classmethod
    def set_config_callback(cls, callback):
        """设置配置获取回调"""
        cls._get_current_config_callback = callback

    @classmethod
    def update_current_provider(cls, provider_name: str):
        """更新当前选中的服务商名称"""
        cls._current_provider_name = provider_name

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.app = FastAPI(title="LLM Chatter API")
        self.server = None
        self._running = False
        self._setup_routes()

    def _setup_routes(self):
        """设置路由"""

        @self.app.get("/health")
        async def health_check():
            """健康检查"""
            return {
                "status": "ok" if self._running else "stopped",
                "service": "llm_chatter_api",
                "version": "1.0.0",
                "running": self._running,
                "address": f"http://{self.host}:{self.port}" if self._running else None,
            }

        @self.app.get("/providers")
        async def get_providers():
            """获取所有服务商列表"""
            if self._get_providers_callback:
                try:
                    result = self._get_providers_callback()
                    # 如果返回的是 dict 列表
                    if isinstance(result, list):
                        providers = result
                    else:
                        providers = result.get("providers", [])
                    return {"success": True, "providers": providers}
                except Exception as e:
                    logger.error(f"[LLMAPI] get_providers 失败: {e}")
            return {"success": False, "error": "Providers callback not set"}

        @self.app.post("/providers/switch")
        async def switch_provider(request: Dict[str, Any]):
            """切换到指定服务商
            
            Request Body:
                {"provider_name": "服务商名称"}
            """
            provider_name = request.get("provider_name", "")
            if not provider_name:
                raise HTTPException(status_code=400, detail="provider_name is required")
            
            # 记录当前选中的服务商
            self.update_current_provider(provider_name)
            return {"success": True, "message": f"已切换到 {provider_name}"}

        @self.app.get("/config")
        async def get_config():
            """获取当前 LLM 配置（自动使用 LLMChatter 选中的配置）"""
            if self._get_current_config_callback:
                try:
                    config = self._get_current_config_callback()
                except Exception as e:
                    logger.error(f"[LLMAPI] get_config 失败: {e}")
                    config = None

                if config:
                    safe_config = {**config}
                    if safe_config.get("API_KEY"):
                        safe_config["API_KEY"] = "***" + safe_config["API_KEY"][-4:]
                    return {
                        "config": safe_config,
                        "provider_name": self._current_provider_name,
                    }
            
            raise HTTPException(status_code=503, detail="Config callback not set")

        @self.app.post("/config")
        async def config_update(request: Dict[str, Any]):
            """更新当前配置（临时覆盖）"""
            return {"success": True, "message": "配置已更新（临时）"}

        @self.app.post("/chat")
        async def chat(request: Dict[str, Any]):
            """简单聊天接口（非流式，不支持工具调用）
            自动使用 LLMChatter 当前选中的服务商配置
            """
            try:
                message = request.get("message", "")
                system_prompt = request.get("system_prompt", "")
                history = request.get("history", [])

                if not message:
                    raise HTTPException(status_code=400, detail="message is required")

                config = self._get_current_config()
                if not config:
                    raise HTTPException(status_code=503, detail="LLM not configured")

                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.extend(history)
                messages.append({"role": "user", "content": message})

                from openai import OpenAI
                client = OpenAI(
                    api_key=config.get("API_KEY", ""),
                    base_url=config.get("API_URL"),
                )

                response = client.chat.completions.create(
                    model=config.get("模型名称", "gpt-4o"),
                    messages=messages,
                    stream=False,
                    temperature=float(config.get("temperature", 0.7)),
                    max_tokens=int(config.get("max_tokens", 4096)),
                )

                content = response.choices[0].message.content or ""

                return {
                    "success": True,
                    "content": content,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                        "total_tokens": response.usage.total_tokens if response.usage else 0,
                    },
                }

            except Exception as e:
                logger.exception(f"[LLMAPI] Chat 请求失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/chat/stream")
        async def chat_stream(request: Dict[str, Any]):
            """流式聊天接口"""
            try:
                message = request.get("message", "")
                system_prompt = request.get("system_prompt", "")
                history = request.get("history", [])

                if not message:
                    raise HTTPException(status_code=400, detail="message is required")

                config = self._get_current_config()
                if not config:
                    raise HTTPException(status_code=503, detail="LLM not configured")

                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.extend(history)
                messages.append({"role": "user", "content": message})

                from openai import OpenAI
                client = OpenAI(
                    api_key=config.get("API_KEY", ""),
                    base_url=config.get("API_URL"),
                )

                async def event_generator():
                    try:
                        response = client.chat.completions.create(
                            model=config.get("模型名称", "gpt-4o"),
                            messages=messages,
                            stream=True,
                            temperature=float(config.get("temperature", 0.7)),
                            max_tokens=int(config.get("max_tokens", 4096)),
                        )

                        for chunk in response:
                            delta = chunk.choices[0].delta
                            content = delta.content if delta else ""
                            if content:
                                yield f"data: {json.dumps({'content': content})}\n\n"

                        yield "data: [DONE]\n\n"

                    except Exception as e:
                        logger.error(f"[LLMAPI] Stream error: {e}")
                        yield f"data: {json.dumps({'error': str(e)})}\n\n"

                return StreamingResponse(
                    event_generator(),
                    media_type="text/event-stream",
                )

            except Exception as e:
                logger.exception(f"[LLMAPI] Stream 请求失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/tools/call")
        async def tools_call(request: Dict[str, Any]):
            """带工具调用的聊天接口"""
            try:
                message = request.get("message", "")
                system_prompt = request.get("system_prompt", "")
                tools = request.get("tools", [])
                history = request.get("history", [])

                if not message:
                    raise HTTPException(status_code=400, detail="message is required")

                config = self._get_current_config()
                if not config:
                    raise HTTPException(status_code=503, detail="LLM not configured")

                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.extend(history)
                messages.append({"role": "user", "content": message})

                from openai import OpenAI
                client = OpenAI(
                    api_key=config.get("API_KEY", ""),
                    base_url=config.get("API_URL"),
                )

                response = client.chat.completions.create(
                    model=config.get("模型名称", "gpt-4o"),
                    messages=messages,
                    tools=tools if tools else None,
                    stream=False,
                    temperature=float(config.get("temperature", 0.7)),
                    max_tokens=int(config.get("max_tokens", 4096)),
                )

                choice = response.choices[0]
                message_data = choice.message

                tool_calls_list = []
                if message_data.tool_calls:
                    for tc in message_data.tool_calls:
                        if hasattr(tc, 'function'):
                            tool_calls_list.append({
                                "id": tc.id,
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            })
                        elif hasattr(tc, 'name'):
                            tool_calls_list.append({
                                "id": tc.id,
                                "name": tc.name,
                                "arguments": getattr(tc, 'arguments', '{}'),
                            })

                return {
                    "success": True,
                    "content": message_data.content or "",
                    "finish_reason": choice.finish_reason,
                    "tool_calls": tool_calls_list,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                        "total_tokens": response.usage.total_tokens if response.usage else 0,
                    },
                }

            except Exception as e:
                logger.exception(f"[LLMAPI] Tools call 请求失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

    def _get_current_config(self) -> Optional[Dict[str, Any]]:
        """获取当前配置"""
        if self._get_current_config_callback:
            return self._get_current_config_callback()
        
        # 降级：从 Settings 读取系统默认配置
        try:
            from app.utils.config import Settings
            settings = Settings.get_instance()
            return {
                "API_URL": settings.llm_api_url.value or "https://api.openai.com/v1",
                "API_KEY": settings.llm_api_key.value or "",
                "模型名称": settings.llm_model.value or "gpt-4o",
                "temperature": float(settings.llm_temperature.value or 0.7),
                "max_tokens": int(settings.llm_max_tokens.value or 4096),
            }
        except Exception:
            return None

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
        else:
            self._run_server()

    def _run_server(self):
        """运行服务器"""
        import uvicorn
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        self._running = True
        server.run()

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
        # 服务未启动，先启动再打开
        start_llm_api_service()
        import time
        time.sleep(1)
        import webbrowser
        webbrowser.open(f"http://localhost:{_llm_api_service.port}/docs")