# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py"
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


class DynamicComponent(BaseComponent):
    name = "图像resize"
    category = "数据处理"
    description = "由用户动态生成的组件"
    requirements = "Pillow"

    inputs = [
        PortDefinition(name="input1", label="input1", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output1", label="output1", type=ArgumentType.IMAGE),
    ]
    properties = {
        "w": PropertyDefinition(
            type=PropertyType.INT,
            default=512,
            label="调整后宽",
        ),
        "h": PropertyDefinition(
            type=PropertyType.INT,
            default=512,
            label="调整后高",
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        from PIL import Image
        return {
            "output1": inputs.input1.resize((params.w, params.h), Image.Resampling.NEAREST)
        }
