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
ConnectionType = base_module.ConnectionType


class Component(BaseComponent):
    name = "文本输入"
    category = "数据集成"
    description = "文本输入内容"
    inputs = [
    ]
    outputs = [
        PortDefinition(name="text", label="text", type=ArgumentType.TEXT),
    ]
    properties = {
        "input": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="文本内容",
            label="输入文本",
        ),
    }

    def run(self, params, inputs=None):
        return {"text": params.input}
