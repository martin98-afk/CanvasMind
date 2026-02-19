# -*- coding: utf-8 -*-
import socket
import threading
import json
from typing import Callable, Dict, Optional, Set
from uuid import uuid4

import uvicorn
import requests  # 需要引入 requests 库发送回调
from fastapi import FastAPI, Request, BackgroundTasks
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
        # 静态回调配置：NodeID -> URL (在节点属性中配置的)
        self.static_callback_urls: Dict[str, str] = {}

        # 动态回调缓存：TaskID -> URL (请求参数里带来的)
        # 格式: { "task_id_123": "http://api.com/callback", ... }
        self.dynamic_callbacks: Dict[str, str] = {}

        self.execution_manager = ExecutionManager()

        self._setup_routes()
        self._server_thread = None
        self._initialized = True

    def get_canvas_triggers_info(self, canvas_name: str):
        # 从基类的 canvas_mapping 中获取该画布下的所有 node_id
        node_ids = self.canvas_mapping.get(canvas_name, [])

        triggers_info = []
        node_to_endpoint = getattr(self, '_node_to_endpoint', {})

        for node_id in node_ids:
            # 获取对应的 Webhook 路径
            endpoint_info = node_to_endpoint.get(node_id)
            if endpoint_info:
                endpoint, name = endpoint_info
                callback_url = self.static_callback_urls.get(node_id, "")
                triggers_info.append({
                    "node_id": node_id,
                    "node_name": name,
                    "endpoint": endpoint,
                    "callback_url": callback_url,  # 展示回调地址信息
                    "url": f"http://{self.host}:{self.port}/api/v1/trigger/{endpoint}"
                })

        return {
            "canvas_name": canvas_name,
            "count": len(triggers_info),
            "triggers": triggers_info
        }

    def _setup_routes(self):
        """配置 FastAPI 路由逻辑"""

        @self.app.get("/health")
        async def health_check():
            return {
                "status": "ok", "active_triggers": {
                    canvas_name: self.get_canvas_triggers_info(canvas_name)
                    for canvas_name in self.canvas_mapping
                }
            }

        @self.app.get("/health/{canvas_name}")
        async def health_check_canvas(canvas_name: str):
            if canvas_name not in self.canvas_mapping:
                return {"status": "not_found"}
            else:
                return {
                    "status": "ok", "active_triggers": {
                        canvas_name: self.get_canvas_triggers_info(canvas_name)
                    }
                }

        @self.app.api_route("/api/v1/trigger/{endpoint}", methods=["GET", "POST", "PUT"])
        async def handle_trigger(endpoint: str, request: Request):
            path = endpoint
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
                    # 2. 提取动态 callback_url
                    # 支持从 JSON body 或 Query Param 中获取 "callback_url"
                    dynamic_url = data.get("callback_url")
                    if dynamic_url:
                        self.dynamic_callbacks[task_id] = dynamic_url
                        logger.info(f"[Webhook] 捕获动态回调地址 Task[{task_id}]: {dynamic_url}")
                    # 注入请求元数据
                    data.update({
                        "request_method": request.method,
                        "request_headers": dict(request.headers),
                        "request_ip": request.client.host,
                        "_webhook_task_id": task_id  # 传递 task_id 以便后续追踪
                    })
                except Exception as e:
                    logger.warning(f"解析 Webhook 数据失败: {e}")

                # 执行触发器回调（这里是触发工作流运行）
                self.registry[path](data, task_id)

                return {"status": "success", "task_id": task_id}

            return JSONResponse(status_code=404, content={"status": "not_registered", "path": path})

        # 保持原有的结果查询接口
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
        """注册触发器"""
        endpoint = kwargs.get("endpoint", node_id)
        static_url = kwargs.get("callback_url", "").strip()

        if endpoint in self.registry:
            logger.warning(f"[Webhook] 已注册 endpoint: {endpoint}")
            return False

        self.registry[endpoint] = callback

        # 更新静态配置
        if static_url:
            self.static_callback_urls[node_id] = static_url
        elif node_id in self.static_callback_urls:
            del self.static_callback_urls[node_id]

        # 维护基类映射
        self._register_in_mapping(canvas_name, node_id)
        if not hasattr(self, '_node_to_endpoint'):
            self._node_to_endpoint = {}
        self._node_to_endpoint[node_id] = (endpoint, kwargs.get("name", ""))

        self.start()
        return True

    def remove_trigger(self, node_id: str):
        endpoint_info = getattr(self, '_node_to_endpoint', {}).get(node_id)
        if endpoint_info:
            endpoint, _ = endpoint_info
            if endpoint in self.registry:
                del self.registry[endpoint]
            del self._node_to_endpoint[node_id]

        if node_id in self.static_callback_urls:
            del self.static_callback_urls[node_id]

        self._unregister_from_mapping(node_id)

    def callback(self, node_id: str, callback_data: dict):
        """
        工作流执行结束后的回调入口
        :param node_id: 触发该任务的节点ID
        :param callback_data: 执行结果数据，期望包含输入时注入的 '_webhook_task_id'
        """
        target_urls = set()

        # 1. 添加静态配置的回调地址 (节点属性里的)
        if node_id in self.static_callback_urls:
            target_urls.add(self.static_callback_urls[node_id])

        # 2. 查找并添加动态回调地址 (请求参数里的)
        # 尝试从结果数据中找 task_id，字段名需与 handle_trigger 中注入的一致
        task_id = callback_data.get("_webhook_task_id")

        if task_id and task_id in self.dynamic_callbacks:
            dynamic_url = self.dynamic_callbacks.pop(task_id)  # 获取并移除，防止内存泄漏
            target_urls.add(dynamic_url)
            logger.info(f"[Webhook] 找到动态回调地址: {dynamic_url}")

        if not target_urls:
            return

        # 3. 异步发送回调
        threading.Thread(
            target=self._send_callbacks,
            args=(target_urls, callback_data, node_id),
            daemon=True
        ).start()

    def _send_callbacks(self, urls: Set[str], data: dict, node_id: str):
        """向所有目标地址发送结果"""
        for url in urls:
            try:
                logger.info(f"[Webhook] 发送回调 -> {url}")
                resp = requests.post(
                    url,
                    json=data,
                    headers={"Content-Type": "application/json", "X-Node-ID": node_id},
                    timeout=5
                )
                if resp.status_code >= 400:
                    logger.warning(f"[Webhook] 回调失败 {url}: {resp.status_code}")
            except Exception as e:
                logger.error(f"[Webhook] 回调异常 {url}: {e}")

    def stop(self):
        self.registry.clear()
        self.callback_urls.clear()
        logger.info("Webhook 管理器逻辑服务已停止")

    def start(self):
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
            "webhook_endpoint": {
                "type": PropertyType.TEXT,
                "label": "接口路由",
                "default": parent_node.persistent_id,
                "description": "接口路由，默认为节点 ID。服务地址: http://0.0.0.0:5000/api/v1/trigger/{endpoint}"
            },
            "callback_url": {
                "type": PropertyType.TEXT,
                "label": "结果回调地址",
                "default": "",
                "description": "可选。工作流运行完成后，将结果以 POST 请求发送至此 URL。"
            }
        }

    def activate(self, canvas_name, node, callback, props):
        endpoint = props.get("webhook_endpoint") or node.persistent_id
        # 获取回调地址属性
        callback_url = props.get("callback_url", "").strip()

        # 将 callback_url 传递给 manager
        success = self.manager.add_trigger(
            canvas_name,
            node.persistent_id,
            callback,
            endpoint=endpoint,
            name=node.name(),
            callback_url=callback_url
        )

        if not success:
            # 如果注册失败（通常是重复了），重置回 ID 也许不是最佳做法，但保持原逻辑
            node.set_property("webhook_endpoint", node.persistent_id)