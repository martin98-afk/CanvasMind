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


class ComfyWanMaskGenerator(BaseComponent):
    name = "Wan视频遮罩生成器"
    category = "comfyui节点/视频生成"
    description = "为视频Latent生成时空遮罩，用于保护首尾帧不被重绘(图生视频必备)"
    requirements = "torch,numpy"
    
    inputs = [
        PortDefinition(name="latent", label="视频Latent", type=ArgumentType.OBJECT, sub_type="LATENT", connection=ConnectionType.SINGLE),
        PortDefinition(name="start_frame_latent", label="首帧图像潜变量", type=ArgumentType.OBJECT, sub_type="LATENT", connection=ConnectionType.SINGLE),
        PortDefinition(name="end_frame_latent", label="尾帧图像潜变量", type=ArgumentType.OBJECT, sub_type="LATENT", connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="latent", label="带遮罩Latent", type=ArgumentType.OBJECT, sub_type="LATENT"),
    ]
    
    properties = {
        "fix_middle": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.0,
            label="锁定中间强度(0-1)",
        ),
    }

    def run(self, params, inputs):
        import torch
        
        latent_input = inputs.get("latent")
        # 深度拷贝，防止污染上游节点
        new_latent = {k: v.clone() if isinstance(v, torch.Tensor) else v for k, v in latent_input.items()}
        samples = new_latent["samples"]
        
        start_latent = inputs.get("start_frame_latent")
        end_latent = inputs.get("end_frame_latent")

        # 首尾帧注入逻辑
        if start_latent is not None:
            samples[:, :, 0:1, :, :] = start_latent["samples"]

        if end_latent is not None:
            samples[:, :, -1:, :, :] = end_latent["samples"]
        
        # ====================== 新增：生成时空噪声遮罩 ======================
        # 获取 Latent 的形状 [Batch, Channel, Time, Height, Width]
        B, C, T, H, W = samples.shape
        # 创建一个全为 1 的遮罩 (1表示允许重绘/加满噪声)
        noise_mask = torch.ones((B, T, H, W), dtype=torch.float32, device=samples.device)
        
        # 保护首帧：将第0帧的遮罩设为 0 (0表示锁定，不加噪声)
        if start_latent is not None:
            noise_mask[:, 0, :, :] = 0.0
            
        # 保护尾帧：如果有的话
        if end_latent is not None:
            noise_mask[:, -1, :, :] = 0.0

        # 将组装好的 latent_dict 传入
        latent_dict = {
            "samples": samples,
            "noise_mask": noise_mask  # 传入遮罩
        }

        return {
            "latent": latent_dict
        }