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


class ComfyControlNetApply(BaseComponent):
    requirements = "torch,# comfy,# nodes"
    name = "应用ControlNet"
    category = "comfyui节点/基础节点"
    description = "将 ControlNet 应用于提示词条件"

    inputs = [
        PortDefinition(name="positive", label="正向提示词", type=ArgumentType.OBJECT),
        PortDefinition(name="negative", label="负向提示词", type=ArgumentType.OBJECT),
        PortDefinition(name="control_net", label="CONTROL_NET", type=ArgumentType.OBJECT),
        PortDefinition(name="image", label="参考图(IMAGE)", type=ArgumentType.OBJECT), # 通常是预处理过的线稿或深度图
    ]
    outputs = [
        PortDefinition(name="positive", label="正向提示词", type=ArgumentType.OBJECT),
        PortDefinition(name="negative", label="负向提示词", type=ArgumentType.OBJECT),
    ]

    properties = {
        "strength": PropertyDefinition(
            type=PropertyType.RANGE,
            default="1.00",
            label="强度",
            min=0.0,
            max=10.0,
            step=0.01,
        ),
        "start_percent": PropertyDefinition(
            type=PropertyType.RANGE,
            default="0.00",
            label="介入时机(%)",
            min=0.0,
            max=1.0,
            step=0.01,
        ),
        "end_percent": PropertyDefinition(
            type=PropertyType.RANGE,
            default="1.00",
            label="结束时机(%)",
            min=0.0,
            max=1.0,
            step=0.01,
        ),
    }

    def ensure_comfy_exist(self):
        import os, sys
        path = self.global_variable.comfy_extension
        if path not in sys.path:
            sys.path.append(path)
        os.chdir(path)

    def run(self, params, inputs):
        self.ensure_comfy_exist()
        import nodes
        
        positive = inputs.get("positive")
        negative = inputs.get("negative")
        control_net = inputs.get("control_net")
        image = inputs.get("image")
        
        strength = float(params.get("strength", 1.0))
        start = float(params.get("start_percent", 0.0))
        end = float(params.get("end_percent", 1.0))

        applier = nodes.ControlNetApplyAdvanced()
        # 返回 (positive, negative)
        pos_out, neg_out = applier.apply_controlnet(positive, negative, control_net, image, strength, start, end)

        return {
            "positive": pos_out,
            "negative": neg_out
        }