# -*- coding: utf-8 -*-
import importlib
import inspect
import os
from abc import ABC, abstractmethod
from typing import Dict, Set, Any
from loguru import logger


ALL_MANAGERS = []
TRIGGER_PLUGINS = {}


def load_trigger_plugins():
    """
    递归扫描目录并加载所有继承自 BaseNodePlugin 的类
    :param root_dir: 插件根目录的绝对路径
    """
    # 1. 确定根包名
    root_dir = os.path.dirname(os.path.abspath(__file__))
    parts = root_dir.replace("\\", "/").split("/")
    try:
        # 这里自动寻找 'app' 目录作为包名起始点，你可以根据实际情况调整
        start_index = parts.index("app")
        base_package_path = ".".join(parts[start_index:])
    except ValueError:
        logger.error(f"路径 {root_dir} 中未找到 'app' 根包名，请检查目录结构")
        return

    # 2. 递归遍历目录
    for root, dirs, files in os.walk(root_dir):
        for filename in files:
            if filename.endswith(".py") and not filename.startswith("__"):
                # 计算相对路径并转为模块路径
                # 例如: /app/node_plugins/display/image_plugin.py -> app.node_plugins.display.image_plugin
                rel_path = os.path.relpath(os.path.join(root, filename), root_dir)
                module_rel_name = rel_path[:-3].replace(os.path.sep, ".")
                full_module_name = f"{base_package_path}.{module_rel_name}"

                try:
                    # 3. 动态加载模块
                    module = importlib.import_module(full_module_name)

                    # 4. 遍历模块中的所有类
                    for name, obj in inspect.getmembers(module):
                        if inspect.isclass(obj):
                            # 检查是否定义了 plugin_id 且不是基类本身
                            if hasattr(obj, "NAME") and obj.NAME != "Abstract":
                                plugin_instance = obj()
                                TRIGGER_PLUGINS[plugin_instance.NAME] = plugin_instance
                                logger.info(
                                    f"已加载触发器 [{plugin_instance.NAME}] 来自模块: {full_module_name}")
                except Exception as e:
                    logger.error(f"加载模块 {full_module_name} 失败: {e}")


class BaseTriggerPlugin(ABC):
    # 插件显示的名称，如 "定时触发"
    NAME = "Abstract"
    manager = None

    def __init__(self):
        pass

    @abstractmethod
    def get_properties(self) -> Dict[str, Dict[str, Any]]:
        """返回该触发器需要的属性定义"""
        return {}

    @abstractmethod
    def activate(self, canvas_name: str, node_id: str, callback: callable, properties: dict):
        """激活触发器"""
        pass

    def deactivate(self, node_id: str):
        """停用触发器"""
        self.manager.remove_trigger(node_id)


class BaseTriggerManager(ABC):
    """
    触发器管理器抽象基类
    定义了所有触发方式必须实现的标准化接口
    """

    def __init__(self, manager_name: str):
        self.manager_name = manager_name
        # 统一维护 画布 -> 节点ID集合 的映射关系
        # { canvas_name: {node_id1, node_id2, ...} }
        self.canvas_mapping: Dict[str, Set[str]] = {}
        logger.debug(f"{self.manager_name} 初始化完成")
        # 核心：将自己加入全局管理列表
        if self not in ALL_MANAGERS:
            ALL_MANAGERS.append(self)

    @abstractmethod
    def add_trigger(self, canvas_name: str, node_id: str, callback: callable, **kwargs):
        """
        添加/注册一个触发器
        :param canvas_name: 画布（工作流）名称
        :param node_id: 节点唯一ID（通常作为触发器的标识）
        :param callback: 触发后的回调函数
        :param kwargs: 各类触发器特有的参数（如 cron_str, endpoint, folder_path 等）
        """
        pass

    @abstractmethod
    def remove_trigger(self, node_id: str):
        """
        移除/注销单个触发器
        """
        # 在子类实现中，记得调用 self._unregister_from_mapping(node_id)
        pass

    def remove_by_canvas(self, canvas_name: str):
        """
        清理特定画布下的所有触发器
        """
        if canvas_name in self.canvas_mapping:
            # 复制一份 ID 列表，避免在循环中删除导致的迭代错误
            node_ids = list(self.canvas_mapping[canvas_name])
            for nid in node_ids:
                self.remove_trigger(nid)

            if canvas_name in self.canvas_mapping:
                del self.canvas_mapping[canvas_name]
            logger.info(f"[{self.manager_name}] 已清理画布 '{canvas_name}' 的所有触发项")

    @abstractmethod
    def stop(self):
        """
        彻底停止整个管理器服务（如关闭调度器、停止 Web Server）
        """
        pass

    # --- 内部辅助方法 ---

    def _register_in_mapping(self, canvas_name: str, node_id: str):
        """记录节点归属于哪个画布"""
        if canvas_name not in self.canvas_mapping:
            self.canvas_mapping[canvas_name] = set()
        self.canvas_mapping[canvas_name].add(node_id)

    def _unregister_from_mapping(self, node_id: str):
        """从映射表中移除节点"""
        for canvas_name, node_ids in self.canvas_mapping.items():
            if node_id in node_ids:
                node_ids.discard(node_id)
                # 如果画布下没节点了，可以选择保留或删除 key
                return canvas_name
        return None