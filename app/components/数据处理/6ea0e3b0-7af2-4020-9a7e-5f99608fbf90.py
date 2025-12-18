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
    name = "文本拼接器"
    category = "数据处理"
    description = "将输入文本与参数中的字符串拼接后输出"
    requirements = "无"
    inputs = [
        PortDefinition(
            name="input_text",
            label="输入文本",
            type=ArgumentType.TEXT,
            connection=ConnectionType.SINGLE
        )
    ]
    outputs = [
        PortDefinition(
            name="output_result",
            label="拼接结果",
            type=ArgumentType.TEXT,
            connection=ConnectionType.SINGLE
        )
    ]
    properties = {
        "separator": PropertyDefinition(
            type=PropertyType.TEXT,
            default=" - ",
            label="分隔符",
            description="用于连接输入文本与参数的字符串"
        ),
        "prefix": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="前缀",
            description="可选添加到结果开头的文本"
        ),
        "suffix": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="后缀",
            description="可选添加到结果结尾的文本"
        )
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        input_text = inputs.input_text
        separator = params.separator
        prefix = params.prefix
        suffix = params.suffix

        result = f"{prefix}{input_text}{separator}{suffix}"
        self.logger.info(f"文本拼接完成: {result}")

        return {
            "output_result": result
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={
            "separator": " | ",
            "prefix": "[INFO] ",
            "suffix": " [END]"
        },
        inputs={
            "input_text": "Hello World"
        },
        node_id="test_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True,
        global_vars={}
    )
    print(result)
