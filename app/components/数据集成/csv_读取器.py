from app.components.base import BaseComponent, PortDefinition, ArgumentType

class Component(BaseComponent):
    name="CSV 读取器"
    category="数据集成"
    description="接收本地上传csv文件"
    inputs=[PortDefinition(name="csv", label="csv文件", type=ArgumentType.FILE)]
    outputs=[PortDefinition(name="csv", label="csv文件", type=ArgumentType.CSV)]

    def run(self, params, inputs=None):
        import pandas as pd
        try:
            self.logger.info(inputs)
            self.logger.info(f"开始读取csv文件: {inputs['csv']}")
            return {"csv": pd.read_csv(inputs["csv"])}
        except Exception as e:
            self.logger.error(f"无法读取csv文件: {str(e)}")
            raise e
