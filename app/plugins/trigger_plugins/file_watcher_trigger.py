# -*- coding: utf-8 -*-
import os
import threading
from typing import Callable
from uuid import uuid4

from loguru import logger
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.components.base import PropertyType
from app.plugins.trigger_plugins.base_trigger import BaseTriggerManager, BaseTriggerPlugin


class SingleFileEventHandler(FileSystemEventHandler):
    """
    单文件监听处理器
    只在指定文件发生 'modified' (修改) 事件时触发
    """

    def __init__(self, callback: Callable, target_path: str, node_id: str, canvas_name: str):
        self.callback = callback
        self.target_path = os.path.abspath(target_path)
        self.node_id = node_id
        self.canvas_name = canvas_name

    def on_modified(self, event):
        if event.is_directory:
            return

        # 只有当变动的文件路径与目标路径完全一致时才触发
        if os.path.abspath(event.src_path) == self.target_path:
            try:
                # 获取文件大小或其他元数据作为 payload
                file_size = os.path.getsize(self.target_path)
                data = {
                    "event_type": "modified",
                    "file_path": self.target_path,
                    "file_size": file_size,
                    "filename": os.path.basename(self.target_path),
                    "trigger_source": "single_file_watcher"
                }
                logger.info(f"[FileMonitor] 检测到文件变更: {self.target_path}")
                # 调用触发器节点的回调，传入 uuid 作为 trace_id
                self.callback(data, uuid4().hex)
            except Exception as e:
                logger.error(f"[FileMonitor] 处理文件事件失败: {e}")


class SingleFileManager(BaseTriggerManager):
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SingleFileManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        super().__init__("SingleFileMonitor")

        self.observer = Observer()
        self.observer.start()

        # 存储 node_id -> watch对象
        self.active_watches = {}

        self._initialized = True
        logger.info("SingleFileMonitor 监听服务已启动")

    def add_trigger(self, canvas_name: str, node_id: str, callback: Callable, **kwargs):
        target_file = kwargs.get("target_file")
        if not target_file:
            logger.warning(f"[FileMonitor] 节点 {node_id} 未提供目标文件路径")
            return

        try:
            # 转换为绝对路径
            abs_path = os.path.abspath(target_file)

            # 检查文件是否存在
            if not os.path.exists(abs_path):
                logger.error(f"[FileMonitor] 目标文件不存在: {abs_path}")
                return

            if not os.path.isfile(abs_path):
                logger.error(f"[FileMonitor] 目标路径不是一个文件: {abs_path}")
                return

            # 如果已存在先移除
            self.remove_trigger(node_id)

            # Watchdog 只能监听目录，所以我们需要监听该文件所在的父目录
            # 然后在 Handler 中过滤出具体的文件名
            parent_dir = os.path.dirname(abs_path)

            handler = SingleFileEventHandler(callback, abs_path, node_id, canvas_name)

            # schedule 返回 watch 对象
            watch_handle = self.observer.schedule(handler, parent_dir, recursive=False)
            self.active_watches[node_id] = watch_handle

            # 注册映射
            self._register_in_mapping(canvas_name, node_id)
            logger.info(f"[FileMonitor] 节点 {node_id} 开始监控文件: {abs_path}")

        except Exception as e:
            logger.error(f"[FileMonitor] 注册监听失败: {e}")

    def remove_trigger(self, node_id: str):
        try:
            if node_id in self.active_watches:
                watch_handle = self.active_watches.pop(node_id)
                self.observer.unschedule(watch_handle)

                self._unregister_from_mapping(node_id)
                logger.info(f"[FileMonitor] 节点 {node_id} 监控已移除")
        except Exception as e:
            logger.error(f"[FileMonitor] 移除监听失败: {e}")

    def stop(self):
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
            logger.info("SingleFileMonitor 服务已停止")


class SingleFileTriggerPlugin(BaseTriggerPlugin):
    NAME = "文件内容变更触发"
    manager = SingleFileManager()

    def get_properties(self, parent_node=None):
        return {
            "target_file_path": {
                "type": PropertyType.FILE,  # 前端通常渲染为文件选择器或文本框
                "label": "目标文件路径",
                "default": ""
            }
        }

    def activate(self, canvas_name, node, callback, props):
        path = props.get("target_file_path")
        if path:
            self.manager.add_trigger(
                canvas_name,
                node.persistent_id,
                callback,
                target_file=path
            )