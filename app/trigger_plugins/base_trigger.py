# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
from typing import Dict, Set, Any
from loguru import logger


ALL_MANAGERS = []


class BaseTriggerPlugin(ABC):
    # 插件显示的名称，如 "定时触发"
    NAME = "Abstract"
    manager = None

    def __init__(self):
        pass

    @abstractmethod
    def get_properties(self, parent_node=None) -> Dict[str, Dict[str, Any]]:
        """返回该触发器需要的属性定义"""
        return {}

    @abstractmethod
    def activate(self, canvas_name: str, node, callback: callable, properties: dict):
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