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
    name = "Wan图生视频(I2V)"
    category = "comfyui节点/视频生成"
    description = "为 Wan (2.0/2.1) 模型准备图生视频条件。初始化 Latent 并注入起始图像(Start Image)和 CLIP Vision 特征。"

    inputs = [
        PortDefinition(name="positive", label="正向条件", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="negative", label="负向条件", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="start_image", label="起始图像", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="clip_vision_output", label="视觉特征", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
    ]

    outputs = [
        PortDefinition(name="positive", label="正向条件(注入后)", type=ArgumentType.OBJECT),
        PortDefinition(name="negative", label="负向条件(注入后)", type=ArgumentType.OBJECT),
        PortDefinition(name="latent", label="Latent", type=ArgumentType.OBJECT),
    ]

    properties = {
        "widt": PropertyDefinition(
            type=PropertyType.INT,
            default=832,
            label="宽度",
        ),
        "heigh": PropertyDefinition(
            type=PropertyType.INT,
            default=480,
            label="高度",
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
        import comfy.model_management
        import comfy.utils
        import node_helpers

        # 1. 获取输入
        positive = inputs.get("positive")
        negative = inputs.get("negative")
        vae = inputs.get("vae")
        start_image = inputs.get("start_image")
        clip_vision_output = inputs.get("clip_vision_output")

        width = int(params.get("widt", 832))
        height = int(params.get("heigh", 480))
        length = int(params.get("length", 81))
        batch_size = int(params.get("batch_size", 1))

        if vae is None:
            raise ValueError("必须连接 VAE 模型")
        if positive is None or negative is None:
            raise ValueError("必须连接正向和负向条件")

        device = comfy.model_management.intermediate_device()

        # 2. 初始化空 Latent
        # Wan 2.0/2.1 特定参数：
        # 通道数: 16
        # 时间压缩: ((length - 1) // 4) + 1
        # 空间压缩: height // 8
        latent_shape = [batch_size, 16, ((length - 1) // 4) + 1, height // 8, width // 8]
        latent = torch.zeros(latent_shape, device=device)

        # 3. 处理起始图像 (图生视频逻辑)
        if start_image is not None:
            self.logger.info(f"处理起始图像... 目标尺寸: {width}x{height}")
            
            # 图像调整尺寸
            # 输入 start_image 通常为 [Batch, H, W, C]
            # movedim(-1, 1) -> [Batch, C, H, W] 用于 interpolation
            resized_image = comfy.utils.common_upscale(
                start_image[:length].movedim(-1, 1), 
                width, 
                height, 
                "bilinear", 
                "center"
            ).movedim(1, -1) # 变回 [Batch, H, W, C]

            # 创建全长视频容器 (灰色填充)
            # 保持与 start_image 相同的 dtype 和 device
            image = torch.ones((length, height, width, resized_image.shape[-1]), 
                               device=resized_image.device, 
                               dtype=resized_image.dtype) * 0.5
            
            # 填入首帧
            image[:resized_image.shape[0]] = resized_image

            # VAE 编码
            # 只取前3个通道(RGB)，忽略可能的 Alpha 通道
            concat_latent_image = vae.encode(image[:, :, :, :3])

            # 创建 Mask
            # 维度对应: [Batch, Channel, Time, Height, Width]
            # Mask 1.0 = 生成/去噪, 0.0 = 保持/条件
            mask = torch.ones(
                (1, 1, latent.shape[2], concat_latent_image.shape[-2], concat_latent_image.shape[-1]), 
                device=resized_image.device, 
                dtype=resized_image.dtype
            )
            
            # 计算起始帧对应的时间步数
            # ((frames - 1) // 4) + 1 是 Wan 的时间下采样公式
            start_frame_count = resized_image.shape[0]
            mask_time_steps = ((start_frame_count - 1) // 4) + 1
            
            # 将起始帧区域的 Mask 设为 0
            mask[:, :, :mask_time_steps] = 0.0

            # 注入到 Conditioning
            # "concat_latent_image" 和 "concat_mask" 是 Wan 模型识别 I2V 条件的特定 Key
            positive = node_helpers.conditioning_set_values(positive, {"concat_latent_image": concat_latent_image, "concat_mask": mask})
            negative = node_helpers.conditioning_set_values(negative, {"concat_latent_image": concat_latent_image, "concat_mask": mask})

        # 4. 处理 CLIP Vision 特征
        if clip_vision_output is not None:
            self.logger.info("注入 CLIP Vision 特征")
            positive = node_helpers.conditioning_set_values(positive, {"clip_vision_output": clip_vision_output})
            negative = node_helpers.conditioning_set_values(negative, {"clip_vision_output": clip_vision_output})

        # 5. 封装返回
        out_latent = {}
        out_latent["samples"] = latent

        return {
            "positive": positive,
            "negative": negative,
            "latent": out_latent
        }