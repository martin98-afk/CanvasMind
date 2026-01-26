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


class LTXVAVLinker(BaseComponent):
    requirements = "# comfy,torch"
    name = "LTX2音视频Latent合并"
    category = "comfyui节点/LTX模型适配"
    description = "将视频潜空间与音频潜空间合并，通过 NestedTensor 传递给模型。"
    
    inputs = [
        PortDefinition(name="video_latent", label="视频Latent", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="audio_latent", label="音频Latent", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="latent", label="合并Latent(AV)", type=ArgumentType.OBJECT),
    ]

    def run(self, params, inputs):
        import torch
        import comfy.nested_tensor
        v_lat = inputs.get("video_latent")
        a_lat = inputs.get("audio_latent")
        
        v_samples = v_lat["samples"]
        a_samples = a_lat["samples"]
        
        v_mask = v_lat.get("noise_mask", torch.ones_like(v_samples[:, :1, :, :, :]))
        a_mask = a_lat.get("noise_mask", torch.ones_like(a_samples[:, :1, :, :, :]))

        # 使用 LTX2 专用的 NestedTensor 结构
        res = {
            "samples": comfy.nested_tensor.NestedTensor((v_samples, a_samples)),
            "noise_mask": comfy.nested_tensor.NestedTensor((v_mask, a_mask))
        }
        return {"latent": res}