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
    name = "LTX文本编码器加载"
    category = "comfyui节点/模型加载器"
    description = ""
    requirements = "numpy,comfy,folder_paths,torch"
    inputs = [
    ]
    outputs = [
        PortDefinition(name="clip", label="CLIP", type=ArgumentType.OBJECT),
    ]
    properties = {
        "text_encoder": PropertyDefinition(
            type=PropertyType.FILE,
            default="safetensors",
            label="文本编码器",
        ),
        "ckpt_name": PropertyDefinition(
            type=PropertyType.FILE,
            default="safetensors",
            label="ckpt_name",
        ),
    }
    def run(self, params, inputs):
        import os
        import torch
        import folder_paths
        import comfy.sd
        def get_path(name, folder):
            if os.path.isabs(name) and os.path.exists(name):
                return name
            return folder_paths.get_full_path_or_raise(folder, name)

        clip_type = comfy.sd.CLIPType.LTXV

        # 使用修正后的路径获取函数
        clip_path1 = get_path(params.get("text_encoder"), "text_encoders")
        clip_path2 = get_path(params.get("ckpt_name"), "checkpoints")

        model_options = {}
        if params.get("device") == "cpu":
            model_options["load_device"] = model_options["offload_device"] = torch.device("cpu")

        clip = comfy.sd.load_clip(
            ckpt_paths=[clip_path1, clip_path2], 
            embedding_directory=folder_paths.get_folder_paths("embeddings"), 
            clip_type=clip_type, 
            model_options=model_options
        )
        return {"clip": clip}

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
