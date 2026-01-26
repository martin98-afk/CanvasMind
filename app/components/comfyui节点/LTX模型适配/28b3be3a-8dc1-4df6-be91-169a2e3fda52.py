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


class LTXVImageToVideoConditioner(BaseComponent):
    requirements = "# comfy,torch"
    name = "LTX2图生视频注入"
    category = "comfyui节点/LTX模型适配"
    description = "将参考图注入到潜空间的首帧，并生成噪声掩码。"
    
    inputs = [
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="image", label="参考图像", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
        PortDefinition(name="latent", label="画布LATENT", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="latent", label="已注入LATENT", type=ArgumentType.OBJECT),
    ]
    properties = {
        "strength": PropertyDefinition(
            type=PropertyType.RANGE,
            default="1.00",
            label="首帧保持强度",
            min=0.0,
            max=1.0,
            step=0.01,
        ),
    }

    def run(self, params, inputs):
        import torch
        import comfy.utils
        vae = inputs.get("vae")
        image = inputs.get("image") # 假设为 [B, H, W, C] 或 [B, C, H, W]
        latent = inputs.get("latent")
        strength = float(params.get("strength", 1.0))
        
        samples = latent["samples"].clone()
        batch, _, latent_frames, latent_height, latent_width = samples.shape
        
        # 内部缩放以匹配 latent
        width = latent_width * 32
        height = latent_height * 32
        
        # 转换并缩放图像
        pixels = image.movedim(-1, 1) # to BCHW
        pixels = comfy.utils.common_upscale(pixels, width, height, "bilinear", "center").movedim(1, -1)
        encode_pixels = pixels[:, :, :, :3]
        
        # VAE 编码
        t = vae.encode(encode_pixels) # 返回 [B, 128, 1, H//32, W//32]
        
        # 注入到第一帧
        samples[:, :, :t.shape[2]] = t
        
        # 生成 Noise Mask (0 代表保留原图, 1 代表加噪生成)
        mask = torch.ones((batch, 1, latent_frames, 1, 1), device=samples.device)
        mask[:, :, :t.shape[2]] = 1.0 - strength
        
        return {"latent": {"samples": samples, "noise_mask": mask}}