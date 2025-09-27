from app.components.base import BaseComponent, PortDefinition, PropertyDefinition, ArgumentType


class Component(BaseComponent):
    name="CSV 读取器"
    category="数据集成"
    description="接收本地上传csv文件"
    inputs=[]
    outputs=[
        PortDefinition(name="csv", label="csv文件", type=ArgumentType.CSV)
    ]

    def run(self, params, inputs=None):
        file_path = params.get("csv")
        config_file = params.get("config_file")
        output_dir = params.get("output")

        # 处理文件逻辑
        result = {
            "csv": file_path,
            "value": config_file,
            "model": output_dir
        }
        return result