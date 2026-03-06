# -*- coding: utf-8 -*-
from loguru import logger

from app.plugins.node_plugins.base import VariableOperatePlugin


class RunNodePlugin(VariableOperatePlugin):
    plugin_id = "run_node"
    plugin_name = "运行制定名称的节点"
    plugin_desc = "根据节点名称选择指定节点，可以多选，也可以只选一个节点，选择节点后再进行create_next_node"
    plugin_template = """self.emit_message(
            method="run_node",
            params={
                "key": "node_name",  # 节点名称
                "run_mode": "run"  # 1. run 只运行节点 2. run_to 运行到该节点 3. run_from 从该节点运行 4. run_subgraph 运行该节点所在子图
            }
        )
    """

    def operate(self, node, params):
        try:
            target_node = node.parent_window.graph.get_node_by_name(params["key"])
            run_mode = params["run_mode"]
            if run_mode == "run":
                node.parent_window.run_node(target_node)
            elif run_mode == "run_to":
                node.parent_window.run_to(target_node)
            elif run_mode == "run_from":
                node.parent_window.run_from(target_node)
            elif run_mode == "run_subgraph":
                node.parent_window.run_subgraph(target_node)
        except:
            logger.exception("运行指定节点失败")