# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod


class BaseNodePlugin(ABC):
    """所有插件的基类"""
    # 插件唯一标识，对应 ComponentMessage 中的 method 或 data_type
    plugin_id = ""

    @abstractmethod
    def handle(self, node, params, msg=None):
        """
        处理逻辑
        :param parent: 主窗口对象
        :param node: 节点对象 (BasicNodeWithGlobalProperty)
        :param params: 消息参数
        :param msg: 原始 ComponentMessage 对象
        """
        raise NotImplementedError


class DisplayPlugin(BaseNodePlugin):
    """分类一：单向数据展示插件 (Node -> UI)"""
    def handle(self, node, params, msg=None):
        # 默认从 params 获取数据并渲染
        for port_name in params:
            data = params.get(port_name, {}).get("data")
            self.render(node, port_name, data)

    @abstractmethod
    def render(self, node, port_name, data):
        raise NotImplementedError


class InteractivePlugin(BaseNodePlugin):
    """分类二：双向交互插件 (Node <-> UI)"""

    @abstractmethod
    def handle(self, node, params, msg=None):
        raise NotImplementedError


class VariableOperatePlugin(BaseNodePlugin):
    """分类三：变量操作插件 (Node -> Variable)"""

    def handle(self, node, params, msg=None):
        # 默认从 params 获取数据并渲染
        self.operate(node, params)

    @abstractmethod
    def operate(self, node, params):
        raise NotImplementedError