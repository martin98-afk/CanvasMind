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
    name = "测试新版组件配置"
    category = "测试组件"
    description = ""
    requirements = "numpy"
    inputs = [
        PortDefinition(name="input1", label="输入1", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output1", label="输出1", type=ArgumentType.TEXT),
    ]
    properties = {
        "prop1": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="属性1",
        ),
        "prop2": PropertyDefinition(
            type=PropertyType.RANGE,
            default="137.9",
            label="属性2",
            min=0.0,
            max=200.0,
            step=1.0,
        ),
        "prop3": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="属性3",
            schema={
                "prop1": PropertyDefinition(
                    type=PropertyType.RANGE,
                    default="67.0",
                    label="属性1",
                    min=0.0,
                    max=100.0,
                    step=1.0
                ),
                "prop2": PropertyDefinition(
                    type=PropertyType.BOOL,
                    default=True,
                    label="属性2",
                ),
            }
        ),
        "prop4": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="test1",
            label="属性4",
            choices=["test1", "test2", "test3"]
        ),
    }
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import numpy as np
        # 在这里编写你的组件逻辑
        input_data = inputs.input1
        param1 = params.prop1
        self.logger.info("这是组件输出信息")
        # 处理逻辑
        result = f"处理结果: {input_data} + {param1}"
        return {
            "output1": result
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={"prop1": "test"},
        inputs={"input1": "output"},
        node_id="测试模型",
        show_input_types = True,
        show_output_types = True,
        show_execution_time = True,
        global_vars = {}
    )
    print(result)
