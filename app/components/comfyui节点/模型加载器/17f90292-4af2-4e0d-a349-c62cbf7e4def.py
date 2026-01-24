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


class ComfyLTXAudioVAELoader(BaseComponent):
    requirements = "comfy"
    name = "LTX2音频VAE加载器"
    category = "comfyui节点/模型加载器"
    description = "加载 LTX2 专用的音频 VAE 模型 (修正版)"
    
    outputs = [
        PortDefinition(name="audio_vae", label="AUDIO_VAE", type=ArgumentType.OBJECT),
    ]
    
    properties = {
        "vae_path": PropertyDefinition(
            type=PropertyType.FILE,
            default="safetensors",
            label="音频 VAE 路径 (.safetensors)",
        ),
    }

    def run(self, params, inputs=None):
        import comfy.utils
        import comfy.sd
        import os

        vae_path = params.get("vae_path")
        if not vae_path or not os.path.exists(vae_path):
            raise FileNotFoundError(f"找不到音频 VAE: {vae_path}")

        self.logger.info(f"正在加载 LTX2 音频 VAE: {os.path.basename(vae_path)}")
        
        # 1. 加载权重
        sd = comfy.utils.load_torch_file(vae_path)
        
        # 2. 核心修复：显式指定类型为 "lightricks_audio"
        # 这样 ComfyUI 才会调用对应的架构去解析权重
        try:
            audio_vae = comfy.sd.VAE(sd=sd, type="lightricks_audio")
        except Exception as e:
            self.logger.warning(f"指定类型加载失败，尝试自动识别。错误: {e}")
            audio_vae = comfy.sd.VAE(sd=sd)

        # 3. 验证加载是否成功
        if audio_vae.first_stage_model is None:
            # 尝试处理常见的 Key 前缀问题 (有些模型带 'audio_vae.' 前缀)
            self.logger.info("检测到 VAE 无效，正在尝试移除 Key 前缀并重新加载...")
            new_sd = {}
            for k, v in sd.items():
                new_key = k.replace("audio_vae.", "")
                new_sd[new_key] = v
            audio_vae = comfy.sd.VAE(sd=new_sd, type="lightricks_audio")

        # 最终检查
        if audio_vae.first_stage_model is None:
            raise RuntimeError("无法创建有效的 LTX2 音频 VAE。请确保您的 ComfyUI 源码已更新至支持 LTX2 的最新版本。")

        self.logger.info("✅ LTX2 音频 VAE 加载成功！")
        return {"audio_vae": audio_vae}