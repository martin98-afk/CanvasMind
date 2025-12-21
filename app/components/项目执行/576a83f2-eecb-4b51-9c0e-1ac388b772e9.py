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
    name = "获取导出项目列表"
    category = "项目执行"
    description = ""
    requirements = ""
    inputs = [
    ]
    outputs = [
        PortDefinition(name="output", label="输出项目列表", type=ArgumentType.ARRAY),
    ]
    properties = {
        "projects": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="项目列表",
            schema={
                "proj": PropertyDefinition(
                    type=PropertyType.VARIABLE,
                    default="导出项目",
                    label="项目路径",
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
            "output": [item.proj for item in params.projects]
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
