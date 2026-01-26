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


class LTXVEmptyLatentVideo(BaseComponent):
    requirements = "# comfy,torch"
    name = "LTX2空白视频潜空间"
    category = "comfyui节点/LTX模型适配"
    description = "生成 LTX2 专用的 128 通道视频画布。"
    
    outputs = [PortDefinition(name="latent", label="LATENT", type=ArgumentType.OBJECT)]
    properties = {
        "widt": PropertyDefinition(
            type=PropertyType.INT,
            default=768,
            label="宽",
        ),
        "heigh": PropertyDefinition(
            type=PropertyType.INT,
            default=512,
            label="高",
        ),
        "length": PropertyDefinition(
            type=PropertyType.INT,
            default=97,
            label="帧数(需为8n+1)",
        ),
        "batch_size": PropertyDefinition(
            type=PropertyType.INT,
            default=1,
            label="批次",
        ),
    }

    def run(self, params, inputs):
        import torch
        import comfy.model_management as mm
        width = int(params.get("widt"))
        height = int(params.get("heigh"))
        length = int(params.get("length"))
        batch_size = int(params.get("batch_size"))
        
        # LTX2 下采样倍率为 32 (空间) 和 8 (时间)
        latent = torch.zeros([batch_size, 128, ((length - 1) // 8) + 1, height // 32, width // 32], 
                             device=mm.intermediate_device())
        return {"latent": {"samples": latent}}