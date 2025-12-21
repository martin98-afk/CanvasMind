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
    name = "获取项目结构"
    category = "项目执行"
    description = ""
    requirements = ""
    inputs = [
    ]
    outputs = [
        PortDefinition(name="project_spec", label="项目结构", type=ArgumentType.JSON),
    ]
    properties = {
        "project": PropertyDefinition(
            type=PropertyType.VARIABLE,
            default="导出项目",
            label="项目地址",
        ),
    }
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import json
        from pathlib import Path
        with open(Path(params.project) / "project_spec.json", 'r', encoding="utf-8") as f:
            data = json.load(f)
        return {
            "project_spec": data
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
