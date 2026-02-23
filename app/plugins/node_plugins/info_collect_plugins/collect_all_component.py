# -*- coding: utf-8 -*-

from app.plugins.node_plugins.base import InteractivePlugin
from app.scan_components import ComponentScanner


class AskPlugin(InteractivePlugin):
    plugin_id = "get_all_components"
    plugin_name = "获取当前所有组件信息"
    plugin_desc = "获取当前组件列表中的所有组件信息"
    plugin_template = """result = self.emit_interactive_message(
            method="get_all_components",
            params={}
        )
"""

    def operate(self, node, params, msg=None):
        return list(ComponentScanner().get_components()[0].keys())