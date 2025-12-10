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


class ErrorHandlingComponent(BaseComponent):
    name = "错误处理"
    category = "逻辑控制"
    description = "处理工具调用或解析过程中的错误，生成错误提示信息"
    requirements = ""
    inputs = [
        PortDefinition(name="variables", label="错误信息", type=ArgumentType.FILE, connection=ConnectionType.SINGLE)
    ]
    outputs = [
        PortDefinition(name="prompt", label="错误提示", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE)
    ]
    properties = {
        "template": PropertyDefinition(
            type=PropertyType.TEXT, 
            default="生成的步骤json信息错误，步骤信息必须为严格的json格式，且包含next_step信息\\n且 next_step 内容必须为：调用工具 或 总结答案 其一\\n\\n当前生成的错误步骤json信息：\\n\\n$input.variables[0]$\\n\\n根据历史对话反思错误，生成正确的步骤信息。",
            label="错误提示模板"
        )
    }

    def run(self, params, inputs):
        """处理错误信息生成提示文本"""
        try:
            # 获取错误信息文件内容
            error_data = inputs.variables

            # 使用模板生成错误提示
            prompt = params.template.replace("$input.variables[0]$", error_data)

            return {
                "prompt": prompt
            }
        except Exception as e:
            self.logger.error(f"错误处理组件执行失败: {str(e)}")
            raise

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = ErrorHandlingComponent()
    result = model.debug(
        params={"template": "生成的步骤json信息错误，步骤信息必须为严格的json格式，且包含next_step信息\\n且 next_step 内容必须为：调用工具 或 总结答案 其一\\n\\n当前生成的错误步骤json信息：\\n\\n$input.variables[0]$\\n\\n根据历史对话反思错误，生成正确的步骤信息。"},
        inputs={"variables": "{\"next_step\": \"invalid_value\"}"},
        global_vars={},
        node_id="error_handler",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)