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
    name = "知识库查询"
    category = "大模型组件"
    description = ""
    requirements = ""

    inputs = [
        PortDefinition(name="query", label="查询问题", type=ArgumentType.TEXT),
    ]
    outputs = [
        PortDefinition(name="context", label="检索结果", type=ArgumentType.TEXT),
        PortDefinition(name="documents", label="原始文档列表", type=ArgumentType.JSON),
    ]

    properties = {
        "top_k": PropertyDefinition(
            type=PropertyType.INT,
            label="返回结果数",
            default="3",
        ),
        "knowledge_base_id": PropertyDefinition(
            type=PropertyType.TEXT,
            label="知识库ID",
            default="default_kb",
        ),
    }

    def run(self, params, inputs = None):
        query = inputs.get("query", "") if inputs else ""
        top_k = int(params.get("top_k", 3))

        # TODO: 实际项目中替换为真实检索逻辑
        # 示例：模拟返回相关文档
        mock_docs = [
            {"content": "Python 是一种高级编程语言。", "score": 0.95},
            {"content": "大模型可以生成文本、代码等。", "score": 0.89},
            {"content": "大模型可以生成文本、代码等。", "score": 0.89},
            {"content": "大模型可以生成文本、代码等。", "score": 0.89},
            {"content": "大模型可以生成文本、代码等。", "score": 0.89},
            {"content": "大模型可以生成文本、代码等。", "score": 0.89},
            {"content": "大模型可以生成文本、代码等。", "score": 0.89},
        ][:top_k]

        context = "\n\n".join([doc["content"] for doc in mock_docs])

        return {
            "context": context,
            "documents": mock_docs
        }
