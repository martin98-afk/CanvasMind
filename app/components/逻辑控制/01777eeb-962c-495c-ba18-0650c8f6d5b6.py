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
    name = "运行计数器"
    category = "逻辑控制"
    description = "简单的节点控制自身property样例，初始次数为0，每运行一次，计数器+1"
    requirements = "numpy"
    inputs = [
        PortDefinition(name="input1", label="输入1", type=ArgumentType.JSON, connection=ConnectionType.MULTIPLE),
    ]
    outputs = [
        PortDefinition(name="output1", label="输出1", type=ArgumentType.JSON),
    ]
    properties = {
        "counter": PropertyDefinition(
            type=PropertyType.INT,
            default=0,
            label="计数器",
        ),
    }
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        self.emit_message(
            method="set_node_property",
            params={"counter": params.counter + 1}
        )
        return {
            "output1": inputs.input1
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
