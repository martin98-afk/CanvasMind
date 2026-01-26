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


class LTXVAudioVAEEncodeFromFile(BaseComponent):
    requirements = "torchaudio"
    name = "LTX2音频编码(文件输入)"
    category = "comfyui节点/LTX模型适配"
    description = "直接从音频文件读取并编码为 LTX2 潜空间。"
    
    inputs = [
        PortDefinition(name="audio_vae", label="音频VAE", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="audio_file", label="音频文件", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="latent", label="音频LATENT", type=ArgumentType.OBJECT),
    ]
    properties = {
        "audio_file": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="音频文件路径 (FILE)",
        ),
    }

    def run(self, params, inputs):
        import torchaudio
        import os
        audio_vae = inputs.get("audio_vae")
        file_path = params.get("audio_file")
        
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"未找到音频文件: {file_path}")

        # 1. 加载音频文件
        waveform, sample_rate = torchaudio.load(file_path)
        
        # 2. 预处理：重采样到 Audio VAE 要求的采样率
        target_sr = int(audio_vae.sample_rate)
        if sample_rate != target_sr:
            self.logger.info(f"音频重采样: {sample_rate} -> {target_sr}")
            resampler = torchaudio.transforms.Resample(sample_rate, target_sr)
            waveform = resampler(waveform)

        # 3. 调整维度以符合 ComfyUI 音频格式 [Batch, Channels, Samples]
        # 如果是单声道，增加通道维；如果是双声道，保持
        if waveform.ndim == 1:
            waveform = waveform.unsqueeze(0).unsqueeze(0)
        elif waveform.ndim == 2:
            waveform = waveform.unsqueeze(0) # 增加 Batch 维
            
        audio_data = {
            "waveform": waveform,
            "sample_rate": target_sr
        }

        # 4. 调用 VAE 编码
        self.logger.info(f"正在通过 VAE 编码音频潜空间...")
        audio_latents = audio_vae.encode(audio_data)
        
        return {"latent": {
            "samples": audio_latents,
            "sample_rate": target_sr,
            "type": "audio",
        }}