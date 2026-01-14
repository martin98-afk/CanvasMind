# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py"
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


class LatentUpscaleComponent(BaseComponent):
    name = "潜空间放大"
    category = "生成模型"
    description = "对 Latent 进行数学空间放大，用于高清修复的中间步骤"
    requirements = "torch,numpy"

    inputs = [
        PortDefinition(name="latent_in", label="潜空间输入", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="latent_out", label="潜空间输出", type=ArgumentType.ARRAY),
    ]

    properties = {
        "upscale_method": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="bicubic",
            label="放大算法",
            choices=["nearest", "linear", "bilinear", "bicubic", "area"]
        ),
        "scale_factor": PropertyDefinition(
            type=PropertyType.RANGE,
            default="2.0",
            label="放大倍数",
            min=1.0,
            max=4.0,
            step=0.1,
        ),
        "align_corners": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="对齐对角线",
        ),
    }

    def run(self, params, inputs=None):
        import torch
        import torch.nn.functional as F
        import numpy as np

        latent_ndarray = inputs.get("latent_in")
        if latent_ndarray is None:
            raise ValueError("未接收到潜空间输入")

        scale_factor = float(params.get("scale_factor", 2.0))
        method = params.get("upscale_method", "bicubic")
        align_corners = params.get("align_corners", False)

        # 1. 转换回 Tensor [Batch, Channel, Height, Width]
        # 假设输入是 K 采样器输出的 Numpy 数组
        latents = torch.from_numpy(latent_ndarray).to("cuda")

        # 2. 执行插值放大
        # 对于 Latent 空间，bicubic 和 nearest 是最常用的
        if method in ["nearest", "area"]:
            upscaled_latents = F.interpolate(
                latents, 
                scale_factor=scale_factor, 
                mode=method
            )
        else:
            upscaled_latents = F.interpolate(
                latents, 
                scale_factor=scale_factor, 
                mode=method, 
                align_corners=align_corners
            )

        self.logger.info(f"Latent 放大完成: 从 {latents.shape[-2:]} 变为 {upscaled_latents.shape[-2:]}")

        return {
            "latent_out": upscaled_latents.cpu().numpy()
        }