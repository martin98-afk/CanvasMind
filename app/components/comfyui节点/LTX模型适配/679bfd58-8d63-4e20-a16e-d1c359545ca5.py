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


class LTXVAudioVAEDecodeAndSave(BaseComponent):
    requirements = "torchaudio,torch,numpy,comfy,soundfile"
    name = "LTX2音频解码并保存"
    category = "comfyui节点/LTX模型适配"
    description = "解码音频潜空间并直接保存为本地 .wav 文件。自动处理合并后的 AV 潜空间。"
    
    inputs = [
        PortDefinition(name="latent", label="音频LATENT", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="audio_vae", label="音频VAE", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output_{{now}}.wav", label="保存路径", type=ArgumentType.FILE),
    ]
    def run(self, params, inputs):
        import torch
        import os
        import numpy as np
        import comfy.nested_tensor

        latent_data = inputs.get("latent")
        audio_vae = inputs.get("audio_vae")
        
        if latent_data is None or audio_vae is None:
            raise ValueError("必须连接音频 Latent 和音频 VAE")

        audio_latent = latent_data["samples"]
        
        # 1. 核心修复：如果是 NestedTensor (音视频合并包)，自动提取音频部分
        if isinstance(audio_latent, comfy.nested_tensor.NestedTensor) or (hasattr(audio_latent, "is_nested") and audio_latent.is_nested):
            self.logger.info("检测到合并潜空间，正在提取音频轨道...")
            # unbind()[-1] 提取 LTX2 嵌套张量的最后一项（音频）
            audio_latent = audio_latent.unbind()[-1]
            
        # 2. VAE 解码为波形
        self.logger.info("正在解码音频波形...")
        with torch.no_grad():
            waveform = audio_vae.decode(audio_latent).to(audio_latent.device)
        
        # 3. 准备数据进行保存
        # waveform 预期形状 [Batch, Channels, Samples]
        sample_rate = int(audio_vae.output_sample_rate)
        
        # 移除 Batch 维并转置为 [Samples, Channels] 以适配 soundfile/save 逻辑
        if waveform.ndim == 3:
            waveform_np = waveform[0].cpu().float().numpy().T
        else:
            waveform_np = waveform.cpu().float().numpy().T

        # 4. 处理保存路径
        output_dir = params.get("output_dir", "output/audio")
        filename = params.get("filename", "output.wav")
        if not filename.endswith(".wav"):
            filename += ".wav"
            
        full_path = os.path.join(output_dir, filename)
        os.makedirs(output_dir, exist_ok=True)

        # 5. 执行保存 (优先使用 soundfile 规避 DLL 报错)
        try:
            import soundfile as sf
            sf.write(full_path, waveform_np, sample_rate)
            self.logger.info(f"音频已成功保存至: {full_path}")
        except Exception as e:
            self.logger.warning(f"soundfile 保存失败，尝试 torchaudio: {e}")
            import torchaudio
            # torchaudio 需要 [Channels, Samples]
            torchaudio.save(full_path, torch.from_numpy(waveform_np.T), sample_rate)

        return {"output_{{now}}.wav": open(full_path, 'rb').read()}