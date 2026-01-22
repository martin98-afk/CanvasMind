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


class Component(BaseComponent):
    name = "ComfyUI模型加载器"
    category = "Comfyui节点/模型加载"
    description = "使用 ComfyUI 后端加载 Checkpoint (.safetensors/.ckpt)"
    requirements = "numpy,folder_paths,comfy"
    inputs = [
    ]
    
    outputs = [
        PortDefinition(name="model", label="MODEL", type=ArgumentType.OBJECT),
        PortDefinition(name="clip", label="CLIP", type=ArgumentType.OBJECT),
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT),
    ]
    
    properties = {
        "ckpt_path": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="模型绝对路径",
        ),
    }

    def run(self, params, inputs=None):
        import os
        import sys
        sys.path.append(params.comfy_path)
        import comfy
        import folder_paths
        ckpt_path = params.get("ckpt_path")
        if not os.path.exists(ckpt_path):
            raise FileNotFoundError(f"找不到模型: {ckpt_path}")

        self.logger.info(f"ComfyUI 正在解析模型: {ckpt_path}")
        
        # 调用 ComfyUI 的核心加载函数
        # 它会自动识别是 SD1.5, SDXL 还是其他，并返回封装好的 Patcher 对象
        out = comfy.sd.load_checkpoint_guess_config(
            ckpt_path, 
            output_vae=True, 
            output_clip=True, 
            embedding_directory=folder_paths.get_folder_paths("embeddings")
        )
        
        # out 的结构是 (model, clip, vae, clipvision)
        return {
            "model": out[0],
            "clip": out[1],
            "vae": out[2]
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={"prop1": "test"},
        inputs={"input1": "output"},
        node_id="测试模型",
        show_input_types = True,
        show_output_types = True,
        show_execution_time = True,
        global_vars = {}
    )
    print(result)
