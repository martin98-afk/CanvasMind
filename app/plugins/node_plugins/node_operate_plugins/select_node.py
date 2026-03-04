# -*- coding: utf-8 -*-
from PyQt5.QtCore import QTimer

from app.plugins.node_plugins.base import VariableOperatePlugin


class SelectNodePlugin(VariableOperatePlugin):
    plugin_id = "select_node"
    plugin_name = "根据uuid选择指定节点"
    plugin_desc = "根据uuid选择指定节点，可以多选，也可以只选一个节点，选择节点后再进行create_next_node"
    plugin_template = """self.emit_message(
            method="select_node",
            params={
                "key": ["node_uuid"]
            }
        )
    """

    def operate(self, node, params):
        try:
            if isinstance(params["key"], str):
                params["key"] = [params["key"]]
            nodes = []
            for node_uuid in params["key"]:
                nodes.append(node.parent_window.graph.get_node_by_uuid(node_uuid))
            [n.set_selected(True) for n in nodes]
        except:
            pass