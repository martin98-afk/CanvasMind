import threading
from uuid import uuid4

import uvicorn

from loguru import logger
from typing import Dict, Callable
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.interfaces.canvas_interaface.utils.execution_manager import ExecutionManager


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
        # 新增：画布与路径的映射关系 { canvas_name: {path1, path2} }
        self.canvas_map: Dict[str, set] = {}

        self._setup_routes()
        self._server_thread = None
        self._initialized = True

    def _setup_routes(self):
        @self.app.get("/api/v1/result/{exec_id}")
        async def get_result(exec_id: str):
            em = ExecutionManager()
            record = em.get_record(exec_id)
            if not record:
                return JSONResponse(status_code=404, content={"message": "Not Found"})

            return {
                "execution_id": record.execution_id,
                "status": record.status,
                "start_time": record.start_time,
                "end_time": record.end_time,
                "duration": (record.end_time - record.start_time) if record.end_time else None,
                "output": record.output_data,
                "error": record.error_msg
            }

        @self.app.api_route("/api/v1/trigger/{node_id}", methods=["GET", "POST", "PUT"])
        async def handle_trigger(node_id: str, request: Request):
            path = f"/api/v1/trigger/{node_id}"
            task_id = uuid4().hex
            if path in self.registry:
                data = {}
                try:
                    if request.method == "POST":
                        content_type = request.headers.get("content-type", "")
                        data = await request.json() if "application/json" in content_type else dict(
                            await request.form())
                    else:
                        data = dict(request.query_params)
                except Exception as e:
                    logger.warning(f"解析 Webhook 数据失败: {e}")

                self.registry[path](data, task_id)
                return {"status": "success", "node_id": node_id, "task_id": task_id}
            return JSONResponse(status_code=404, content={"status": "not_registered", "path": path})

    def register(self, canvas_name: str, endpoint: str, callback: Callable):
        """注册路径回调，关联画布名"""
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint

        self.registry[endpoint] = callback

        # 记录到画布映射中
        if canvas_name not in self.canvas_map:
            self.canvas_map[canvas_name] = set()
        self.canvas_map[canvas_name].add(endpoint)

        logger.info(f"[Webhook] 画布 '{canvas_name}' 注册接口: {endpoint}")

    def unregister(self, endpoint: str):
        """注销单个路径"""
        if endpoint in self.registry:
            del self.registry[endpoint]
            # 从所有画布映射中移除该路径
            for endpoints in self.canvas_map.values():
                endpoints.discard(endpoint)
            logger.info(f"[Webhook] 注销接口: {endpoint}")

    def unregister_by_canvas(self, canvas_name: str):
        """新增：直接关闭该画布下的所有 Webhook"""
        if canvas_name in self.canvas_map:
            endpoints = list(self.canvas_map[canvas_name])
            for ep in endpoints:
                if ep in self.registry:
                    del self.registry[ep]
            del self.canvas_map[canvas_name]
            logger.info(f"[Webhook] 已清理画布 '{canvas_name}' 的所有 Webhook 注册 ({len(endpoints)} 个)")

    def start(self):
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
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        # 新增：画布与任务ID的映射 { canvas_name: {job_id1, job_id2} }
        self.canvas_jobs: Dict[str, set] = {}
        self._initialized = True
        logger.info("APScheduler 调度器已启动")

    def add_job(self, canvas_name: str, node_id: str, callback: callable, cron_str: str):
        """添加定时任务，关联画布名"""
        try:
            cron_str = cron_str.strip()
            fields = cron_str.split()
            if len(fields) == 5:
                trigger = CronTrigger.from_crontab(cron_str)
            elif len(fields) == 6:
                trigger = CronTrigger(second=fields[0], minute=fields[1], hour=fields[2],
                                      day=fields[3], month=fields[4], day_of_week=fields[5])
            else:
                raise ValueError("Cron 格式需为 5 位或 6 位")

            self.scheduler.add_job(callback, trigger, id=node_id, replace_existing=True, misfire_grace_time=10)

            # 记录画布与 Job 的关系
            if canvas_name not in self.canvas_jobs:
                self.canvas_jobs[canvas_name] = set()
            self.canvas_jobs[canvas_name].add(node_id)

            logger.info(f"[Scheduler] 画布 '{canvas_name}' 节点 {node_id} 挂载成功: {cron_str}")
        except Exception as e:
            logger.error(f"[Scheduler] 任务添加失败: {e}")

    def remove_job(self, node_id: str):
        """移除单个任务"""
        try:
            if self.scheduler.get_job(node_id):
                self.scheduler.remove_job(node_id)
                # 清理映射关系
                for job_ids in self.canvas_jobs.values():
                    job_ids.discard(node_id)
                logger.info(f"[Scheduler] 任务已注销: {node_id}")
        except Exception as e:
            logger.error(f"[Scheduler] 移除任务失败: {e}")

    def remove_by_canvas(self, canvas_name: str):
        """新增：清理特定画布的所有定时任务"""
        if canvas_name in self.canvas_jobs:
            job_ids = list(self.canvas_jobs[canvas_name])
            for jid in job_ids:
                if self.scheduler.get_job(jid):
                    self.scheduler.remove_job(jid)
            del self.canvas_jobs[canvas_name]
            logger.info(f"[Scheduler] 已清理画布 '{canvas_name}' 的所有定时任务 ({len(job_ids)} 个)")

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown()