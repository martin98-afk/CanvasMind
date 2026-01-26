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


class LTXVAudioVAELoader(BaseComponent):
    requirements = "folder_paths,comfy"
    name = "LTX2音频VAE加载器"
    category = "comfyui节点/模型加载器"
    description = "加载 LTXV 专用的音频 VAE 模型，用于音频与潜空间的转换。"
    
    outputs = [PortDefinition(name="audio_vae", label="音频VAE", type=ArgumentType.OBJECT)]
    properties = {
        "ckpt_name": PropertyDefinition(
            type=PropertyType.FILE, 
            default="safetensors", 
            label="检查点文件"
        ),
    }

    def run(self, params, inputs):
        import folder_paths
        import comfy.utils
        from comfy.ldm.lightricks.vae.audio_vae import AudioVAE
        ckpt_name = params.get("ckpt_name")
        ckpt_path = folder_paths.get_full_path_or_raise("checkpoints", ckpt_name)
        
        # 加载权重
        sd, metadata = comfy.utils.load_torch_file(ckpt_path, return_metadata=True)
        # 初始化 AudioVAE 对象
        audio_vae_model = AudioVAE(sd, metadata)
        
        return {"audio_vae": audio_vae_model}