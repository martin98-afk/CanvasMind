# -*- coding: utf-8 -*-
from app.plugins.base import VariableOperatePlugin


class AskPlugin(VariableOperatePlugin):
    plugin_id = "clear_global_variable"  # 对应 method: "ui.ask"

    def operate(self, node, params):
        value = params.get("value", "")
        if value.startswith(params.get("type", "")):
            value = value.split("node_vars.")[1]
        if node.parent_window:
            node.parent_window._on_global_variables_changed(
                var_type="node_vars", var_name=value, action="clear"
            )