from app.components.base import BaseComponent, PortDefinition, PropertyDefinition, ArgumentType


class Component(BaseComponent):
    name="CSV 读取器"
    category="数据集成"
    description="接收本地上传csv文件"
    inputs=[PortDefinition(name="csv", label="csv文件", type=ArgumentType.CSV)]
    outputs=[PortDefinition(name="csv", label="csv文件", type=ArgumentType.CSV)]

    def run(self, params, inputs=None):
        return {"csv": inputs["csv"]}