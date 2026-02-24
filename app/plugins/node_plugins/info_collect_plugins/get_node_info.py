# -*- coding: utf-8 -*-

from app.plugins.node_plugins.base import InteractivePlugin
from app.scan_components import ComponentScanner


class AskPlugin(InteractivePlugin):
    plugin_id = "get_node_info"
    plugin_name = "获取指定组件的信息"
    plugin_desc = "提供组件名路径，获取组件描述、输入、输出端口、readme.md信息"
    plugin_template = """result = self.emit_message(
            method="get_node_info",
            params={"node_path": "category/node_name"},
            interactive=True
        )
"""

    def operate(self, node, params, msg=None):
        node = ComponentScanner().get_component(params["node_path"])
        if node is None:
            return "未找到该组件, 必须使用collect_all_component返回的key进行查询"
        return {
            "description": node.description,
            "inputs": [item.dict() for item in node.inputs],
            "outputs": [item.dict() for item in node.outputs],
            "properties": {item[0]: item[1].dict() for item in node.properties.items()},
        }