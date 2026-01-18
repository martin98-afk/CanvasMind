# -*- coding: utf-8 -*-
from app.plugins.base import VariableOperatePlugin


class AskPlugin(VariableOperatePlugin):
    plugin_id = "add_global_variable"

    def operate(self, node, params):
        value = params.get("value", "")
        if value and node.parent_window:
            node.parent_window.property_panel._add_output_to_global_variable(
                node=node, port_name=value,
            )