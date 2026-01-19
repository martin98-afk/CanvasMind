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


class ControlNetLoader(BaseComponent):
    name = "ControlNet加载器"
    category = "生成模型/模型加载"
    description = "加载单文件 ControlNet 权重"
    requirements = "transformers,torch,accelerate,safetensors,diffusers"
    
    outputs = [PortDefinition(name="controlnet", label="ControlNet", type=ArgumentType.OBJECT)]
    properties = {
        "model_file": PropertyDefinition(type=PropertyType.FILE, default="", label="插件权重文件"),
        "config_repo": PropertyDefinition(type=PropertyType.TEXT, default="lllyasviel/sd-controlnet-canny", label="配置源"),
    }

    def run(self, params, inputs=None):
        import torch
        from safetensors.torch import load_file
        from diffusers import ControlNetModel
        from accelerate import init_empty_weights

        file_path = params.get("model_file")
        config_id = params.get("config_repo")
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        with init_empty_weights():
            # 获取配置，如果 config_id 是文件，尝试加载其同名配置
            config = ControlNetModel.load_config(config_id)
            cnet = ControlNetModel.from_config(config)
        
        cnet = cnet.to_empty(device=device)
        state_dict = load_file(file_path, device=str(device))
        
        # 自动对齐 Key
        cnet.load_state_dict(state_dict, strict=False)
        return {"controlnet": cnet.to(torch.float16)}