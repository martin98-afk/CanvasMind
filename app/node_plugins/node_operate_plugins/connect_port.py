# -*- coding: utf-8 -*-
from PyQt5.QtCore import QTimer

from app.node_plugins.base import VariableOperatePlugin


class ClearVariablePlugin(VariableOperatePlugin):
    plugin_id = "connect_port"  # 对应 method: "ui.ask"
    plugin_name = "连接两个节点之间的端口"
    plugin_desc = "连接两个节点之间的端口"
    plugin_template = """self.emit_message(
            method="connect_port",
            params={
                "source": {
                    “node_id": "node_uuid",
                    "type": "output",
                    "port_index": 0
                },
                "target": {
                    “node_id": "node_uuid",
                    "type": "input",
                    "port_index": 0
                }
            }
        )
    """

    def operate(self, node, params):
        try:
            source_node = node.parent_window.graph.get_node_by_uuid(params["source"]["node_id"])
            target_node = node.parent_window.graph.get_node_by_uuid(params["target"]["node_id"])
            if params.get("source").get("type") == "output":
                source_port = source_node.output(params["source"]["port_index"])
                QTimer.singleShot(0, lambda: target_node.set_input(params.get("target").get("port_index"), source_port))
            else:
                source_port = target_node.output(params["source"]["port_index"])
                QTimer.singleShot(0, lambda: source_node.set_input(params.get("target").get("port_index"), source_port))
        except:
            return "操作失败"