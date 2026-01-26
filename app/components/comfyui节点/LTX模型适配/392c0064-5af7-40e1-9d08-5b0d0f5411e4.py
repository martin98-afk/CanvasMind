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


class LTXVConditioning(BaseComponent):
    requirements = "node_helpers"
    name = "LTX2帧率条件调节"
    category = "comfyui节点/LTX模型适配"
    description = "设置视频的帧率元数据，影响生成动作的节奏。"
    
    inputs = [
        PortDefinition(name="positive", label="正向COND", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="negative", label="负向COND", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="positive", label="正向COND", type=ArgumentType.OBJECT),
        PortDefinition(name="negative", label="负向COND", type=ArgumentType.OBJECT),
    ]
    properties = {
        "frame_rate": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=25.0,
            label="目标帧率",
        ),
    }

    def run(self, params, inputs):
        import node_helpers
        fps = float(params.get("frame_rate", 25.0))
        pos = node_helpers.conditioning_set_values(inputs.get("positive"), {"frame_rate": fps})
        neg = node_helpers.conditioning_set_values(inputs.get("negative"), {"frame_rate": fps})
        return {"positive": pos, "negative": neg}