# -*- coding: utf-8 -*-
from PyQt5.QtCore import QTimer

from app.plugins.node_plugins.base import VariableOperatePlugin


class AddVariablePlugin(VariableOperatePlugin):
    plugin_id = "set_node_property"
    plugin_name = "设定当前节点的属性值"
    plugin_desc = "用于动态改变当前节点、或者指定uuid的节点的属性值，比如随机数，可以通过这个方法进行控制"
    plugin_template = """self.emit_message(
            method="set_node_property",
            params={
                "current_node": {"property_name": "property_value"},
                "node_uuid": {"property_name": "property_value"}
            }
        )
    """

    def set_node_property(self, node, params):
        for key, value in params.items():
            node.set_property(key, value)

    def operate(self, node, params):
        for key, value in params.items():
            if key == "current_node":
                try:
                    self.set_node_property(node, value)
                except:
                    pass
            else:
                source_node = node.parent_window.graph.get_node_by_uuid(key)
                self.set_node_property(source_node, value)