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
    requirements = "torchaudio,TorchCodec,torch,numpy,soundfile"
    name = "LTX2音频编码(文件输入)"
    category = "comfyui节点/LTX模型适配"
    description = "直接从音频文件读取并编码为 LTX2 潜空间。"
    
    inputs = [
        PortDefinition(name="audio_vae", label="音频VAE", type=ArgumentType.OBJECT, sub_type="VAE", connection=ConnectionType.SINGLE),
        PortDefinition(name="audio_file", label="音频文件", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="latent", label="音频LATENT", type=ArgumentType.OBJECT, sub_type="LATENT"),
    ]
    properties = {
    }

    def run(self, params, inputs):
        import torch
        import os
        import numpy as np
        audio_vae = inputs.get("audio_vae")
        file_path = inputs.get("audio_file")
        
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"未找到音频文件: {file_path}")

        target_sr = int(audio_vae.sample_rate)

        # --- 核心修复：使用 soundfile 加载音频 ---
        try:
            import soundfile as sf
            # data 形状通常是 [Samples, Channels]
            data, sample_rate = sf.read(file_path)
            waveform = torch.from_numpy(data).float()
            
            # 转置为 [Channels, Samples]
            if waveform.ndim == 1:
                waveform = waveform.unsqueeze(0) # 单声道 [1, S]
            else:
                waveform = waveform.transpose(0, 1) # 多声道 [C, S]
                
            self.logger.info("使用 soundfile 成功加载音频")
        except Exception as e:
            self.logger.warning(f"soundfile 加载失败，尝试 torchaudio 备选方案: {e}")
            import torchaudio
            waveform, sample_rate = torchaudio.load(file_path)

        # --- 重采样逻辑 ---
        if sample_rate != target_sr:
            import torchaudio.transforms as T
            resampler = T.Resample(sample_rate, target_sr)
            waveform = resampler(waveform)

        # 构建符合 ComfyUI AudioVAE 接口的数据格式
        # AudioVAE.encode 预期输入是 {"waveform": Tensor[B, C, S], "sample_rate": int}
        audio_data = {
            "waveform": waveform.unsqueeze(0), # 增加 Batch 维 -> [1, C, S]
            "sample_rate": target_sr
        }

        self.logger.info(f"正在通过 VAE 编码音频潜空间... 采样率: {target_sr}")
        audio_latents = audio_vae.encode(audio_data)
        
        return {"latent": {
            "samples": audio_latents,
            "sample_rate": target_sr,
            "type": "audio",
        }}