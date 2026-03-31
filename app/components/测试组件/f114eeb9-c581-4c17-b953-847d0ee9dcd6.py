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


class Component(BaseComponent):
    name = "添加字符串"
    category = "测试组件"
    description = "将输入文本与指定字符串进行拼接，适用于文本预处理、前后缀添加、动态内容组合等场景喵~"
    requirements = ""
    inputs = [
        PortDefinition(name="input1", label="待拼接文本", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output1", label="拼接结果", type=ArgumentType.TEXT),
    ]
    properties = {
        "prop1": PropertyDefinition(
            type=PropertyType.VARIABLE,
            default="全局变量",
            label="拼接字符串",
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        self.logger.info(params)
        return {
            "output1": inputs.input1 + params.prop1[1]
        }
