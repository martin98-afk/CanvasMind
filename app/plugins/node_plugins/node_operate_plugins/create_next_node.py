# -*- coding: utf-8 -*-

from app.plugins.node_plugins.base import InteractivePlugin


class ClearVariablePlugin(InteractivePlugin):
    plugin_id = "create_next_node"  # 对应 method: "ui.ask"
    plugin_name = "新建下一个节点"
    plugin_desc = "在当前节点后创建指定节点"
    plugin_template = """self.emit_interactive_message(
            method="create_next_node",
            params={
                "key": "next_node_key"
            }
        )
    """

    def operate(self, node, params, msg=None):
        node = node.parent_window.node_operations.create_next_node(params.get("key"))
        return node.persistent_id