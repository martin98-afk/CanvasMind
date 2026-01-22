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


class ComfyWanImageEncode(BaseComponent):
    requirements = "torch,numpy,Pillow"
    name = "Wan图像编码器"
    category = "comfyui节点/视频生成"
    description = "将图片自动缩放到视频尺寸并使用 Wan VAE 编码"
    
    inputs = [
        PortDefinition(name="image", label="IMAGE", type=ArgumentType.IMAGE),
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT),
        PortDefinition(name="video_latent", label="参考视频Latent", type=ArgumentType.OBJECT), # 连空潜空间节点
    ]
    outputs = [
        PortDefinition(name="latent", label="LATENT", type=ArgumentType.OBJECT),
    ]

    def run(self, params, inputs):
        import torch
        import numpy as np
        from PIL import Image
        
        vae = inputs.get("vae")
        pil_img = inputs.get("image")
        video_latent = inputs.get("video_latent")
        
        if any(x is None for x in [vae, pil_img, video_latent]):
            raise ValueError("缺少输入：请确保连接了 VAE、图片和视频空潜空间")

        # 1. 自动获取视频潜空间的目标尺寸
        # Target shape: [B, 16, F, H_latent, W_latent]
        target_h_latent = video_latent["samples"].shape[3]
        target_w_latent = video_latent["samples"].shape[4]
        
        # 换算回像素尺寸
        target_width = target_w_latent * 16
        target_height = target_h_latent * 16

        self.logger.info(f"正在自动缩放图片至视频尺寸: {target_width}x{target_height}")

        # 2. 缩放图片
        pil_img = pil_img.resize((target_width, target_height), Image.LANCZOS)

        # 3. 转换为 Tensor [B, H, W, C]
        img_np = np.array(pil_img).astype(np.float32) / 255.0
        pixel_tensor = torch.from_numpy(img_np).unsqueeze(0) # [1, H, W, 3]

        # 4. 使用 VAE 编码
        with torch.no_grad():
            # 这里必须确保使用的是 Wan 2.1 的 VAE
            latent_samples = vae.encode(pixel_tensor)
            
            # 5. 维度修正：确保输出是 5D [B, 16, 1, H, W]
            if latent_samples.ndim == 4:
                # [1, 16, 60, 104] -> [1, 16, 1, 60, 104]
                latent_samples = latent_samples.unsqueeze(2)
            
            # 强制清理显存
            import gc
            gc.collect()

        self.logger.info(f"编码完成，最终形状: {latent_samples.shape}")

        return {"latent": {"samples": latent_samples}}