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


class Component(BaseComponent):
    name = "图像4通道转3通道"
    category = "数据预处理"
    description = ""
    requirements = "numpy"
    inputs = [
        PortDefinition(name="input", label="端口1", type=ArgumentType.IMAGE),
    ]
    outputs = [
        PortDefinition(name="output", label="端口1", type=ArgumentType.IMAGE),
    ]
    properties = {
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import numpy as np
        self.logger.info(np.array(inputs.get("input"))[..., :3].shape)
        return {
            "output": np.array(inputs.get("input"))[..., :3]
        }
