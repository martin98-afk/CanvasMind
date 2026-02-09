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
    requirements = "comfy,torch,torchaudio"
    inputs = [
        PortDefinition(name="audio", label="音频输入", type=ArgumentType.OBJECT),
        PortDefinition(name="vae", label="VAE模型", type=ArgumentType.OBJECT),
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
        import torchaudio
        
        audio = inputs.audio
        vae = inputs.vae
        
        if audio is None:
            raise ValueError("音频输入不能为空")
        if vae is None:
            raise ValueError("VAE模型输入不能为空")
        
        # 获取音频数据和采样率
        waveform = audio.get("waveform")
        sample_rate = audio.get("sample_rate", 44100)
        
        if waveform is None:
            raise ValueError("音频输入缺少waveform字段")
        
        # 重采样至44100Hz（如果需要）
        if sample_rate != 44100:
            waveform = torchaudio.functional.resample(waveform, sample_rate, 44100)
        
        # 执行VAE编码（调整维度：[B, C, T] -> [B, T, C]）
        latent_tensor = vae.encode(waveform.movedim(1, -1))
        
        return {
            "latent": {"samples": latent_tensor}
        }
