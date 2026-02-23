# -*- coding: utf-8 -*-

from app.plugins.node_plugins.base import InteractivePlugin


class AskPlugin(InteractivePlugin):
    plugin_id = "get_node_info"
    plugin_name = "获取指定组件的描述"
    plugin_desc = "获取当前组件列表中的所有组件信息"
    plugin_template = """result = self.emit_interactive_message(
            method="get_node_info",
            params={"node_id": "node_uuid"}
        )
"""

    def operate(self, node, params, msg=None):
        if "node_id" not in params:
            return node.description
        else:
            return node.parent_window.graph.get_node_by_uuid(params["node_id"]).description