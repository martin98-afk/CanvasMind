# -*- coding: utf-8 -*-
import socket
import threading
from typing import Callable, Dict
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from app.components.base import PropertyType
from app.widgets.side_dock_area.plugins.canvas_execution_records.execution_manager import ExecutionManager
from app.trigger_plugins.base_trigger import BaseTriggerManager, BaseTriggerPlugin


class WebhookManager(BaseTriggerManager):
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(WebhookManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, host="0.0.0.0", port=5000):
        if self._initialized:
            return
        # 初始化基类
        super().__init__("Webhook")

        self.app = FastAPI(title="NodeGraph Webhook Server")
        self.host = host
        self.port = port

        # self.registry 用于存放路径到回调的映射
        self.registry: Dict[str, Callable] = {}
        self.execution_manager = ExecutionManager()

        self._setup_routes()
        self._server_thread = None
        self._initialized = True

    def _setup_routes(self):
        """配置 FastAPI 路由逻辑"""

        @self.app.get("/health")
        async def health_check():
            return {"status": "ok", "active_canvases": list(self.canvas_mapping.keys())}

        @self.app.get("/api/v1/canvases/{canvas_name}/triggers")
        async def get_triggers_by_canvas(canvas_name: str):
            """获取指定画布下注册的所有 Webhook 触发器及其 Endpoint"""
            # 从基类的 canvas_mapping 中获取该画布下的所有 node_id
            node_ids = self.canvas_mapping.get(canvas_name, [])

            triggers_info = []
            node_to_endpoint = getattr(self, '_node_to_endpoint', {})

            for node_id in node_ids:
                # 获取对应的 Webhook 路径
                endpoint = node_to_endpoint.get(node_id)
                if endpoint:
                    triggers_info.append({
                        "node_id": node_id,
                        "endpoint": endpoint,
                        "url": f"http://{self.host}:{self.port}{endpoint}"
                    })

            return {
                "canvas_name": canvas_name,
                "count": len(triggers_info),
                "triggers": triggers_info
            }

        @self.app.api_route("/api/v1/trigger/{node_id}", methods=["GET", "POST", "PUT"])
        async def handle_trigger(node_id: str, request: Request):
            # 这里的 endpoint 构造规则需要与 add_trigger 保持一致
            path = f"/api/v1/trigger/{node_id}"
            task_id = uuid4().hex

            if path in self.registry:
                data = {}
                try:
                    if request.method == "POST":
                        content_type = request.headers.get("content-type", "")
                        if "application/json" in content_type:
                            data = await request.json()
                        else:
                            data = dict(await request.form())
                    else:
                        data = dict(request.query_params)
                except Exception as e:
                    logger.warning(f"解析 Webhook 数据失败: {e}")

                # 执行回调
                self.registry[path](data, task_id)
                return {"status": "success", "node_id": node_id, "task_id": task_id}

            return JSONResponse(status_code=404, content={"status": "not_registered", "path": path})

        # 这里保留你原有的 /api/v1/result/{exec_id} 路由...
        @self.app.get("/api/v1/result/{exec_id}")
        async def get_result(exec_id: str):
            record = self.execution_manager.get_record(exec_id)
            if not record:
                return {"status": "not_found", "exec_id": exec_id}
            status = record.status if record else "waiting"
            if status == "success":
                return {"status": "success", "exec_id": exec_id, "output_data": record.output_data}
            elif status == "failed":
                return {"status": "failed", "exec_id": exec_id, "error_msg": record.error_msg}
            elif status == "cancelled":
                return {"status": "cancelled", "exec_id": exec_id}
            elif status == "waiting":
                return {"status": "waiting", "exec_id": exec_id}
            elif status == "running":
                return {"status": "running", "exec_id": exec_id}
            return {"status": "unknown", "exec_id": exec_id}

    def add_trigger(self, canvas_name: str, node_id: str, callback: Callable, **kwargs):
        """
        实现基类方法：注册 Webhook 路径
        参数要求: kwargs 需包含 'endpoint' (可选，默认为标准路径)
        """
        # 如果没有传入 endpoint，则使用默认的 node_id 路径
        endpoint = kwargs.get("endpoint", f"/api/v1/trigger/{node_id}")

        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint

        # 注册回调
        self.registry[endpoint] = callback

        # 调用基类映射维护
        self._register_in_mapping(canvas_name, node_id)

        # 记录 node_id 与 endpoint 的对应关系，方便 remove_trigger 时查找
        if not hasattr(self, '_node_to_endpoint'):
            self._node_to_endpoint = {}
        self._node_to_endpoint[node_id] = endpoint

        # 自动启动 Server（如果未启动）
        self.start()

        logger.info(f"[Webhook] 节点 {node_id} 已注册接口: {endpoint}")

    def remove_trigger(self, node_id: str):
        """实现基类方法：注销 Webhook"""
        endpoint = getattr(self, '_node_to_endpoint', {}).get(node_id)
        if endpoint and endpoint in self.registry:
            del self.registry[endpoint]
            del self._node_to_endpoint[node_id]

            # 调用基类映射清理
            self._unregister_from_mapping(node_id)
            logger.info(f"[Webhook] 已注销接口: {endpoint}")

    def stop(self):
        """
        由于 uvicorn 的 Server 运行在 Thread 中且通常随主线程退出，
        这里主要做逻辑上的清理。彻底停止 uvicorn 线程通常需要更复杂的信号控制。
        """
        self.registry.clear()
        logger.info("Webhook 管理器逻辑服务已停止")

    def start(self):
        """启动后端 Web Server"""
        if self._server_thread is not None:
            return

        if self._is_port_in_use(self.port):
            logger.error(f"端口 {self.port} 已被占用，Webhook 服务启动失败！")
            return

        config = uvicorn.Config(
            self.app, host=self.host, port=self.port,
            log_level="error", log_config=None,
            ws="none", loop="asyncio"
        )
        server = uvicorn.Server(config)
        self._server_thread = threading.Thread(target=server.run, daemon=True)
        self._server_thread.start()
        logger.info(f"FastAPI 服务已启动: http://{self.host}:{self.port}")

    def _is_port_in_use(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex((self.host, port)) == 0


class WebhookPlugin(BaseTriggerPlugin):
    NAME = "Webhook触发"
    manager = WebhookManager()

    def get_properties(self, parent_node=None):
        return {
            "webhook_endpoint":
                {
                    "type": PropertyType.TEXT,
                    "label": "接口路由",
                    "default": f"/api/v1/trigger/{parent_node.persistent_id}"
                }
        }

    def activate(self, canvas_name, node_id, callback, props):
        endpoint = props.get("webhook_endpoint") or f"/api/v1/trigger/{node_id}"
        self.manager.add_trigger(canvas_name, node_id, callback, endpoint=endpoint)