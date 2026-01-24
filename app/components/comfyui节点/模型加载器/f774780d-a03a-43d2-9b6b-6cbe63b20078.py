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


class ComfyGGUFLoader(BaseComponent):
    name = "GGUF模型加载器"
    category = "comfyui节点/模型加载器"
    description = "自动检查并安装 GGUF 插件，然后加载 GGUF 扩散模型"
    requirements = "gguf>=0.13.0,sentencepiece,protobuf,folder_paths,comfy_gguf,torch"
    
    outputs = [
        PortDefinition(name="model", label="MODEL", type=ArgumentType.OBJECT),
    ]
    
    properties = {
        "model_path": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="GGUF模型路径",
        ),
    }

    def run(self, params, inputs=None):
        import os
        import sys
        import torch
        import folder_paths
        sys.path.append(self.global_variable.comfy_extension)
        
        model_path = params.get("model_path")
        if not model_path or not os.path.exists(model_path):
            raise FileNotFoundError(f"找不到 GGUF 模型: {model_path}")

        try:
            # 动态导入刚刚下载好的插件模块
            import comfy_gguf.nodes as nodes_gguf 
            
            # 配置 ComfyUI 寻找模型的路径
            folder_paths.add_model_folder_path("diffusion_models", os.path.dirname(model_path))
            
            self.logger.info(f"正在加载 GGUF 权重: {os.path.basename(model_path)}")
            loader = nodes_gguf.UnetLoaderGGUF()
            result = loader.load_unet(os.path.basename(model_path))
            
            return {"model": result[0]}

        except Exception as e:
            self.logger.error(f"加载 GGUF 时发生异常: {e}")
            raise e