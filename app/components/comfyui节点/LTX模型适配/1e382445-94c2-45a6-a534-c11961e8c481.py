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


class ComfyLTXAudioEncode(BaseComponent):
    name = "LTX2音频编码器"
    category = "comfyui节点/LTX模型适配"
    description = "将音频文件转换为 LTX2 潜空间特征"
    requirements = "torchaudio,numpy,comfy,torch"

    inputs = [
        PortDefinition(name="audio_vae", label="AUDIO_VAE", type=ArgumentType.OBJECT),
    ]
    outputs = [
        PortDefinition(name="audio_latent", label="AUDIO_LATENT", type=ArgumentType.OBJECT),
    ]

    properties = {
        "audio_path": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="语音文件 (.wav/.mp3)",
        ),
        "frame_rate": PropertyDefinition(
            type=PropertyType.INT,
            default=16,
            label="对口型视频帧率",
        ),
    }

    def run(self, params, inputs):
        import torch
        import numpy as np
        import librosa  # 使用 librosa 替代 soundfile 和 torchaudio
        import comfy.model_management as mm

        audio_vae = inputs.get("audio_vae")
        audio_path = params.get("audio_path")
        
        if audio_vae is None or not audio_path:
            raise ValueError("音频编码器：缺少 VAE 或音频文件路径")

        self.logger.info(f"正在加载并解析音频: {audio_path}")

        try:
            # --- 核心修复：一行搞定加载、单声道、重采样 ---
            # sr=16000: 强制采样率为 16000Hz (LTX2要求)
            # mono=True: 自动混合多声道为单声道
            waveform_np, sr = librosa.load(audio_path, sr=16000, mono=True)
            
            # 转换为 Tensor 格式 [Channels, Samples] -> [1, L]
            waveform = torch.from_numpy(waveform_np).float().unsqueeze(0)
            
            self.logger.info(f"音频解析成功: {sr}Hz, 持续时间: {len(waveform_np)/sr:.2f}秒")
            
        except Exception as e:
            error_msg = str(e)
            if "No backend" in error_msg or "audioread" in error_msg:
                self.logger.error("缺少 FFmpeg 解码器，无法读取 m4a/mp3 文件！")
                raise RuntimeError("请在环境中执行 'conda install ffmpeg' 以支持该音频格式。")
            else:
                self.logger.error(f"音频解析异常: {error_msg}")
                raise e

        # 2. 显存调度与编码
        
        with torch.no_grad():
            # waveform 需要 [Batch, Channels, Samples] -> [1, 1, L]
            # LTX2 音频 VAE 会输出 [1, C_latent, T_latent]
            self.logger.info("执行音频潜空间 VAE 编码...")
            audio_latent = audio_vae.encode(waveform.unsqueeze(0)) 
            
        return {"audio_latent": audio_latent}