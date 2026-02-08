# -*- coding: utf-8 -*-
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from app.trigger_plugins.base_trigger import BaseTriggerManager, BaseTriggerPlugin

from app.components.base import PropertyType



class SchedulerManager(BaseTriggerManager):
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SchedulerManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized: return
        super().__init__("Scheduler")

        self.scheduler = BackgroundScheduler(job_defaults={
            'coalesce': True,
            'max_instances': 1,
            'misfire_grace_time': 30
        })
        self.scheduler.start()
        self._initialized = True
        logger.info("APScheduler 调度器已启动")

    def add_trigger(self, canvas_name: str, node_id: str, callback: callable, **kwargs):
        cron_str = kwargs.get("cron_str", "").strip()
        try:
            fields = cron_str.split()
            if len(fields) == 5:
                trigger = CronTrigger.from_crontab(cron_str)
            elif len(fields) == 6:
                trigger = CronTrigger(second=fields[0], minute=fields[1], hour=fields[2],
                                      day=fields[3], month=fields[4], day_of_week=fields[5])
            else:
                raise ValueError("Cron 格式需为 5 位或 6 位")

            self.scheduler.add_job(callback, trigger, id=node_id, replace_existing=True)

            # 调用基类方法记录映射
            self._register_in_mapping(canvas_name, node_id)
            logger.info(f"[Scheduler] 节点 {node_id} 挂载成功: {cron_str}")
        except Exception as e:
            logger.error(f"[Scheduler] 任务添加失败: {e}")

    def remove_trigger(self, node_id: str):
        try:
            if self.scheduler.get_job(node_id):
                self.scheduler.remove_job(node_id)
                self._unregister_from_mapping(node_id)
                logger.info(f"[Scheduler] 任务已注销: {node_id}")
        except Exception as e:
            logger.error(f"[Scheduler] 移除任务失败: {e}")

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown()


class CronTriggerPlugin(BaseTriggerPlugin):
    NAME = "定时触发"
    manager = SchedulerManager()

    def get_properties(self):
        return {
            "cron_expression": {
                "type": PropertyType.TEXT,
                "label": "Cron 表达式",
                "default": "*/30 * * * * *"
            }
        }

    def activate(self, canvas_name, node_id, callback, properties):
        cron = properties.get("cron_expression")
        if cron:
            self.manager.add_trigger(
                canvas_name=canvas_name,
                node_id=node_id,
                callback=callback,
                cron_str=cron
            )