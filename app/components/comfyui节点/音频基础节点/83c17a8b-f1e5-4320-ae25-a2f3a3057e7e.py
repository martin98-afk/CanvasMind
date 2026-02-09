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


class VAEDecodeAudio(BaseComponent):
    name = "VAE音频解码"
    category = "comfyui节点/音频基础节点"
    description = "将潜空间解码为音频波形，并进行自动音量标准化"
    requirements = "#comfy,torch"
    inputs = [
        PortDefinition(name="latent", label="潜空间输入", type=ArgumentType.OBJECT),
        PortDefinition(name="vae", label="VAE模型", type=ArgumentType.OBJECT),
    ]
    outputs = [
        PortDefinition(name="audio", label="解码音频", type=ArgumentType.OBJECT),
    ]
    properties = {}

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import torch
        
        latent = inputs.latent
        vae = inputs.vae
        
        if latent is None:
            raise ValueError("潜空间输入不能为空")
        if vae is None:
            raise ValueError("VAE模型输入不能为空")
        
        # 获取潜空间张量
        samples = latent.get("samples")
        if samples is None:
            raise ValueError("潜空间输入缺少samples字段")
        
        # 执行VAE解码（调整维度：[B, T, C] -> [B, C, T]）
        waveform = vae.decode(samples).movedim(-1, 1)
        
        # 音量标准化：基于标准差缩放
        std = torch.std(waveform, dim=[1, 2], keepdim=True) * 5.0
        std = torch.where(std < 1.0, torch.ones_like(std), std)
        waveform = waveform / std
        
        # 保留原始采样率信息（如果存在）
        sample_rate = latent.get("sample_rate", 44100)
        
        return {
            "audio": {
                "waveform": waveform,
                "sample_rate": sample_rate
            }
        }