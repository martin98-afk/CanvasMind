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


class ComfyGGUFUnetLoader(BaseComponent):
    name = "GGUF Unet模型加载器"
    category = "comfyui节点/模型加载器"
    description = "加载 GGUF 格式的扩散模型(UNet)，支持自定义精度和设备加载策略"
    requirements = "gguf>=0.13.0,sentencepiece,protobuf,# folder_paths,# comfy_gguf,torch"
    
    outputs = [
        PortDefinition(name="model", label="MODEL", type=ArgumentType.OBJECT),
    ]
    
    properties = {
        "model_path": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="GGUF模型文件(.gguf)",
        ),
        "dequant_dtype": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="default",
            label="反量化精度 (Dequant Dtype)",
            choices=["default", "target", "float32", "float16", "bfloat16"]
        ),
        "patch_dtype": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="default",
            label="Patch精度 (Patch Dtype)",
            choices=["default", "target", "float32", "float16", "bfloat16"]
        ),
        "patch_on_device": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="在显存中Patch (Patch on Device)",
        ),
    }

    def run(self, params, inputs=None):
        import os
        import sys
        import folder_paths
        
        # 确保插件目录在 path 中
        if self.global_variable.comfy_extension not in sys.path:
            sys.path.append(self.global_variable.comfy_extension)
            
        model_path = params.get("model_path")
        if not model_path or not os.path.exists(model_path):
            raise FileNotFoundError(f"找不到 GGUF 模型文件: {model_path}")

        try:
            # 导入插件模块
            import comfy_gguf.nodes as nodes_gguf
            
            # 获取参数
            dequant_dtype = params.get("dequant_dtype", "default")
            patch_dtype = params.get("patch_dtype", "default")
            patch_on_device = params.get("patch_on_device", False)
            
            # 注册路径：ComfyUI 需要通过文件名查找，所以我们需要把文件夹加进去
            model_dir = os.path.dirname(model_path)
            model_filename = os.path.basename(model_path)
            
            # 注册 unet_gguf 路径类型 (参考源码 update_folder_names_and_paths)
            folder_paths.add_model_folder_path("unet_gguf", model_dir)
            folder_paths.add_model_folder_path("diffusion_models", model_dir)

            self.logger.info(f"正在加载 GGUF UNet: {model_filename} | Dequant: {dequant_dtype}")
            
            # 使用 Advanced Loader 以支持更多参数
            loader = nodes_gguf.UnetLoaderGGUFAdvanced()
            
            # 调用 load_unet 方法
            result = loader.load_unet(
                unet_name=model_filename,
                dequant_dtype=dequant_dtype,
                patch_dtype=patch_dtype,
                patch_on_device=patch_on_device
            )
            
            return {"model": result[0]}

        except Exception as e:
            self.logger.error(f"加载 GGUF 模型失败: {e}")
            raise RuntimeError(f"GGUF Load Error: {e}")