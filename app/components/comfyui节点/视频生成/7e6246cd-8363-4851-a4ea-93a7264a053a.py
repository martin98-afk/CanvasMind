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

        atent = torch.zeros([batch_size, 16, ((length - 1) // 4) + 1, height // 8, width // 8], device=comfy.model_management.intermediate_device())
        if start_image is not None:
            start_image = comfy.utils.common_upscale(start_image[:length].movedim(-1, 1), width, height, "bilinear", "center").movedim(1, -1)
            image = torch.ones((length, height, width, start_image.shape[-1]), device=start_image.device, dtype=start_image.dtype) * 0.5
            image[:start_image.shape[0]] = start_image

            concat_latent_image = vae.encode(image[:, :, :, :3])
            mask = torch.ones((1, 1, latent.shape[2], concat_latent_image.shape[-2], concat_latent_image.shape[-1]), device=start_image.device, dtype=start_image.dtype)
            mask[:, :, :((start_image.shape[0] - 1) // 4) + 1] = 0.0

            positive = node_helpers.conditioning_set_values(positive, {"concat_latent_image": concat_latent_image, "concat_mask": mask})
            negative = node_helpers.conditioning_set_values(negative, {"concat_latent_image": concat_latent_image, "concat_mask": mask})

        if clip_vision_output is not None:
            positive = node_helpers.conditioning_set_values(positive, {"clip_vision_output": clip_vision_output})
            negative = node_helpers.conditioning_set_values(negative, {"clip_vision_output": clip_vision_output})

        out_latent = {}
        out_latent["samples"] = latent

        return {
            "positive": positive,
            "negative": negative,
            "latent": out_latent
        }