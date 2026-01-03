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
    name = "文本存储为文件"
    category = "数据存储"
    description = ""
    requirements = ""
    inputs = [
        PortDefinition(name="input_text", label="待存储文本", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="file_name", label="文件名", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output_file", label="存储文件", type=ArgumentType.FILE),
    ]
    properties = {
        "suffix": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="txt",
            label="存储后缀",
            choices=["txt", "doc", "docx"]
        ),
    }
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        file_name = f"{inputs.file_name}.{params.suffix}"
        with open(file_name, "w", encoding="utf-8") as f:
            f.write(inputs.input_text)
        return {
            "output_file": file_name
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
