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
ConnectionType = base_module.ConnectionType


class Component(BaseComponent):
    name = "CSV 读取器"
    category = "数据集成"
    description = "接收本地上传csv文件"
    requirements = "pandas"
    inputs = [
        PortDefinition(name="csv", label="csv文件", type=ArgumentType.UPLOAD, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="csv", label="csv文件", type=ArgumentType.CSV),
    ]

    def run(self, params, inputs=None):
        try:
            import pandas as pd
            self.logger.info(inputs)
            self.logger.info(f"开始读取csv文件: {inputs['csv']}")
            return {"csv": pd.read_csv(inputs["csv"])}
        except Exception as e:
            self.logger.error(f"无法读取csv文件: {str(e)}")
            raise e
