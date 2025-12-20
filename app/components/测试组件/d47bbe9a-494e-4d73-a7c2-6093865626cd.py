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
    name = "获取导出项目"
    category = "测试组件"
    description = "用于获取导出项目"
    requirements = ""
    inputs = [
    ]
    outputs = [
        PortDefinition(name="output1", label="输出1", type=ArgumentType.TEXT),
    ]
    properties = {
        "prop1": PropertyDefinition(
            type=PropertyType.VARIABLE,
            default="导出项目",
            label="属性1",
        ),
        "prop2": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="属性2",
            schema={
                "prop1": PropertyDefinition(
                    type=PropertyType.RANGE,
                    default="40.0",
                    label="属性1",
                    min=0.0,
                    max=120.0,
                    step=1.0
                ),
                "prop2": PropertyDefinition(
                    type=PropertyType.BOOL,
                    default=True,
                    label="属性2",
                ),
                "prop3": PropertyDefinition(
                    type=PropertyType.VARIABLE,
                    default="全局变量",
                    label="属性3",
                ),
                "prop4": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="TEST{{id}}",
                    label="属性4",
                ),
            }
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        return {
            "output1": params.prop1
        }
