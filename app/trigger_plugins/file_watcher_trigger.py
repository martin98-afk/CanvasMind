# -*- coding: utf-8 -*-
import os
import threading
from typing import Callable
from uuid import uuid4

from loguru import logger
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.components.base import PropertyType
from app.trigger_plugins.base_trigger import BaseTriggerManager, BaseTriggerPlugin


class FileWatcherHandler(FileSystemEventHandler):
    """自定义事件处理器，当文件发生变动时触发回调"""

    def __init__(self, callback: Callable, node_id: str, canvas_name: str):
        self.callback = callback
        self.node_id = node_id
        self.canvas_name = canvas_name

    def on_created(self, event):
        if not event.is_directory:
            data = {
                "event_type": "created",
                "path": event.src_path,
                "filename": os.path.basename(event.src_path),
                "trigger_source": "file_watcher"
            }
            # 调用触发器节点的回调
            self.callback(data, uuid4().hex)


class FileWatcherManager(BaseTriggerManager):
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(FileWatcherManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        # 初始化基类
        super().__init__("FileWatcher")

        self.observer = Observer()
        self.observer.start()

        # 记录 node_id 与其对应的 watch 对象（watchdog 内部句柄）
        # { node_id: watch_handle }
        self.active_watches = {}

        self._initialized = True
        logger.info("FileWatcher 监听服务已启动")

    def add_trigger(self, canvas_name: str, node_id: str, callback: Callable, **kwargs):
        """
        实现基类方法：注册文件夹监听
        参数要求: kwargs 需包含 'watch_path'
        """
        watch_path = kwargs.get("watch_path")
        if not watch_path:
            logger.warning(f"[Watcher] 节点 {node_id} 未提供监听路径")
            return

        try:
            if not os.path.exists(watch_path):
                logger.error(f"[Watcher] 路径不存在，无法监听: {watch_path}")
                return

            # 如果该节点已经有监听任务，先移除旧的（防止重复监听）
            self.remove_trigger(node_id)

            handler = FileWatcherHandler(callback, node_id, canvas_name)

            # schedule 返回一个 watch 句柄，用于后续停止监听
            watch_handle = self.observer.schedule(handler, watch_path, recursive=False)
            self.active_watches[node_id] = watch_handle

            # 调用基类辅助方法：维护画布映射关系
            self._register_in_mapping(canvas_name, node_id)

            logger.info(f"[Watcher] 节点 {node_id} (画布: {canvas_name}) 已挂载监听: {watch_path}")
        except Exception as e:
            logger.error(f"[Watcher] 注册监听失败: {e}")

    def remove_trigger(self, node_id: str):
        """实现基类方法：移除单个节点的监听"""
        try:
            if node_id in self.active_watches:
                watch_handle = self.active_watches.pop(node_id)
                self.observer.unschedule(watch_handle)

                # 调用基类辅助方法：清理映射
                self._unregister_from_mapping(node_id)
                logger.info(f"[Watcher] 监听已成功卸载: {node_id}")
        except Exception as e:
            logger.error(f"[Watcher] 卸载监听失败: {e}")

    def stop(self):
        """实现基类方法：完全停止 Observer 线程"""
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
            logger.info("FileWatcher 监听服务已彻底停止")


class FileWatcherPlugin(BaseTriggerPlugin):
    NAME = "文件夹监听触发"
    manager = FileWatcherManager()

    def get_properties(self):
        return {
            "watch_folder_path": {"type": PropertyType.FILE, "label": "监听路径", "default": "folder"}
        }

    def activate(self, canvas_name, node_id, callback, props):
        self.manager.add_trigger(canvas_name, node_id, callback, watch_path=props.get("watch_folder_path"))