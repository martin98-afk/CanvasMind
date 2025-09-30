from app.components.base import BaseComponent, PortDefinition, PropertyDefinition, PropertyType, ArgumentType
class InputComponent(BaseComponent):
    name = "文本输入"
    category = "数据集成"
    description = "文本输入内容"
    inputs = [
    ]
    outputs = [
        PortDefinition(name="text", label="text", type=ArgumentType.TEXT),
    ]
    properties = {
        "input": PropertyDefinition(
            type=PropertyType.TEXT,
            default="文本内容",
            label="输入文本"
        )
    }

    def run(self, params, inputs=None):
        return {"text": params["input"]}
