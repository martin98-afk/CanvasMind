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


class ComfyCLIPLoader(BaseComponent):
    inputs = []
    name = "CLIP加载器"
    category = "comfyui节点/模型加载器"
    description = "加载 CLIP 文本编码器，支持 SD1.5/SDXL/SD3/Flux/LTX 等多种架构"
    requirements = "comfyui,torch,comfy,folder_paths"

    outputs = [
        PortDefinition(name="clip", label="CLIP", type=ArgumentType.OBJECT, sub_type="CLIP"),
    ]

    properties = {
        "clip_name": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="CLIP模型路径",
        ),
        "type": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="stable_diffusion",
            label="模型架构类型",
            choices=["stable_diffusion", "stable_cascade", "sd3", "stable_audio", "mochi", "ltxv", "pixart", "cosmos", "lumina2", "wan", "hidream", "chroma", "ace", "omnigen2", "qwen_image", "hunyuan_image", "flux2", "ovis"]
        ),
        "device": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="default",
            label="加载设备",
            choices=["default", "cpu"]
        ),
    }

    def run(self, params, inputs=None):
        import torch
        import os
        import folder_paths
        import comfy.sd
        
        clip_name = params.get("clip_name", "")
        model_type_str = params.get("type", "stable_diffusion")
        device_mode = params.get("device", "default")

        if not clip_name:
            raise ValueError("CLIP模型路径不能为空")

        # 1. 解析 CLIP 类型枚举
        try:
            clip_type = getattr(comfy.sd.CLIPType, model_type_str.upper())
        except AttributeError:
            self.logger.warning(f"当前 ComfyUI 版本不支持 '{model_type_str}' 类型，回退到 STABLE_DIFFUSION。")
            clip_type = comfy.sd.CLIPType.STABLE_DIFFUSION

        # 2. 设置设备选项
        model_options = {}
        if device_mode == "cpu":
            model_options["load_device"] = model_options["offload_device"] = torch.device("cpu")
            self.logger.info("已启用 CPU 强制加载模式")

        # 3. 路径解析逻辑
        if os.path.isabs(clip_name) and os.path.exists(clip_name):
            clip_path = clip_name
        else:
            try:
                folder_paths.add_model_folder_path("text_encoders", os.path.dirname(clip_name))
            except (ValueError, KeyError):
                if os.path.exists(clip_name):
                    clip_path = clip_name
                else:
                    raise FileNotFoundError(f"未在 models/clip 或 models/text_encoders 中找到模型: {clip_name}")

        self.logger.info(f"正在加载 CLIP: {os.path.basename(clip_path)} (类型: {model_type_str})")

        # 4. 加载模型
        clip = comfy.sd.load_clip(
            ckpt_paths=[clip_name],
            embedding_directory=folder_paths.get_folder_paths("embeddings"),
            clip_type=clip_type,
            model_options=model_options
        )

        return {"clip": clip}