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


class ComfyCheckpointLoader(BaseComponent):
    inputs = [
    ]
    requirements = "#comfy,#folder_paths,torch"
    name = "Checkpoint加载器"
    category = "comfyui节点/模型加载器"
    description = "加载单文件检查点(.safetensors/.ckpt)，自动识别并拆分 MODEL, CLIP 和 VAE。"
    
    outputs = [
        PortDefinition(name="model", label="MODEL", type=ArgumentType.OBJECT, sub_type="MODEL"),
        PortDefinition(name="clip", label="CLIP", type=ArgumentType.OBJECT, sub_type="CLIP"),
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT, sub_type="VAE"),
    ]
    
    properties = {
        "ckpt_name": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="检查点文件",
            description="The name of the checkpoint (model) to load.",
        ),
    }

    def run(self, params, inputs):
        import os
        import torch
        import folder_paths
        import comfy.sd
        import comfy.utils
        ckpt_name = params.get("ckpt_name")
        
        # 1. 获取模型绝对路径
        if os.path.isabs(ckpt_name) and os.path.exists(ckpt_name):
            ckpt_path = ckpt_name
        else:
            ckpt_path = folder_paths.get_full_path_or_raise("checkpoints", ckpt_name)

        self.logger.info(f"正在加载检查点: {ckpt_path}")

        # 2. 调用源码中的核心加载函数
        try:
            out = comfy.sd.load_checkpoint_guess_config(
                ckpt_path, 
                output_vae=True, 
                output_clip=True, 
                embedding_directory=folder_paths.get_folder_paths("embeddings")
            )
        except Exception as e:
            self.logger.error(f"模型加载失败: {str(e)}")
            raise e

        if out is None:
            raise RuntimeError(f"无法识别该模型的配置: {ckpt_path}")

        model, clip, vae, _ = out

        # 3. 输出结果
        return {
            "model": model,
            "clip": clip,
            "vae": vae
        }