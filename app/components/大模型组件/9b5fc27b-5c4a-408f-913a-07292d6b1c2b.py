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
    name = "大模型输出解析"
    category = "大模型组件"
    description = "从大模型输出中提取并解析结构化数据（JSON/Python/XML）"
    requirements = ""

    inputs = [
        PortDefinition(name="llm_output", label="模型原始输出", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
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
        "type": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="json",
            label="解析类型",
            choices=["json", "python", "xml"]
        ),
    }

    def run(self, params, inputs=None):

        text = inputs.llm_output if inputs else ""
        strict = params.strict
        parse_type = params.type

        try:
            if parse_type == "json":
                parsed = self._parse_json(text)
            elif parse_type == "python":
                parsed = self._parse_python(text)
            elif parse_type == "xml":
                parsed = self._parse_xml(text)
            else:
                raise ValueError(f"Unsupported parse type: {parse_type}")

            return {
                "parsed_json": parsed,
                "is_valid": True
            }

        except Exception as e:
            return self._handle_parse_error(e, text, strict)

    def _parse_json(self, text: str):
        import json
        import re
        # Step 1: 尝试从 markdown 代码块中提取 json 内容
        # 支持 ```json ... ``` 或 ```python ... ``` 等，只取 json 类型
        json_match = re.search(r"```(?:json|JSON)\s*([\s\S]*?)\s*```", text, re.DOTALL)
        if json_match:
            candidate = json_match.group(1).strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as e:
                # 如果代码块内 JSON 无效，继续尝试其他方式
                pass
        
        # Step 2: 尝试直接解析整个文本（可能包含多个 JSON 块）
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        
        # Step 3: 如果没有完整 JSON，尝试提取最外层的 JSON 对象或数组
        # 支持 {} 或 []，考虑嵌套括号/方括号
        stack = 0
        start = None
        bracket_type = None  # 'curly' for {}, 'square' for []
        
        for i, char in enumerate(text):
            if char == '{':
                if stack == 0:
                    start = i
                    bracket_type = 'curly'
                stack += 1
            elif char == '}':
                if stack == 1 and start is not None:
                    candidate = text[start:i+1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        # 如果失败，继续寻找下一个匹配
                        start = None
                stack -= 1
            elif char == '[':
                if stack == 0:
                    start = i
                    bracket_type = 'square'
                stack += 1
            elif char == ']':
                if stack == 1 and start is not None:
                    candidate = text[start:i+1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        start = None
                stack -= 1
        
        # 如果仍无法解析，返回错误
        raise ValueError("No valid JSON object or array found in input")


    def _parse_python(self, text: str):
        import re
        import ast
        # 移除 Markdown 代码块
        text = re.sub(r"```(?:python|py)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"```", "", text)

        return text.strip()

    def _parse_xml(self, text: str):
        import re
        import xml.etree.ElementTree as ET
        # 移除可能的 markdown 代码块
        text = re.sub(r"```(?:xml)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"```", "", text)

        try:
            root = ET.fromstring(text.strip())
            return self._xml_to_dict(root)
        except ET.ParseError as e:
            raise ValueError(f"Invalid XML: {e}")

    def _handle_parse_error(self, error, text, strict):
        if not strict:
            return {
                "parsed_json": {"raw_text": text, "error": str(error)},
                "is_valid": False
            }
        else:
            raise error

    def _xml_to_dict(self, element):
        """将 XML 元素递归转换为字典"""
        # 如果元素没有子元素且有文本，直接返回文本
        if len(element) == 0 and element.text and element.text.strip():
            return element.text.strip()

        result = {}
        if element.attrib:
            result["@attributes"] = element.attrib

        if element.text and element.text.strip() and len(element) > 0:
            result["#text"] = element.text.strip()

        children = {}
        for child in element:
            child_data = self._xml_to_dict(child)
            if child.tag in children:
                if not isinstance(children[child.tag], list):
                    children[child.tag] = [children[child.tag]]
                children[child.tag].append(child_data)
            else:
                children[child.tag] = child_data

        result.update(children)
        return result if result else None
