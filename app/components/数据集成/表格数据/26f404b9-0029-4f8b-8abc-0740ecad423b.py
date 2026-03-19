# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py" if (Path(__file__).parent.parent / "base.py").exists() else Path(__file__).parent.parent.parent / "base.py"
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
    name = "CSV读取器"
    category = "数据集成/表格数据"
    description = "CSV读取器需连接文档上传组件作为输入，将文件内容解析为结构化数据流输出，支持单个CSV文件上传输入，输出为CSV格式数据，无额外参数配置。"
    requirements = ""
    inputs = [
        PortDefinition(name="csv", label="csv文件", type=ArgumentType.UPLOAD, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="csv", label="csv文件", type=ArgumentType.CSV),
    ]

    def run(self, params, inputs=None):
        return {"csv": inputs.csv}