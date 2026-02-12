# -*- coding: utf-8 -*-
from app.node_plugins.base import VariableOperatePlugin


class ClearVariablePlugin(VariableOperatePlugin):
    plugin_id = "connect_port"  # 对应 method: "ui.ask"
    plugin_name = "连接两个节点之间的端口"
    plugin_desc = "连接两个节点之间的端口"
    plugin_template = """self.emit_message(
            method="connect_port",
            params={
                "source_port": "next_node_key",
                "target_port": ""
            }
        )
    """

    def operate(self, node, params):
        node.parent_window.node_operations.create_next_node(params.get("key"))