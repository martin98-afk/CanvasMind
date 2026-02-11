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


class ComfyUNETLoader(BaseComponent):
    requirements = "#comfy,torch,#folder_paths"
    name = "Unet加载器"
    category = "comfyui节点/模型加载器"
    description = "加载单独的 Diffusion Model (UNet/DiT)，支持 FP8 量化设置以降低显存占用。"

    inputs = [
    ]

    outputs = [
        PortDefinition(name="model", label="模型", type=ArgumentType.OBJECT, sub_type="MODEL"),
    ]

    properties = {
        "unet_name": PropertyDefinition(
            type=PropertyType.FILE,
            default="safetensors",
            label="模型文件名",
        ),
        "weight_dtype": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="default",
            label="数据类型(量化)",
            choices=["default", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"]
        ),
    }

    def ensure_comfy_exist(self):
        import os, sys
        if hasattr(self, "global_variable") and hasattr(self.global_variable, "comfy_extension"):
            path = self.global_variable.comfy_extension
            if path not in sys.path:
                sys.path.append(path)
                os.chdir(path)

    def run(self, params, inputs):
        self.ensure_comfy_exist()
        import os
        import torch
        import folder_paths
        import comfy.sd

        # 1. 获取参数
        unet_name = params.get("unet_name")
        weight_dtype = params.get("weight_dtype", "default")

        if not unet_name:
            raise ValueError("未指定模型文件名 (unet_name)")

        self.logger.info(f"准备加载模型: {unet_name}, 数据类型: {weight_dtype}")

        # 2. 设置模型加载选项 (核心逻辑)
        model_options = {}
        if weight_dtype == "fp8_e4m3fn":
            model_options["dtype"] = torch.float8_e4m3fn
        elif weight_dtype == "fp8_e4m3fn_fast":
            model_options["dtype"] = torch.float8_e4m3fn
            model_options["fp8_optimizations"] = True
        elif weight_dtype == "fp8_e5m2":
            model_options["dtype"] = torch.float8_e5m2
        
        # 3. 获取路径并加载
        try:
            # ComfyUI 会在 models/diffusion_models 和 models/unet 中查找
            folder_paths.add_model_folder_path("loras", os.path.dirname(unet_name))
            
            model = comfy.sd.load_diffusion_model(unet_name, model_options=model_options)
            
            self.logger.info("模型加载成功")
            
            return {
                "model": model
            }

        except FileNotFoundError:
            self.logger.error(f"找不到模型文件: {unet_name}。请检查文件是否位于 ComfyUI/models/diffusion_models 目录下。")
            raise
        except Exception as e:
            self.logger.error(f"加载模型时发生错误: {e}")
            raise e