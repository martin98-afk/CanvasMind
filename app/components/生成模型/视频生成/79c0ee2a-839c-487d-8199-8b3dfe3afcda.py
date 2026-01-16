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


class WanVAEDecodeComponent(BaseComponent):
    description = ""
    requirements = "numpy,torch"
    name = "Wan VAE 解码"
    category = "生成模型/视频生成"
    
    inputs = [
        PortDefinition(name="vae", label="vae", type=ArgumentType.OBJECT),
        PortDefinition(name="latents", label="潜空间输入", type=ArgumentType.OBJECT),
    ]
    
    outputs = [
        PortDefinition(name="frames", label="像素帧序列", type=ArgumentType.OBJECT),
    ]

    def run(self, params, inputs=None):
        import torch
        import numpy as np

        vae = inputs["vae"]
        latents = inputs["latents"]
        
        # 显存优化：开启分块解码
        vae.enable_tiling()

        self.logger.info("VAE 解码中...")
        with torch.no_grad():
            # Wan VAE 解码
            video = vae.decode(latents, return_dict=False)[0]
            
            # 转换格式 [B, C, F, H, W] -> [F, H, W, C]
            video = (video / 2 + 0.5).clamp(0, 1)
            video = video[0].cpu().float().numpy()
            video = np.transpose(video, (1, 2, 3, 0))
            
            frames = (video * 255).astype(np.uint8)

        return {"frames": frames}