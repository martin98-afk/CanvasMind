# -*- coding: utf-8 -*-
from app.plugins.base import VariableOperatePlugin


class AddVariablePlugin(VariableOperatePlugin):
    plugin_id = "add_custom_to_global_variable"
    plugin_name = "设置自定义变量"
    plugin_desc = "在全局变量中设置自定义变量，支持一次设定多个变量。"
    plugin_template = """self.emit_message(
            method="add_custom_to_global_variable",
            params={"key": "value"}
        )
    """

    def operate(self, node, params):
        if node.parent_window:
            for key, value in params.items():
                node.parent_window.global_variables.set(key=key, value=value)
                node.parent_window.property_panel._on_global_variables_changed(
                    var_type="custom", var_name=key, action="update"
                )