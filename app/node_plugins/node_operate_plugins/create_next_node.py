# -*- coding: utf-8 -*-
from app.node_plugins.base import VariableOperatePlugin


class ClearVariablePlugin(VariableOperatePlugin):
    plugin_id = "create_next_node"  # 对应 method: "ui.ask"
    plugin_name = "新建下一个节点"
    plugin_desc = "在当前节点后创建指定节点"
    plugin_template = """self.emit_message(
            method="create_next_node",
            params={
                "key": "next_node_key"
            }
        )
    """

    def operate(self, node, params):
        node.parent_window.node_operations.create_next_node(params.get("key"))