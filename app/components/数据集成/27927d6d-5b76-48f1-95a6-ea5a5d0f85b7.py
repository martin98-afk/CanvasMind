# -*- coding: utf-8 -*-
import importlib.util
import pathlib
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
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
    name = "文档上传"
    category = "数据集成"
    description = "接收本地上传文件"
    outputs=[PortDefinition(name="file", label="csv文件", type=ArgumentType.FILE)]

    def run(self, params, inputs=None):
        pass
