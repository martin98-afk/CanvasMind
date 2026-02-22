# -*- coding: utf-8 -*-
import threading
import time
from sqlalchemy import create_engine, text
from loguru import logger

from app.plugins.trigger_plugins.base_trigger import BaseTriggerManager, BaseTriggerPlugin
from app.components.base import PropertyType


class SQLWatchManager(BaseTriggerManager):
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SQLWatchManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized: return
        super().__init__("SQLWatcher")
        self.running = True
        self.tasks = {}  # {node_id: task_info}

        self.worker_thread = threading.Thread(target=self._polling_loop, daemon=True)
        self.worker_thread.start()
        self._initialized = True

    def _get_engine(self, db_url):
        # 简单缓存 engine，实际生产中需考虑连接池回收
        return create_engine(db_url, pool_recycle=3600)

    def _execute_check(self, node_id, task):
        try:
            db_url = task['db_url']
            sql = task['sql']
            last_result = task.get('last_result')

            engine = self._get_engine(db_url)
            with engine.connect() as conn:
                result = conn.execute(text(sql)).fetchone()
                # 将 result 转为 tuple 或 str 以便比较
                current_val = str(result[0]) if result else None

                # 如果是第一次运行，只记录不触发（或者根据需求触发）
                if last_result is None:
                    task['last_result'] = current_val
                    return

                # 对比是否有变化
                if current_val != last_result:
                    logger.info(f"[SQL] 节点 {node_id} 数据变更: {last_result} -> {current_val}")
                    task['last_result'] = current_val

                    # 触发回调
                    threading.Thread(target=task['callback'], kwargs={
                        "old_value": last_result,
                        "new_value": current_val
                    }).start()

        except Exception as e:
            logger.error(f"[SQL] 查询失败 {node_id}: {e}")

    def _polling_loop(self):
        while self.running:
            for node_id in list(self.tasks.keys()):
                task = self.tasks.get(node_id)
                if task:
                    interval = task.get('interval', 60)
                    last_run = task.get('last_run', 0)

                    if time.time() - last_run > interval:
                        task['last_run'] = time.time()
                        threading.Thread(
                            target=self._execute_check,
                            args=(node_id, task)
                        ).start()

            time.sleep(1)

    def add_trigger(self, canvas_name: str, node_id: str, callback: callable, **kwargs):
        db_url = kwargs.get("db_url")  # e.g., mysql+pymysql://user:pass@host/db
        sql = kwargs.get("sql")  # e.g., SELECT MAX(id) FROM table
        interval = kwargs.get("interval", 60)

        if not db_url or not sql:
            return

        self.tasks[node_id] = {
            "db_url": db_url,
            "sql": sql,
            "interval": int(interval),
            "callback": callback,
            "last_result": None,
            "last_run": 0
        }
        self._register_in_mapping(canvas_name, node_id)
        logger.info(f"[SQL] 节点 {node_id} 挂载监控: {sql[:30]}...")

    def remove_trigger(self, node_id: str):
        if node_id in self.tasks:
            del self.tasks[node_id]
            self._unregister_from_mapping(node_id)
            logger.info(f"[SQL] 节点 {node_id} 已移除")

    def stop(self):
        self.running = False


class SQLTriggerPlugin(BaseTriggerPlugin):
    NAME = "数据库变更"
    manager = SQLWatchManager()

    def get_properties(self, parent_node=None):
        return {
            "db_url": {
                "type": PropertyType.TEXT,
                "label": "数据库连接串 (SQLAlchemy 格式)",
                "default": "sqlite:///data.db"
            },
            "sql": {
                "type": PropertyType.TEXT,
                "label": "监控 SQL (返回单值)",
                "default": "SELECT COUNT(*) FROM users"
            },
            "interval": {
                "type": PropertyType.INT,
                "label": "轮询间隔 (秒)",
                "default": 60
            }
        }

    def activate(self, canvas_name, node, callback, properties):
        self.manager.add_trigger(
            canvas_name=canvas_name,
            node_id=node.persistent_id,
            callback=callback,
            **properties
        )