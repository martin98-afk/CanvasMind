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


class VAEEncodeAudio(BaseComponent):
    name = "VAE音频编码"
    category = "comfyui节点/音频基础节点"
    description = "将音频波形编码为潜空间表示，自动重采样至44100Hz"
    requirements = "torch,torchaudio"
    inputs = [
        PortDefinition(name="audio", label="音频对象", type=ArgumentType.OBJECT),
        PortDefinition(name="vae", label="音频VAE", type=ArgumentType.OBJECT),
    ]
    outputs = [
        PortDefinition(name="latent", label="编码潜空间", type=ArgumentType.OBJECT),
    ]
    properties = {}

    def run(self, params, inputs=None):
        """ 
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import torch
        import torchaudio
        
        audio = inputs.audio
        vae = inputs.vae
        
        if audio is None:
            raise ValueError("音频输入不能为空")
        if vae is None:
            raise ValueError("VAE模型输入不能为空")
        
        # 获取音频数据
        waveform = audio.get("waveform")
        sample_rate = audio.get("sample_rate", 44100)
        
        if waveform is None:
            raise ValueError("音频对象缺少waveform字段")
        if not isinstance(waveform, torch.Tensor):
            raise ValueError("waveform必须是torch.Tensor类型")
        
        # 重采样至44100Hz（VAE训练采样率）
        target_sample_rate = 44100
        if sample_rate != target_sample_rate:
            self.logger.info(f"重采样音频: {sample_rate}Hz → {target_sample_rate}Hz")
            waveform = torchaudio.functional.resample(
                waveform, float(sample_rate), float(target_sample_rate)
            )
            current_sample_rate = target_sample_rate
        else:
            current_sample_rate = sample_rate
        
        # 调整维度以适配VAE编码器: [B, C, T] → [B, T, C]
        # ComfyUI音频VAE期望输入形状为 [batch, time, channels]
        waveform_for_vae = waveform.movedim(1, -1)
        
        # 执行VAE编码
        try:
            latent_tensor = vae.encode(waveform_for_vae)
        except Exception as e:
            # 尝试兼容不同VAE实现（部分实现可能不需要维度调整）
            if "shape" in str(e).lower() or "dimension" in str(e).lower():
                self.logger.warning(f"标准维度编码失败，尝试原始维度: {e}")
                latent_tensor = vae.encode(waveform)
            else:
                raise RuntimeError(f"VAE编码失败: {e}")
        
        # 构建标准潜空间对象（与ComfyUI兼容）
        latent = {
            "samples": latent_tensor,
            "sample_rate": current_sample_rate,  # 保留采样率信息供后续使用
            "type": "audio"
        }
        
        self.logger.info(
            f"✓ VAE编码成功 | "
            f"输入形状: {list(waveform.shape)} → "
            f"潜空间形状: {list(latent_tensor.shape)}"
        )
        
        return {
            "latent": latent
        }