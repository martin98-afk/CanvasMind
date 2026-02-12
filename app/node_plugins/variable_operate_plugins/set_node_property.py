# -*- coding: utf-8 -*-
from app.node_plugins.base import VariableOperatePlugin


class AddVariablePlugin(VariableOperatePlugin):
    plugin_id = "set_node_property"
    plugin_name = "设定当前节点的属性值"
    plugin_desc = "用于动态改变当前节点的属性值，比如随机数，可以通过这个方法进行控制"
    plugin_template = """self.emit_message(
            method="set_node_property",
            params={"property_name": "property_value"}
        )
    """

    def operate(self, node, params):
        if node.parent_window:
            for key, value in params.items():
                try:
                    node.set_property(key, value)
                except:
                    pass