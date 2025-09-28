"""
@author: mading
@license: (C) Copyright: LUCULENT Corporation Limited.
@contact: mading@luculent.net
@file: select_columns.py
@time: 2025/9/28 08:57
@desc: 
"""
from app.components.base import BaseComponent, PortDefinition, PropertyDefinition, ArgumentType, PropertyType


class MyComponent(BaseComponent):
    name = "CSV列选择"
    category = "数据处理"
    description = "从CSV文件中选择特定列"

    inputs = [
        PortDefinition(name="input_data", label="输入数据", type=ArgumentType.CSV)
    ]

    outputs = [
        PortDefinition(name="output_data", label="输出数据", type=ArgumentType.CSV),
    ]

    properties = {
        "columns": PropertyDefinition(
            type=PropertyType.COLUM_SELECT,
            default="",
            label="选择列名"
        )
    }

    def run(self, params, inputs=None):
        # 组件逻辑
        input_data = inputs.get("input_data") if inputs else "default"
        param1 = params.get("parameter1", "default")
        max_count = int(params.get("max_count", 10))

        # 处理逻辑...
        result_data = f"{input_data}_{param1}_{max_count}"

        return {
            "output_data": "/path/to/output.csv",  # 文件路径
            "result": result_data  # 文本结果
        }