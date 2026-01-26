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


class LTXVSeparateAVLatent(BaseComponent):
    name = "LTX2音视频分离"
    category = "comfyui节点/LTX模型适配"
    description = "将合并的 AV Latent 拆分为独立的视频和音频潜空间。"
    
    inputs = [PortDefinition(name="latent", label="合并LATENT", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE)]
    outputs = [
        PortDefinition(name="video_latent", label="视频LATENT", type=ArgumentType.OBJECT),
        PortDefinition(name="audio_latent", label="音频LATENT", type=ArgumentType.OBJECT),
    ]

    def run(self, params, inputs):
        av_latent = inputs.get("latent")
        samples = av_latent["samples"]
        
        if not hasattr(samples, "unbind"):
            # 如果不是嵌套张量，说明可能没音频或已经分离
            return {"video_latent": av_latent, "audio_latent": None}
            
        latents = samples.unbind()
        v_latent = av_latent.copy()
        v_latent["samples"] = latents[0]
        
        a_latent = av_latent.copy()
        a_latent["samples"] = latents[1]
        
        if "noise_mask" in av_latent:
            masks = av_latent["noise_mask"].unbind()
            v_latent["noise_mask"] = masks[0]
            a_latent["noise_mask"] = masks[1]
            
        return {"video_latent": v_latent, "audio_latent": a_latent}