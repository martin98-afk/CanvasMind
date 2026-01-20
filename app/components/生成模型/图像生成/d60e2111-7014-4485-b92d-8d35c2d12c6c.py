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


class VAEEncoderDecoder(BaseComponent):
    requirements = "torch,numpy,Pillow"
    name = "VAE编解码器(模型输入)"
    category = "生成模型/图像生成"
    description = "Latent 与 Image 之间的转换"
    
    inputs = [
        PortDefinition(name="vae", label="VAE模型", type=ArgumentType.OBJECT),
        PortDefinition(name="latent", label="潜空间数据", type=ArgumentType.OBJECT),
        PortDefinition(name="image", label="输入图像(用于编码)", type=ArgumentType.IMAGE),
    ]
    properties = {
        "mode": PropertyDefinition(type=PropertyType.CHOICE, default="decode", choices=["encode", "decode"], label="模式"),
    }
    outputs = [
        PortDefinition(name="image", label="图像", type=ArgumentType.IMAGE),
        PortDefinition(name="latent", label="潜空间", type=ArgumentType.OBJECT),
    ]

    def run(self, params, inputs=None):
        import torch
        import numpy as np
        from PIL import Image
        
        vae = inputs.get("vae")
        mode = params.get("mode")

        if mode == "decode":
            latent = inputs.get("latent")
            if latent is None: raise ValueError("解码模式需要潜空间输入")
            
            # VAE 解码公式: image = vae.decode(latent / 0.18215).sample
            with torch.no_grad():
                # 某些模型系数不同，SD1.5 默认为 0.18215
                latents = latent / 0.18215
                image = vae.decode(latents).sample

            # 后处理
            image = (image / 2 + 0.5).clamp(0, 1)
            image = image.cpu().permute(0, 2, 3, 1).numpy()[0]
            image = (image * 255).astype(np.uint8)
            return {"image": Image.fromarray(image)}

        else: # encode 模式
            pil_img = inputs.get("image")
            if pil_img is None: raise ValueError("编码模式需要图像输入")
            
            img_np = np.array(pil_img.convert("RGB")).astype(np.float32) / 255.0
            img_tensor = torch.from_numpy(img_np).permute(2, 0, 1).unsqueeze(0).to(vae.device)
            img_tensor = (img_tensor * 2) - 1 # 归一化到 [-1, 1]

            with torch.no_grad():
                latent = vae.encode(img_tensor).latent_dist.sample()
                latent = latent * 0.18215
            
            return {"latent": latent}