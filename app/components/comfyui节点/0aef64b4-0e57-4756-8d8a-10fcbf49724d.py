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


class ComfyKSampler(BaseComponent):
    description = ""
    requirements = "nodes,comfy"
    name = "K采样器"
    category = "comfyui节点"
    
    inputs = [
        PortDefinition(name="model", label="MODEL", type=ArgumentType.OBJECT),
        PortDefinition(name="positive", label="正向提示词", type=ArgumentType.OBJECT),
        PortDefinition(name="negative", label="负向提示词", type=ArgumentType.OBJECT),
        PortDefinition(name="latent", label="Latent", type=ArgumentType.OBJECT),
    ]
    outputs = [
        PortDefinition(name="latent", label="输出Latent", type=ArgumentType.OBJECT),
    ]
    
    def ensure_comfy_exist(self):
        import os 
        # comfyui节点必须从本地comfy包中读取
        if "comfy_extension" not in self.global_variable.custom:
            raise Exception("自定义全局变量未添加 comfy_extension 参数，无法使用comfy节点。")
        elif not os.path.exists(self.global_variable.comfy_extension):
            raise Exception("配置的 comfy_extension 参数，无法找到本地文件。")
        import sys
        sys.path.append(self.global_variable.comfy_extension)
        
    def run(self, params, inputs):
        self.ensure_comfy_exist()
        import comfy.model_management as mm
        import nodes
        # 直接实例化 ComfyUI 的内置节点类
        sampler_node = nodes.KSampler()
        mm.load_models_to_gpu([params.model]) 
        # 调用内置节点的函数
        # ComfyUI 的节点方法通常叫 'sample' 或 'execute'
        result = sampler_node.sample(
            model=inputs.get("model"),
            seed=params.get("seed", 42),
            steps=params.get("steps", 20),
            cfg=params.get("cfg", 7.0),
            sampler_name="euler",
            scheduler="normal",
            positive=inputs.get("positive"),
            negative=inputs.get("negative"),
            latent_image=inputs.get("latent"),
            denoise=0.5
        )
        
        return {"latent": result[0]}