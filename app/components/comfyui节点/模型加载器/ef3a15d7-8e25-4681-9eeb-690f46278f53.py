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


class ComfyLoraLoader(BaseComponent):
    requirements = "torch,#comfy,#nodes,folder_paths"
    name = "Lora加载器"
    category = "comfyui节点/模型加载器"
    description = "加载 Lora 并应用到 Model 和 CLIP"

    inputs = [
        PortDefinition(name="model", label="MODEL", type=ArgumentType.OBJECT),
        PortDefinition(name="clip", label="CLIP", type=ArgumentType.OBJECT),
    ]
    outputs = [
        PortDefinition(name="model", label="MODEL", type=ArgumentType.OBJECT),
        PortDefinition(name="clip", label="CLIP", type=ArgumentType.OBJECT),
    ]

    properties = {
        "lora_name": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="Lora文件名",
        ),
        "strength_model": PropertyDefinition(
            type=PropertyType.RANGE,
            default="1.0",
            label="模型强度",
            min=-10.0,
            max=10.0,
            step=0.1,
        ),
        "strength_clip": PropertyDefinition(
            type=PropertyType.RANGE,
            default="1.0",
            label="CLIP强度",
            min=-10.0,
            max=10.0,
            step=0.1,
        ),
    }

    def ensure_comfy_exist(self):
        import os, sys
        path = self.global_variable.comfy_extension
        if path not in sys.path:
            sys.path.append(path)
        os.chdir(path)

    def run(self, params, inputs):
        self.ensure_comfy_exist()
        import os
        import comfy
        import nodes
        import folder_paths
        
        model = inputs.get("model")
        clip = inputs.get("clip")
        
        lora_name = params.get("lora_name")
        strength_model = float(params.get("strength_model", 1.0))
        strength_clip = float(params.get("strength_clip", 1.0))

        if strength_model == 0 and strength_clip == 0:
            return {
            "model": model,
            "clip": clip
        }
        folder_paths.add_model_folder_path("loras", os.path.dirname(os.path.abspath(lora_name)))
        lora = comfy.utils.load_torch_file(lora_name, safe_load=True)
        model_lora, clip_lora = comfy.sd.load_lora_for_models(
            model, clip, lora, strength_model, strength_clip
        )
        return {
            "model": model_lora,
            "clip": clip_lora
        }