# -*- coding: utf-8 -*-
from app.plugins.base import VariableOperatePlugin


class AddVariablePlugin(VariableOperatePlugin):
    plugin_id = "add_global_variable"
    plugin_name = "添加全局变量"
    plugin_desc = "将本节点的指定端口添加到全局变量中"
    plugin_template = """self.emit_message(
            method="add_global_variable",
            params={"value": "port_name"}
        )
    """

    def operate(self, node, params):
        value = params.get("value", "")
        if value and node.parent_window:
            node.parent_window.property_panel._add_output_to_global_variable(
                node=node, port_name=value,
            )