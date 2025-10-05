# -*- coding: utf-8 -*-
import importlib.util
import pathlib
base_path = pathlib.Path(__file__).parent.parent / "base.py"
spec = importlib.util.spec_from_file_location("base", str(base_path))
base_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base_module)

# 导入所需项目
BaseComponent = base_module.BaseComponent
PortDefinition = base_module.PortDefinition
PropertyDefinition = base_module.PropertyDefinition
PropertyType = base_module.PropertyType
ArgumentType = base_module.ArgumentType


class Component(BaseComponent):
    name = "归一化推理(npy)"
    category = "数据预处理"
    description = ""
    requirements = ""
    inputs = [
        PortDefinition(name="input", label="端口1", type=ArgumentType.ARRAY),
        PortDefinition(name="scaler", label="端口2", type=ArgumentType.SKLEARNMODEL),
    ]
    outputs = [
        PortDefinition(name="output", label="端口1", type=ArgumentType.ARRAY),
    ]
    properties = {
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        # 在这里编写你的组件逻辑
        input = inputs.get("input")
        if len(input.shape) == 1:
            input = input[None, :]
        output = inputs.get("scaler").transform(input)
        return {
            "output": output
        }
