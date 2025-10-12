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
    name = "文件转图片"
    category = "数据转换"
    description = ""
    requirements = "Pillow"
    inputs = [
        PortDefinition(name="file", label="端口1", type=ArgumentType.UPLOAD),
    ]
    outputs = [
        PortDefinition(name="image", label="端口1", type=ArgumentType.IMAGE),
    ]
    properties = {
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        self.logger.info(inputs)
        from PIL import Image
        return {
            "image": Image.open(inputs.get("file"))
        }
