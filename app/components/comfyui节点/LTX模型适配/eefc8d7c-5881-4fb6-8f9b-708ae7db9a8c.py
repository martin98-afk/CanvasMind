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


class LTXVSeparateAVLatent(BaseComponent):
    name = "LTX2音视频分离"
    category = "comfyui节点/LTX模型适配"
    description = "将合并的 AV Latent 拆分为独立的视频和音频潜空间。"
    
    inputs = [PortDefinition(name="latent", label="合并LATENT", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE)]
    outputs = [
        PortDefinition(name="video_latent", label="视频LATENT", type=ArgumentType.OBJECT),
        PortDefinition(name="audio_latent", label="音频LATENT", type=ArgumentType.OBJECT),
    ]

    def run(self, params, inputs):
        import torch
        import comfy.nested_tensor
        av_latent = inputs.get("latent")
        if av_latent is None:
            return {"video_latent": None, "audio_latent": None}

        samples = av_latent["samples"]
        
        # 初始化返回结果
        video_latent = av_latent.copy()
        audio_latent = None # 默认音频为空

        # 核心修复：判断是否为真正的 LTX2 嵌套张量 (NestedTensor)
        if isinstance(samples, comfy.nested_tensor.NestedTensor):
            self.logger.info("检测到嵌套张量，正在执行音视频轨道分离...")
            tracks = samples.unbind()
            
            # 视频轨道
            if len(tracks) >= 1:
                video_latent["samples"] = tracks[0]
            
            # 音频轨道
            if len(tracks) >= 2:
                audio_latent = av_latent.copy()
                audio_latent["samples"] = tracks[1]
                # 修改类型标记
                audio_latent["type"] = "audio"
            
            # 处理噪声掩码 (noise_mask 也可能是 NestedTensor)
            if "noise_mask" in av_latent:
                masks = av_latent["noise_mask"]
                if isinstance(masks, comfy.nested_tensor.NestedTensor):
                    mask_tracks = masks.unbind()
                    video_latent["noise_mask"] = mask_tracks[0]
                    if len(mask_tracks) >= 2 and audio_latent:
                        audio_latent["noise_mask"] = mask_tracks[1]
                else:
                    video_latent["noise_mask"] = masks
        else:
            # 如果是标准 Tensor，说明这就是纯视频
            self.logger.info("输入为标准张量，识别为纯视频模式。")
            video_latent["samples"] = samples
            audio_latent = None

        # 确保 video_latent 标记为视频
        video_latent["type"] = "video"

        return {
            "video_latent": video_latent, 
            "audio_latent": audio_latent
        }