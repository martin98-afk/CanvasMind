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
    name = "提示词模板"
    category = "大模型组件"
    description = ""
    requirements = ""

    inputs = [
        PortDefinition(name="variables", label="变量字典", type=ArgumentType.JSON, connection="multi"), 
    ]
    outputs = [
        PortDefinition(name="prompt", label="生成的提示词", type=ArgumentType.TEXT),
    ]

    properties = {
        "template": PropertyDefinition(
            type=PropertyType.LONGTEXT,
            default="""你好，{{name}}！今天是{{day}}。""",
            label="提示词模板",
        ),
    }

    def run(self, params, inputs = None):
        import re
        self.logger.info(inputs)
        template = params.get("template", "")
        variables = inputs.get("variables", {}) if inputs else {}
        for variable in variables:
            if isinstance(variable, str):
                import json
                try:
                    variables = json.loads(variable)
                except:
                    variables = {}

            # 替换 {{key}} 为变量值
            def replace_match(match):
                key = match.group(1)
                return str(variable.get(key, match.group(0)))

            template = re.sub(r"\{\{(\w+)\}\}", replace_match, template)
        self.logger.info(template)
        
        return {"prompt": template}
