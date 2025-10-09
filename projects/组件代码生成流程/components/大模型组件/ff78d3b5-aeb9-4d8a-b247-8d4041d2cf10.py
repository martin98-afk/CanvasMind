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
    name = "JSON文本包装"
    category = "大模型组件"
    description = ""
    requirements = ""
    inputs = [
        PortDefinition(name="input1", label="输入1", type=ArgumentType.TEXT),
    ]
    outputs = [
        PortDefinition(name="output1", label="输出1", type=ArgumentType.JSON),
    ]
    properties = {
        "prop_0": PropertyDefinition(
            type=PropertyType.TEXT,
            default="text",
            label="属性1",
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        # 在这里编写你的组件逻辑
        input = inputs.get("input1")
        return {
            "output1": {
                params.get("prop_0"): input
            }
        }
