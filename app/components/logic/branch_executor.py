"""
@author: mading
@license: (C) Copyright: LUCULENT Corporation Limited.
@contact: mading@luculent.net
@file: branch_executor.py
@time: 2025/9/29 08:50
@desc: 
"""
from app.components.base import BaseComponent, PortDefinition, PropertyDefinition, PropertyType, ArgumentType


class BranchExecutorNode(BaseComponent):
    name = "分支执行器"
    category = "控制流"
    description = "根据条件结果执行相应分支"

    inputs = [
        PortDefinition(name="condition", label="条件结果", type=ArgumentType.BOOL),
        PortDefinition(name="true_branch", label="真分支", type=ArgumentType.TEXT),
        PortDefinition(name="false_branch", label="假分支", type=ArgumentType.TEXT)
    ]

    outputs = [
        PortDefinition(name="executed_output", label="执行输出", type=ArgumentType.TEXT),
        PortDefinition(name="branch_taken", label="执行分支", type=ArgumentType.TEXT)
    ]

    properties = {
        "execution_mode": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="conditional",
            choices=["conditional", "both"],
            label="执行模式"
        )
    }

    def run(self, params, inputs=None):
        condition = inputs.get("condition", False) if inputs else False
        true_data = inputs.get("true_branch") if inputs else None
        false_data = inputs.get("false_branch") if inputs else None
        mode = params.get("execution_mode", "conditional")

        if mode == "conditional":
            if condition:
                executed_output = true_data
                branch_taken = "true"
            else:
                executed_output = false_data
                branch_taken = "false"
        else:
            # 执行模式为 both 时，返回两个分支的数据
            executed_output = {
                "true": true_data,
                "false": false_data
            }
            branch_taken = "both"

        return {
            "executed_output": executed_output,
            "branch_taken": branch_taken
        }