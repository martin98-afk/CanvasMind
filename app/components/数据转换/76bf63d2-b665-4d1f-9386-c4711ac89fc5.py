# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py"
spec = importlib.util.spec_from_file_location("base", str(base_path))
base_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base_module)

# 导入所需项目
BaseComponent = base_module.BaseComponent
PortDefinition = base_module.PortDefinition
PropertyDefinition = base_module.PropertyDefinition
PropertyType = base_module.PropertyType
ArgumentType = base_module.ArgumentType
ConnectionType = base_module.ConnectionType


class Component(BaseComponent):
    name = "csv转npy"
    category = "数据转换"
    description = ""
    requirements = ""
    inputs = [
        PortDefinition(name="input", label="端口1", type=ArgumentType.CSV, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output", label="数据", type=ArgumentType.ARRAY),
        PortDefinition(name="columns", label="列名", type=ArgumentType.ARRAY),
        PortDefinition(name="index", label="标签", type=ArgumentType.ARRAY),
    ]
    properties = {
        "number": PropertyDefinition(
            type=PropertyType.INT,
            default=-1,
            label="取数量(-1为全部)",
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        # 在这里编写你的组件逻辑
        if params.number == -1:
            input_csv = inputs.input
        else:
            input_csv = inputs.input[:params.number]
        return {
            "output": input_csv.values,
            "columns": [column for column in input_csv.columns],
            "index": [id for id in input_csv.index]
        }
