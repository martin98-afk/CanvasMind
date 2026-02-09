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


class ComfyConditioningCombine(BaseComponent):
    requirements = "torch,#comfy,#nodes"
    name = "Comfy条件合并"
    category = "comfyui节点/基础节点"
    description = "将两个 Conditioning 合并 (例如连接多段提示词)"

    inputs = [
        PortDefinition(name="conditioning_1", label="条件1", type=ArgumentType.OBJECT, sub_type="Conditioning", connection=ConnectionType.SINGLE),
        PortDefinition(name="conditioning_2", label="条件2", type=ArgumentType.OBJECT, sub_type="Conditioning", connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="conditioning", label="合并后条件", type=ArgumentType.OBJECT, sub_type="Conditioning"),
    ]
    properties = {}

    def ensure_comfy_exist(self):
        import os, sys
        path = self.global_variable.comfy_extension
        if path not in sys.path:
            sys.path.append(path)
        os.chdir(path)

    def run(self, params, inputs):
        self.ensure_comfy_exist()
        import nodes
        
        cond1 = inputs.get("conditioning_1")
        cond2 = inputs.get("conditioning_2")

        combiner = nodes.ConditioningCombine()
        result = combiner.combine(cond1, cond2)[0]

        return {
            "conditioning": result
        }