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


class LTXVCropGuides(BaseComponent):
    requirements = "torch"
    name = "LTX2引导帧裁剪"
    category = "comfyui节点/LTX模型适配"
    description = "移除 Latent 中用于引导的多余帧，恢复原始长度以便解码。"
    
    inputs = [
        PortDefinition(name="positive", label="正向条件", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="latent", label="LATENT", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
    ]
    outputs = [PortDefinition(name="latent", label="已裁剪LATENT", type=ArgumentType.OBJECT)]

    def run(self, params, inputs):
        import torch
        pos = inputs.get("positive")
        latent = inputs.get("latent")
        
        # 从 Conditioning 中获取 Keyframes 数量
        num_keyframes = 0
        for item in pos:
            if "keyframe_idxs" in item[1] and item[1]["keyframe_idxs"] is not None:
                # 计算唯一开始位置的数量
                coords = item[1]["keyframe_idxs"]
                num_keyframes = torch.unique(coords[:, 0, :, 0]).shape[0]
        
        if num_keyframes == 0:
            return {"latent": latent}

        latent_image = latent["samples"][:, :, :-num_keyframes]
        noise_mask = latent["noise_mask"][:, :, :-num_keyframes] if "noise_mask" in latent else None
        
        return {"latent": {"samples": latent_image, "noise_mask": noise_mask}}