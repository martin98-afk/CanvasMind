# -*- coding: utf-8 -*-
from app.node_plugins.base import VariableOperatePlugin


class ClearVariablePlugin(VariableOperatePlugin):
    plugin_id = "clear_global_variable"  # 对应 method: "ui.ask"
    plugin_name = "清空指定节点变量"
    plugin_desc = "从全局变量中删除指定变量的数据"
    plugin_template = """self.emit_message(
            method="clear_global_variable",
            params={
                "type": "node_vars",
                "value": "变量名"
            }
        )
    """

    def operate(self, node, params):
        value = params.get("value", "")
        if value.startswith(params.get("type", "")):
            value = value.split("node_vars.")[1]
        if node.parent_window:
            node.parent_window._on_global_variables_changed(
                var_type="node_vars", var_name=value, action="clear"
            )