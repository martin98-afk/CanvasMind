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
    name = "运行指定节点"
    category = "变量操作"
    description = "根据指定的节点名称和运行模式，执行画布中的节点"
    requirements = ""
    inputs = [
        PortDefinition(name="input1", label="输入1", type=ArgumentType.TEXT, connection=ConnectionType.MULTIPLE),
    ]
    outputs = [
        PortDefinition(name="output1", label="输出1", type=ArgumentType.TEXT),
    ]
    properties = {
        "node_name": PropertyDefinition(
            type=PropertyType.VARIABLE,
            default="画布节点",
            label="待运行节点名",
        ),
        "run_mode": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="运行该节点",
            label="运行方式",
            choices=["运行该节点", "从该节点运行", "运行到该节点", "运行该节点所在子图"]
        ),
    }

    def run(self, params, inputs=None):
        """
        执行指定的画布节点

        Args:
            params: 节点属性（来自UI）
            inputs: 上游输入（触发型组件不使用）

        Returns:
            dict: 执行结果（空字典，因为是触发型组件）
        """
        # 获取参数
        node_name = params.get("node_name", "").strip()
        run_mode_option = params.get("run_mode", "运行该节点")

        # 参数校验
        if not node_name:
            raise ValueError("节点名称不能为空")

        # 运行模式映射
        mode_mapping = {
            "运行该节点": "run",
            "从该节点运行": "run_from",
            "运行到该节点": "run_to",
            "运行该节点所在子图": "run_subgraph"
        }

        actual_run_mode = mode_mapping.get(run_mode_option, "run")

        # 发送执行消息
        self.emit_message(
            method="run_node",
            params={
                "key": node_name,
                "run_mode": actual_run_mode
            }
        )

        # 返回空字典（触发型组件无输出）
        return {}


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
