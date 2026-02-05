import threading
import uvicorn

from loguru import logger
from typing import Dict, Callable
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class WebhookManager:
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

        self.app = FastAPI(title="NodeGraph Webhook Server")
        self.host = host
        self.port = port
        self.registry: Dict[str, Callable] = {}  # { path: callback }

        self._setup_routes()
        self._server_thread = None
        self._initialized = True

    def _setup_routes(self):
        """配置 FastAPI 路由"""

        # 使用通配符/路径参数来捕获所有触发请求
        @self.app.api_route("/api/v1/trigger/{node_id}", methods=["GET", "POST", "PUT"])
        async def handle_trigger(node_id: str, request: Request):
            path = f"/api/v1/trigger/{node_id}"
            logger.info(f"收到 Webhook 请求: {path}")

            if path in self.registry:
                # 解析请求体
                data = {}
                try:
                    if request.method == "POST":
                        # 尝试获取 JSON，如果失败则尝试获取表单
                        content_type = request.headers.get("content-type", "")
                        if "application/json" in content_type:
                            data = await request.json()
                        else:
                            form_data = await request.form()
                            data = dict(form_data)
                    else:
                        # GET 请求获取查询参数
                        data = dict(request.query_params)
                except Exception as e:
                    logger.warning(f"解析 Webhook 数据失败: {e}")

                # 调用节点的回调函数 (TriggerNode.trigger_execution)
                # 注意：回调函数内部通过信号发射到主线程，所以这里可以安全调用
                self.registry[path](data)

                return {"status": "success", "node_id": node_id}

            return JSONResponse(status_code=404, content={"status": "not_registered", "path": path})

    def register(self, endpoint: str, callback: Callable):
        """注册路径回调"""
        # 确保路径以 / 开头
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint
        self.registry[endpoint] = callback
        logger.info(f"[FastAPI] 注册接口: {endpoint}")

    def unregister(self, endpoint: str):
        """注销路径"""
        if endpoint in self.registry:
            del self.registry[endpoint]
            logger.info(f"[FastAPI] 注销接口: {endpoint}")

    def start(self):
        """在独立线程中启动 Uvicorn"""
        if self._server_thread is None:
            config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="error")
            server = uvicorn.Server(config)

            self._server_thread = threading.Thread(target=server.run, daemon=True)
            self._server_thread.start()
            logger.info(f"FastAPI Webhook 服务已启动: http://{self.host}:{self.port}")


class SchedulerManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SchedulerManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        # 使用 BackgroundScheduler
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        self._initialized = True
        logger.info("APScheduler 调度器已启动")

    def add_job(self, node_id: str, callback: callable, cron_str: str):
        """
        添加/更新定时任务
        """
        try:
            # 1. 预处理表达式，去除多余空格
            cron_str = cron_str.strip()
            fields = cron_str.split()

            trigger = None

            # 2. 根据字段数量判断解析方式
            if len(fields) == 5:
                # 标准 Unix 格式: 分 时 日 月 周
                trigger = CronTrigger.from_crontab(cron_str)
                logger.info(f"[Scheduler] 解析为标准 5 位 Crontab (分钟级)")
            elif len(fields) == 6:
                # 扩展格式: 秒 分 时 日 月 周
                trigger = CronTrigger(
                    second=fields[0],
                    minute=fields[1],
                    hour=fields[2],
                    day=fields[3],
                    month=fields[4],
                    day_of_week=fields[5]
                )
                logger.info(f"[Scheduler] 解析为 6 位 Cron (秒级)")
            else:
                raise ValueError(f"不支持的 Cron 格式 (字段数量: {len(fields)})，请使用 5 位或 6 位表达式")

            # 3. 提交任务
            self.scheduler.add_job(
                callback,
                trigger,
                id=node_id,
                replace_existing=True,
                # 容错时间：如果系统繁忙导致错过触发，10秒内仍允许运行
                misfire_grace_time=10
            )
            logger.info(f"[Scheduler] 节点 {node_id} 任务已成功挂载: {cron_str}")

        except Exception as e:
            # 使用 logger.exception 会打印出完整的堆栈信息，方便调试
            logger.error(f"[Scheduler] 任务解析或添加失败: {cron_str} | 错误: {e}")

    def remove_job(self, node_id: str):
        """移除指定节点的定时任务"""
        try:
            if self.scheduler.get_job(node_id):
                self.scheduler.remove_job(node_id)
                logger.info(f"[Scheduler] 任务已注销: {node_id}")
        except Exception as e:
            logger.error(f"[Scheduler] 移除任务失败: {node_id} | {e}")

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown()