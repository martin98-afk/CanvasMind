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


class ComfyVAEEncode(BaseComponent):
    requirements = "torch,Pillow,numpy,comfy"
    description = ""
    name = "VAE编码器(图生图)"
    category = "comfyui节点/基础节点"
    
    inputs = [
        PortDefinition(name="image", label="IMAGE", type=ArgumentType.IMAGE), # 假设平台输入是 PIL 对象
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT),
    ]
    outputs = [
        PortDefinition(name="latent", label="LATENT", type=ArgumentType.OBJECT),
    ]

    def run(self, params, inputs):
        import torch
        import numpy as np
        from PIL import Image
        vae = inputs.get("vae")
        pil_image = inputs.get("image") # 这里的 pil_image 是 PIL.Image 对象

        if vae is None or pil_image is None:
            raise ValueError("缺少 VAE 模型或图像输入")

        # --- 核心转换逻辑：PIL -> Tensor ---
        
        # 1. 确保图像是 RGB 模式（防止 RGBA 或灰度图报错）
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')

        # 2. 转换为 Numpy 数组并归一化到 0.0 ~ 1.0
        # Numpy 形状: [H, W, C]
        image_np = np.array(pil_image).astype(np.float32) / 255.0

        # 3. 转换为 PyTorch Tensor
        pixels = torch.from_numpy(image_np)

        # 4. 重点：添加 Batch 维度
        # ComfyUI 期待 [Batch, Height, Width, Channels]
        # 转换后形状: [1, H, W, 3]
        pixels = pixels.unsqueeze(0)

        # --- 调用 ComfyUI 编码 ---
        self.logger.info(f"正在进行 VAE 编码，输入张量形状: {pixels.shape}")
        
        # vae.encode 返回的是潜空间张量 [1, 4, H/8, W/8]
        latent_samples = vae.encode(pixels)
        
        # 按照 ComfyUI 标准格式封装返回
        return {"latent": {"samples": latent_samples}}