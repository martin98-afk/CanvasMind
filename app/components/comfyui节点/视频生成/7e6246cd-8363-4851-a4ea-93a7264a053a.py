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


class ComfyWanImageToVideo(BaseComponent):
    requirements = "comfy,torch,node_helpers"
    name = "Wan图生视频(Latent版)"
    category = "comfyui节点/视频生成"
    description = "为 Wan (2.0/2.1) 模型准备图生视频条件。自动补齐 Latent 时间轴并生成对应掩码。"

    inputs = [
        PortDefinition(name="positive", label="正向条件", type=ArgumentType.OBJECT, sub_type="Conditioning", connection=ConnectionType.SINGLE),
        PortDefinition(name="negative", label="负向条件", type=ArgumentType.OBJECT, sub_type="Conditioning", connection=ConnectionType.SINGLE),
        PortDefinition(name="start_latent", label="起始 Latent", type=ArgumentType.OBJECT, sub_type="LATENT", connection=ConnectionType.SINGLE),
        PortDefinition(name="clip_vision_output", label="视觉特征", type=ArgumentType.OBJECT, sub_type="LATENT", connection=ConnectionType.SINGLE),
    ]

    outputs = [
        PortDefinition(name="positive", label="正向条件(注入后)", type=ArgumentType.OBJECT, sub_type="Conditioning"),
        PortDefinition(name="negative", label="负向条件(注入后)", type=ArgumentType.OBJECT, sub_type="Conditioning"),
        PortDefinition(name="latent", label="Latent (用于采样)", type=ArgumentType.OBJECT, sub_type="LATENT"),
    ]

    properties = {
        "widt": PropertyDefinition(
            type=PropertyType.INT,
            default=832,
            label="输出宽度",
        ),
        "heigh": PropertyDefinition(
            type=PropertyType.INT,
            default=480,
            label="输出高度",
        ),
        "length": PropertyDefinition(
            type=PropertyType.INT,
            default=81,
            label="总帧数",
        ),
        "batch_size": PropertyDefinition(
            type=PropertyType.INT,
            default=1,
            label="批次大小",
        ),
    }

    def ensure_comfy_exist(self):
        import os, sys
        if hasattr(self, "global_variable") and hasattr(self.global_variable, "comfy_extension"):
            path = self.global_variable.comfy_extension
            if path not in sys.path:
                sys.path.append(path)
                os.chdir(path)

    def run(self, params, inputs):
        self.ensure_comfy_exist()
        import torch
        import torch.nn.functional as F
        import comfy.model_management
        import node_helpers

        positive = inputs.get("positive")
        negative = inputs.get("negative")
        start_latent_input = inputs.get("start_latent")
        clip_vision_output = inputs.get("clip_vision_output")

        width = int(params.get("widt", 832))
        height = int(params.get("heigh", 480))
        length = int(params.get("length", 81))
        batch_size = int(params.get("batch_size", 1))

        if positive is None or negative is None:
            raise ValueError("必须连接正向和负向条件")

        # 1. 初始化目标主 Latent [B, 16, T, H, W]
        t_size = ((length - 1) // 4) + 1
        target_h, target_w = height // 8, width // 8
        device = comfy.model_management.intermediate_device()
        
        latent_tensor = torch.zeros(
            [batch_size, 16, t_size, target_h, target_w], 
            device=device
        )

        # 2. 处理起始 Latent 并注入
        if start_latent_input is not None and "samples" in start_latent_input:
            src_latent = start_latent_input["samples"].to(device)
            
            # 确保维度为 5D [B, C, T, H, W]
            if src_latent.ndim == 4:
                src_latent = src_latent.unsqueeze(2) # [B, 16, 1, H, W]
            
            # --- 关键修复 1: 空间尺寸对齐 (H, W) ---
            # 如果输入的 Latent 宽高与设置不符，进行插值缩放，否则 torch.cat 会报错
            if src_latent.shape[-2:] != (target_h, target_w):
                # F.interpolate 不直接支持 5D 所有的模式，先转为 4D 处理或用 5D 线性
                b, c, t, h, w = src_latent.shape
                src_latent = src_latent.view(b * t, c, h, w)
                src_latent = F.interpolate(src_latent, size=(target_h, target_w), mode="bilinear")
                src_latent = src_latent.view(b, c, t, target_h, target_w)

            # --- 关键修复 2: 时间轴补齐 (T) ---
            # 创建一个与目标 Latent 形状完全一致的“参考图序列”
            full_concat_latent = torch.zeros_like(latent_tensor)
            # 创建对应的掩码 [B, 1, T, H, W]，初始全部为 1.0 (代表需要生成)
            full_mask = torch.ones(
                (batch_size, 1, t_size, target_h, target_w), 
                device=device, dtype=src_latent.dtype
            )

            # 计算可以放入多少帧（不能超过目标总长度）
            available_t = min(src_latent.shape[2], t_size)
            
            # 将输入的 Latent 填入序列开头
            full_concat_latent[:, :, :available_t, :, :] = src_latent[:, :, :available_t, :, :]
            # 将对应帧的掩码设为 0.0 (代表已知内容，不重新生成)
            full_mask[:, :, :available_t, :, :] = 0.0

            # 注入条件
            inject_dict = {
                "concat_latent_image": full_concat_latent, 
                "concat_mask": full_mask
            }
            positive = node_helpers.conditioning_set_values(positive, inject_dict)
            negative = node_helpers.conditioning_set_values(negative, inject_dict)

        # 3. 注入 CLIP Vision 特征
        if clip_vision_output is not None:
            positive = node_helpers.conditioning_set_values(positive, {"clip_vision_output": clip_vision_output})
            negative = node_helpers.conditioning_set_values(negative, {"clip_vision_output": clip_vision_output})

        return {
            "positive": positive,
            "negative": negative,
            "latent": {"samples": latent_tensor}
        }