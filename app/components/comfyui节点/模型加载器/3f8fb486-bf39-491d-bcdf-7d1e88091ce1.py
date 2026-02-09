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


class ComfySD3CLIPLoader(BaseComponent):
    inputs = [
    ]
    outputs = [
        PortDefinition(name="clip", label="CLIP", type=ArgumentType.OBJECT, sub_type="CLIP"),
    ]
    description = ""
    requirements = "comfy"
    name = "SD3.5三模型CLIP加载器"
    category = "comfyui节点/模型加载器"
    
    properties = {
        "clip_l": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="CLIP-L 路径",
        ),
        "clip_g": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="CLIP-G 路径",
        ),
        "t5xxl": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="T5XXL 路径",
        ),
    }
    def ensure_comfy_exist(self):
        import os 
        # comfyui节点必须从本地comfy包中读取
        if "comfy_extension" not in self.global_variable.custom:
            raise Exception("自定义全局变量未添加 comfy_extension 参数，无法使用comfy节点。")
        elif not os.path.exists(self.global_variable.comfy_extension):
            raise Exception("配置的 comfy_extension 参数，无法找到本地文件。")
        import sys
        sys.path.append(self.global_variable.comfy_extension)
    
    def run(self, params, inputs=None):
        self.ensure_comfy_exist()
        import comfy.sd
        
        # SD3 必须同时指定三个路径，ComfyUI 才能拼出 2048 维的池化向量
        clip = comfy.sd.load_clip(
            ckpt_paths=[params.get("clip_l"), params.get("clip_g"), params.get("t5xxl")],
            embedding_directory=None,
            clip_type=comfy.sd.CLIPType.SD3 # 明确指定 SD3 类型
        )
        return {"clip": clip}