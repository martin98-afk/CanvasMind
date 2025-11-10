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
    name = "测试节点1"
    category = "测试组件"
    description = "测试专用组件"
    requirements = ""
    inputs = [
        PortDefinition(name="input1", label="输入1", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output1", label="输出1", type=ArgumentType.TEXT),
    ]
    properties = {
        "prop1": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="属性1",
            schema={
                "prop1": PropertyDefinition(
                    type=PropertyType.RANGE,
                    default="12",
                    label="属性1",
                    min=0.0,
                    max=20.0,
                    step=1.0
                ),
                "prop2": PropertyDefinition(
                    type=PropertyType.BOOL,
                    default=False,
                    label="是否开启身份校验",
                ),
                "prop3": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="属性3",
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
        self.logger.info(params)
        return {
            "output1": inputs.input1
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={"prop1": [{"prop1": "1", "prop2": True}]},
        inputs={"input1": "output"},
        node_id="测试模型",
        show_input_types = True,
        show_output_types = True,
        show_execution_time = True,
        global_vars = {}
    )
    print(result)
