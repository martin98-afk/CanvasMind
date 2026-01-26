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


class LTXVAudioEncoder(BaseComponent):
    requirements = "torchaudio,torch"
    name = "LTX2音频编码器"
    category = "comfyui节点/LTX模型适配"
    description = "将音频文件编码为 LTX2 潜空间特征。用于驱动视频口型和表情。"
    
    inputs = [
         PortDefinition(name="audio_model", label="音频模型", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="audio_latent", label="音频LATENT", type=ArgumentType.OBJECT),
    ]
    properties = {
        "audio_path": PropertyDefinition(type=PropertyType.TEXT, default="", label="音频文件路径"),
    }

    def run(self, params, inputs):
        import torch
        import torchaudio
        audio_model = inputs.get("audio_model")
        path = params.get("audio_path")
        
        if not path:
            raise ValueError("请提供有效的音频路径")

        # 1. 加载音频
        waveform, sample_rate = torchaudio.load(path)
        
        # 2. 音频重采样/预处理 (假设模型需要 16k 或 44.1k)
        # 这里需要根据你加载的具体音频模型进行调整
        self.logger.info(f"正在编码音频: {path}")
        
        # 3. 推理得到 Latent
        with torch.no_grad():
            # 这里的 audio_model 通常是 LTX2 的专用音频编码器
            # 输出形状应匹配视频潜空间的时间步长：[B, 128, F, 1, 1]
            audio_latent_tensor = audio_model.encode(waveform) 
            
        return {"audio_latent": {"samples": audio_latent_tensor}}