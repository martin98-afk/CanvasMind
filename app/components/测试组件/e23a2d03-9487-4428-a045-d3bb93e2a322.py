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
    name = "test"
    category = "测试组件"
    description = ""
    requirements = ""
    inputs = [
    ]
    outputs = [
    ]
    properties = {
        "prop1": PropertyDefinition(
            type=PropertyType.RANGE,
            default="",
            label="属性1",
            min=0,
            max=100,
            step=1,
        ),
        "prop2": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="属性2",
            schema={
                "prop1": PropertyDefinition(
                    type=PropertyType.RANGE,
                    default="",
                    label="属性1",
                    min=0,
                    max=100,
                    step=1
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
        # 在这里编写你的组件逻辑
        self.logger.info(params)
        # 处理逻辑
        result = "处理结果: {input_data} + {param1}"
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
