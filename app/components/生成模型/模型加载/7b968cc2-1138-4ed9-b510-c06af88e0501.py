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


class VAELoader(BaseComponent):
    name = "VAE加载器"
    category = "生成模型/模型加载"
    description = "加载单文件 VAE 权重"
    requirements = "transformers,torch,accelerate,safetensors,diffusers"
    
    outputs = [PortDefinition(name="vae", label="VAE模型", type=ArgumentType.OBJECT)]
    properties = {
        "model_file": PropertyDefinition(type=PropertyType.FILE, default="", label="VAE文件"),
        "config_repo": PropertyDefinition(type=PropertyType.TEXT, default="stabilityai/sd-vae-ft-mse", label="配置源"),
    }

    def run(self, params, inputs=None):
        import torch
        from safetensors.torch import load_file
        from diffusers import AutoencoderKL
        from accelerate import init_empty_weights

        file_path = params.get("model_file")
        config_id = params.get("config_repo")
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        with init_empty_weights():
            vae = AutoencoderKL.from_config(AutoencoderKL.load_config(config_id))
        
        vae = vae.to_empty(device=device)
        state_dict = load_file(file_path, device=str(device))
        
        # VAE 权重有时被包裹在 'vae.' 下
        if any(k.startswith("vae.") for k in state_dict.keys()):
            state_dict = {k.replace("vae.", ""): v for k, v in state_dict.items()}

        vae.load_state_dict(state_dict, strict=False)
        return {"vae": vae.to(torch.float32)} # VAE通常建议用fp32防止溢出