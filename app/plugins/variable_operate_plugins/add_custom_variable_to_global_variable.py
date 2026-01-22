# -*- coding: utf-8 -*-
from app.plugins.base import VariableOperatePlugin


class AddVariablePlugin(VariableOperatePlugin):
    plugin_id = "add_custom_to_global_variable"
    plugin_name = "添加全局变量"
    plugin_desc = "将本节点的指定端口添加到全局变量中"
    plugin_template = """self.emit_message(
            method="add_custom_to_global_variable",
            params={"key": "value"}
        )
    """

    def operate(self, node, params):
        if node.parent_window:
            for key, value in params.items():
                node.parent_window.global_variables.set(key=key, value=value)