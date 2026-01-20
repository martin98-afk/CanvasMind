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


class UNETLoader(BaseComponent):
    name = "UNET加载器"
    category = "生成模型/模型加载"
    description = "加载单文件 UNET/Transformer 权重"
    requirements = "transformers,torch,accelerate,safetensors,diffusers"
    
    outputs = [PortDefinition(name="model", label="UNET模型", type=ArgumentType.OBJECT)]
    properties = {
        "model_file": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="模型文件 (.safetensors)",
        ),
        "config_repo": PropertyDefinition(
            type=PropertyType.TEXT,
            default="runwayml/stable-diffusion-v1-5",
            label="架构配置源",
        ),
        "precision": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="fp16",
            label="精度",
            choices=["fp16", "bf16", "fp32"]
        ),
    }

    def run(self, params, inputs=None):
        import torch
        from safetensors.torch import load_file
        # 移除了 AutoConfig，改用类自带的 load_config
        from diffusers import UNet2DConditionModel, SD3Transformer2DModel, FluxTransformer2DModel
        from accelerate import init_empty_weights

        file_path = params.get("model_file")
        config_id = params.get("config_repo")
        subfolder = params.get("subfolder", "unet")
        dtype = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}[params.get("precision")]
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # 1. 动态获取配置
        # 这里使用 UNet2DConditionModel 作为通用配置入口，或者根据 config_id 判断
        try:
            # 尝试加载配置字典
            config_dict = UNet2DConditionModel.load_config(config_id, subfolder=subfolder)
            model_class_name = config_dict.get("_class_name", "UNet2DConditionModel")
            
            # 根据配置中的类名选择正确的类
            if "Flux" in model_class_name:
                model_class = FluxTransformer2DModel
            elif "SD3" in model_class_name:
                model_class = SD3Transformer2DModel
            else:
                model_class = UNet2DConditionModel
                
            with init_empty_weights():
                model = model_class.from_config(config_dict)
        except Exception as e:
            self.logger.error(f"配置加载失败: {e}")
            raise e
        
        # 2. 这里的后续逻辑（to_empty 和 load_state_dict）保持不变...
        model = model.to_empty(device=device)
        state_dict = load_file(file_path, device=str(device))
        
        # 自动剥离前缀
        prefix = "model.diffusion_model."
        new_state_dict = {}
        for k, v in state_dict.items():
            new_key = k.replace(prefix, "") if k.startswith(prefix) else k
            new_state_dict[new_key] = v
            
        model.load_state_dict(new_state_dict, strict=False)
        return {"model": model.to(dtype)}