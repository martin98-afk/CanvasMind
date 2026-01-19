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


class SetLatentNoiseMask(BaseComponent):
    requirements = "torch,numpy,Pillow"
    name = "设置潜空间噪波遮罩"
    category = "生成模型/图像重绘"
    description = "将遮罩绑定到潜空间数据上，用于局部重绘"
    
    inputs = [
        PortDefinition(name="samples", label="潜空间数据", type=ArgumentType.OBJECT),
        PortDefinition(name="mask", label="遮罩图像", type=ArgumentType.IMAGE),
    ]
    outputs = [
        PortDefinition(name="samples", label="带遮罩潜空间", type=ArgumentType.OBJECT),
    ]

    def run(self, params, inputs=None):
        import torch
        import numpy as np
        from PIL import Image

        samples = inputs.get("samples")
        mask_img = inputs.get("mask")

        if samples is None or mask_img is None:
            return {"samples": samples}

        # 1. 确保 samples 是 Tensor [B, C, H, W]
        # 如果是 ComfyUI 风格的字典，我们需要提取 ['samples']
        latent_tensor = samples if isinstance(samples, torch.Tensor) else samples.get("samples")
        
        # 2. 预处理遮罩：缩放到 Latent 的大小
        lat_h, lat_w = latent_tensor.shape[-2:]
        mask_resized = mask_img.convert("L").resize((lat_w, lat_h), Image.BILINEAR)
        
        # 3. 转为 Tensor 并归一化 [1, 1, H, W]
        mask_tensor = torch.from_numpy(np.array(mask_resized)).to(torch.float32) / 255.0
        mask_tensor = mask_tensor.unsqueeze(0).unsqueeze(0)

        # 4. 封装成 ComfyUI 风格的对象
        output = {
            "samples": latent_tensor,
            "noise_mask": mask_tensor # 关键：将遮罩作为附件携带
        }

        return {"samples": output}