# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py" if (Path(__file__).parent.parent / "base.py").exists() else Path(__file__).parent.parent.parent / "base.py"
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


class DynamicComponent(BaseComponent):
    name = "过滤数值型数据"
    category = "数据预处理"
    description = "过滤csv中数值型数据"
    requirements = ""

    inputs = [
        PortDefinition(name="input1", label="input1", type=ArgumentType.CSV, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output1", label="output1", type=ArgumentType.CSV),
    ]
    properties = {
        "opposite": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="取非数值型数据",
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        if params.opposite:
            result = inputs.input1.select_dtypes(exclude=['number'])
        else:
            result = inputs.input1.select_dtypes(include=['number'])
        return {
            "output1": result
        }
