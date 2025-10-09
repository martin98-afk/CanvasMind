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
    name = "移除思考过程（<think>标签）"
    category = "大模型组件"
    description = "移除大模型输出中被 <think>...</think> 包裹的思考过程，仅保留外部内容"
    requirements = ""

    inputs = [
        PortDefinition(name="raw_text", label="原始模型输出", type=ArgumentType.TEXT),
    ]
    outputs = [
        PortDefinition(name="cleaned_text", label="清理后文本", type=ArgumentType.TEXT),
        PortDefinition(name="has_think_removed", label="是否移除了思考", type=ArgumentType.BOOL),
    ]

    properties = {
        "remove_empty_lines": PropertyDefinition(
            type=PropertyType.BOOL,
            label="是否移除空行",
            default="True",
        ),
        "keep_inner_if_no_outer": PropertyDefinition(
            type=PropertyType.BOOL,
            label="若只有 <think> 内容，是否保留内部",
            default="True",
    description = "移除大模型输出中被 <think>...</think> 包裹的思考过程，仅保留外部内容"
        ),
    }

    def run(self, params, inputs = None):
        import re
        raw_text = inputs.get("raw_text", "") if inputs else ""
        remove_empty = params.get("remove_empty_lines", True)
        keep_inner = params.get("keep_inner_if_no_outer", True)

        if not raw_text:
            return {
                "cleaned_text": "",
                "has_think_removed": False
            }

        # 使用非贪婪模式匹配 <think>...</think>，支持跨行
        think_pattern = r"<think>.*?</think>"
        has_think = bool(re.search(think_pattern, raw_text, re.DOTALL | re.IGNORECASE))

        # 移除所有 <think>...</think> 块
        cleaned = re.sub(think_pattern, "", raw_text, flags=re.DOTALL | re.IGNORECASE)

        # 如果移除后内容为空，但用户希望保留内部内容
        if not cleaned.strip() and has_think and keep_inner:
            # 提取第一个 <think> 内容作为 fallback
            match = re.search(r"<think>(.*?)</think>", raw_text, re.DOTALL | re.IGNORECASE)
            if match:
                cleaned = match.group(1)

        # 清理多余空白
        if remove_empty:
            lines = [line.rstrip() for line in cleaned.splitlines() if line.strip()]
            cleaned = "\n".join(lines)
        else:
            cleaned = cleaned.strip()

        return {
            "cleaned_text": cleaned,
            "has_think_removed": has_think
        }
