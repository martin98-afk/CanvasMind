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


class LTXVAVLinker(BaseComponent):
    requirements = "# comfy,torch"
    name = "LTX2音视频Latent合并"
    category = "comfyui节点/LTX模型适配"
    description = "将视频潜空间与音频潜空间合并，通过 NestedTensor 传递给模型。"
    
    inputs = [
        PortDefinition(name="video_latent", label="视频Latent", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="audio_latent", label="音频Latent", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="latent", label="合并Latent(AV)", type=ArgumentType.OBJECT),
    ]

    def run(self, params, inputs):
        import torch
        import comfy.nested_tensor
        v_lat = inputs.get("video_latent")
        a_lat = inputs.get("audio_latent")
        
        if v_lat is None or a_lat is None:
            raise ValueError("必须同时连接视频 Latent 和音频 Latent")

        v_samples = v_lat["samples"] # 预期 [B, 128, F, H, W] (5D)
        a_samples = a_lat["samples"] # 预期 [B, C, T, F] (4D)
        
        # --- 核心修复：处理视频掩码 ---
        v_mask = v_lat.get("noise_mask")
        if v_mask is None:
            # 如果没有掩码，生成一个全 1 的掩码（代表全加噪）
            # 视频是 5 维的
            v_mask = torch.ones_like(v_samples)
        
        # --- 核心修复：处理音频掩码 ---
        a_mask = a_lat.get("noise_mask")
        if a_mask is None:
            # 如果没有掩码，生成一个全 1 的掩码
            # 音频是 4 维的，ones_like 会自动匹配维度
            a_mask = torch.ones_like(a_samples)

        self.logger.info(f"正在合并音视频: 视频维度{list(v_samples.shape)}, 音频维度{list(a_samples.shape)}")

        # 使用 LTX2 源码指定的 NestedTensor 结构进行包装
        # 采样器内部会识别这种嵌套结构并分别处理音视频轨道
        res = {
            "samples": comfy.nested_tensor.NestedTensor((v_samples, a_samples)),
            "noise_mask": comfy.nested_tensor.NestedTensor((v_mask, a_mask)),
            "type": "av_combined" # 标记这是一个合并后的张量
        }
        
        return {"latent": res}