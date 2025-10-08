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
    name = "获取指定变量"
    category = "测试组件"
    description = ""
    requirements = ""
    inputs = [
        PortDefinition(name="input", label="端口1", type=ArgumentType.CSV),
    ]
    outputs = [
        PortDefinition(name="output", label="端口1", type=ArgumentType.JSON),
    ]
    properties = {
        "prop_0": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="属性1",
            schema={
                "params": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="属性1",
                ),
            }
        ),
        "prop_1": PropertyDefinition(
            type=PropertyType.RANGE,
            default="12",
            label="属性2",
            min=0,
            max=100,
            step=1,
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        # 在这里编写你的组件逻辑
        input = inputs.get("input")
        param = params.get("prop_0")
        self.logger.info(params)
        output = {}
        self.logger.info(input)
        self.logger.info(input.columns)
        for item in param:
            value = item.get("params")
            if getattr(input, value, None) is not None:
                self.logger.info(getattr(input, value))
                output[value] = [item for item in getattr(input, value)]
                
        return {
            "output": output
        }
