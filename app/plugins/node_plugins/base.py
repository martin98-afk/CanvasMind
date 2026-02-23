# -*- coding: utf-8 -*-
import os
import pickle
import tempfile
import uuid
from abc import ABC, abstractmethod

from app.plugins.constants import PluginType
from app.utils.config import Settings
from app.utils.utils import ssh_send_file


class BaseNodePlugin(ABC):
    """所有插件的基类"""
    # 插件唯一标识，对应 ComponentMessage 中的 method 或 data_type
    plugin_id = ""
    plugin_name = ""
    plugin_desc = ""
    plugin_type = PluginType.NODE
    plugin_template = ""

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

    def on_confirmed(self, result_data, env_data, response_file):
        is_ssh = env_data and env_data.get('type') == 'ssh'
        if is_ssh:
            temp_path = os.path.join(tempfile.gettempdir(), f"ask_{uuid.uuid4().hex}.pkl")
            with open(temp_path, 'wb') as f:
                pickle.dump(result_data, f)
            ssh_send_file(env_data, temp_path, response_file)
            if os.path.exists(temp_path): os.remove(temp_path)
        else:
            os.makedirs(os.path.dirname(response_file), exist_ok=True)
            with open(response_file, 'wb') as f:
                pickle.dump(result_data, f)

    def handle(self, node, params, msg=None):
        # 默认从 params 获取数据并渲染
        response_file = params.get("response_file")
        env_data = getattr(node.parent_window, 'env_data', None)
        result = self.operate(node, params, msg)
        if Settings.get_instance().communication_method.value == "ZMQ通信":
            return result
        else:
            self.on_confirmed(result, env_data, response_file)

    @abstractmethod
    def operate(self, node, params, msg=None):
        raise NotImplementedError


class VariableOperatePlugin(BaseNodePlugin):
    """分类三：变量操作插件 (Node -> Variable)"""

    def handle(self, node, params, msg=None):
        # 默认从 params 获取数据并渲染
        self.operate(node, params)

    @abstractmethod
    def operate(self, node, params):
        raise NotImplementedError