from app.components.base import BaseComponent, PortDefinition, PropertyDefinition, PropertyType, ArgumentType
class Component(BaseComponent):
    name="文档上传"
    category="数据集成"
    description="接收本地上传文件"
    outputs=[PortDefinition(name="file", label="csv文件", type=ArgumentType.FILE)]

    def run(self, params, inputs=None):
        pass
