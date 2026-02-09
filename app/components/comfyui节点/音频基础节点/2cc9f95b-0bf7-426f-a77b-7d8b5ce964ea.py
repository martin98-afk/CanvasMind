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


class AudioSave(BaseComponent):
    name = "音频保存"
    category = "comfyui节点/音频基础节点"
    description = "将音频对象保存为指定格式的音频文件（支持wav/flac/mp3/opus）"
    requirements = "torchaudio,torch,torchcodec,soundfile"
    inputs = [
        PortDefinition(name="audio", label="音频对象", type=ArgumentType.OBJECT),
    ]
    outputs = [
        PortDefinition(name="file_paths", label="保存路径列表", type=ArgumentType.JSON),
    ]
    properties = {
        "format": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="wav",
            label="音频格式",
            description="输出音频格式",
            choices=["wav", "flac", "mp3", "opus"]
        ),
        "quality": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="128k",
            label="音质",
            description="MP3/Opus格式的比特率或质量等级",
            choices=["64k", "96k", "128k", "192k", "320k", "V0"]
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import os
        import time
        import torch
        
        # 获取音频数据
        audio = inputs.audio
        if audio is None:
            raise ValueError("音频输入不能为空")
        
        waveform = audio.get("waveform")
        sample_rate = audio.get("sample_rate", 44100)
        
        if waveform is None:
            raise ValueError("音频对象缺少waveform字段")
        if not isinstance(waveform, torch.Tensor):
            raise ValueError("waveform必须是torch.Tensor类型")
        
        # 确保sample_rate为整数
        sample_rate = int(sample_rate)
        
        # 处理batch维度：统一为 [B, C, T]
        if waveform.ndim == 2:  # 无batch维度 [C, T]
            waveform = waveform.unsqueeze(0)
        elif waveform.ndim != 3:
            raise ValueError(f"不支持的waveform维度: {waveform.ndim} (应为2或3)")
        
        # 确定输出目录（固定为当前工作目录下的 output 目录）
        base_output_dir = os.path.join(os.getcwd(), "output")
        output_dir = os.path.join(base_output_dir, "audio")
        os.makedirs(output_dir, exist_ok=True)
        
        # 获取格式和音质参数
        format = params.format.lower()
        quality = params.quality
        
        # Opus支持的采样率
        OPUS_RATES = [8000, 12000, 16000, 24000, 48000]
        saved_paths = []
        
        # 遍历每个batch保存音频
        for batch_idx in range(waveform.size(0)):
            # 生成带时间戳的唯一文件名
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"output_audio_{timestamp}_{batch_idx}.wav"  # 初始用wav，后续根据格式修改
            
            # 根据格式调整扩展名
            if format == "flac":
                filename = filename.replace(".wav", ".flac")
            elif format == "mp3":
                filename = filename.replace(".wav", ".mp3")
            elif format == "opus":
                filename = filename.replace(".wav", ".ogg")  # torchaudio要求opus保存为ogg
            
            full_path = os.path.abspath(os.path.join(output_dir, filename))
            
            # 提取当前batch的waveform [C, T]
            batch_wave = waveform[batch_idx].cpu().float()
            
            # 处理opus特殊采样率要求
            current_sample_rate = sample_rate
            current_waveform = batch_wave
            if format == "opus" and sample_rate not in OPUS_RATES:
                # 选择最接近的更高采样率
                higher_rates = [r for r in OPUS_RATES if r > sample_rate]
                current_sample_rate = higher_rates[0] if higher_rates else 48000
                
                # 重采样
                try:
                    import torchaudio
                    current_waveform = torchaudio.functional.resample(
                        batch_wave, sample_rate, current_sample_rate
                    )
                    self.logger.info(
                        f"Opus要求特定采样率，已从{sample_rate}Hz重采样至{current_sample_rate}Hz"
                    )
                except Exception as e:
                    self.logger.warning(f"Opus重采样失败，使用原始采样率: {e}")
                    current_sample_rate = sample_rate
                    current_waveform = batch_wave
            
            # 保存音频（根据格式选择策略）
            saved_successfully = False
            save_error = None
            
            try:
                if format in ["wav", "flac"]:
                    # 优先使用soundfile（无DLL依赖）
                    try:
                        import soundfile as sf
                        waveform_np = current_waveform.numpy().T  # [T, C]
                        sf.write(full_path, waveform_np, current_sample_rate, format=format)
                        saved_successfully = True
                        self.logger.info(f"✓ 音频已保存 (soundfile/{format}): {full_path}")
                    except Exception as sf_err:
                        # soundfile失败，回退到torchaudio
                        self.logger.warning(f"soundfile保存失败，尝试torchaudio: {sf_err}")
                        import torchaudio
                        torchaudio.save(full_path, current_waveform, current_sample_rate, format=format)
                        saved_successfully = True
                        self.logger.info(f"✓ 音频已保存 (torchaudio回退/{format}): {full_path}")
                
                elif format in ["mp3", "opus"]:
                    # MP3/Opus必须使用torchaudio（soundfile不支持编码）
                    import torchaudio
                    # 设置比特率参数（torchaudio 2.1+ 支持）
                    kwargs = {}
                    if format == "mp3":
                        bitrate_map = {"64k": "64k", "96k": "96k", "128k": "128k", 
                                      "192k": "192k", "320k": "320k", "V0": "320k"}
                        kwargs["bits_per_sample"] = 16
                    elif format == "opus":
                        kwargs["encoder"] = "libopus"
                    
                    try:
                        torchaudio.save(full_path, current_waveform, current_sample_rate, format=format, **kwargs)
                        saved_successfully = True
                        self.logger.info(f"✓ 音频已保存 (torchaudio/{format}): {full_path}")
                    except Exception as enc_err:
                        # 编码失败，回退到wav
                        self.logger.warning(
                            f"{format}编码失败（{enc_err}），回退保存为WAV"
                        )
                        fallback_path = full_path.replace(f".{filename.split('.')[-1]}", "_fallback.wav")
                        import soundfile as sf
                        waveform_np = batch_wave.numpy().T
                        sf.write(fallback_path, waveform_np, sample_rate)
                        full_path = fallback_path
                        saved_successfully = True
                        self.logger.info(f"✓ 已回退保存为WAV: {full_path}")
            
            except Exception as e:
                save_error = e
                self.logger.error(f"音频保存失败: {e}")
            
            if saved_successfully:
                # 返回相对于output目录的路径
                saved_paths.append(full_path)
            else:
                raise RuntimeError(f"无法保存音频文件 {full_path}: {save_error}")
        
        if not saved_paths:
            raise RuntimeError("未保存任何音频文件")
        
        return {
            "file_paths": saved_paths
        }