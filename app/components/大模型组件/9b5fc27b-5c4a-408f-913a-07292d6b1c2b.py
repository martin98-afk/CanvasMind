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


class Component(BaseComponent):
    name = "JSON输出解析"
    category = "大模型组件"
    description = ""
    requirements = ""

    inputs = [
        PortDefinition(name="llm_output", label="模型原始输出", type=ArgumentType.TEXT),
    ]
    outputs = [
        PortDefinition(name="parsed_json", label="解析后的 JSON", type=ArgumentType.JSON),
        PortDefinition(name="is_valid", label="是否有效", type=ArgumentType.BOOL),
    ]

    properties = {
        "strict": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="严格模式",
        ),
    }

    def run(self, params, inputs = None):
        import json
        import re
        text = inputs.get("llm_output", "") if inputs else ""
        strict = params.get("strict", False)

        # 尝试提取 ```json ... ``` 块
        json_match = re.search(r"```(?:json)?\s*({.*?})\s*```", text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 否则尝试找最外层 {}
            brace_match = re.search(r"\{.*\}", text, re.DOTALL)
            json_str = brace_match.group(0) if brace_match else text

        try:
            parsed = json.loads(json_str)
            return {
                "parsed_json": parsed,
                "is_valid": True
            }
        except Exception as e:
            if not strict:
                # 宽松模式：返回原始文本作为 fallback
                return {
                    "parsed_json": {"raw_text": text, "error": str(e)},
                    "is_valid": False
                }
            else:
                raise e
