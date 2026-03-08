# -*- coding: utf-8 -*-
from app.plugins.node_plugins.base import VariableOperatePlugin


class ClearVariablePlugin(VariableOperatePlugin):
    plugin_id = "store_current_task_output"  # 对应 method: "ui.ask"
    plugin_name = "将结果固化到当前任务输出"
    plugin_desc = "将输出结果存储到当前执行任务的最终输出中，避免节点重复运行覆盖"
    plugin_template = """self.emit_message(
            method="store_current_task_output",
            params={
                "key": "output"
            }
        )
    """

    def operate(self, node, params):
        node.parent_window.canvas_runner.store_output(output=params)