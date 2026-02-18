# -*- coding: utf-8 -*-
import os
import pickle
import tempfile
import uuid

from app.node_plugins.base import InteractivePlugin
from app.scan_components import ComponentScanner
from app.utils.config import Settings
from app.utils.utils import ssh_send_file


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