# -*- coding: utf-8 -*-
from app.plugins.base import VariableOperatePlugin


class DeleteVariablePlugin(VariableOperatePlugin):
    plugin_id = "delete_output_from_global_variable"
    plugin_name = "删除全局变量"
    plugin_desc = "将本节点的指定端口从全局变量中删除"
    plugin_template = """self.emit_message(
            method="delete_output_from_global_variable",
            params={"value": "port_name"}
        )
"""

    def operate(self, node, params):
        value = params.get("value", "")
        if value and node.parent_window:
            node.parent_window.property_panel._delete_output_from_global_variable(
                node=node, port_name=value,
            )