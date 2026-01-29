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


class ComfyEmptyLatent(BaseComponent):
    description = ""
    requirements = "torch,#nodes"
    name = "图像空潜空间生成"
    category = "comfyui节点/潜空间处理"
    
    outputs = [
        PortDefinition(name="latent", label="LATENT", type=ArgumentType.OBJECT),
    ]
    
    properties = {
        "widt": PropertyDefinition(
            type=PropertyType.INT,
            default=512,
            label="宽度",
        ),
        "heigh": PropertyDefinition(
            type=PropertyType.INT,
            default=512,
            label="高度",
        ),
        "batch_size": PropertyDefinition(
            type=PropertyType.INT,
            default=1,
            label="张数",
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
        import nodes # 导入 ComfyUI 的节点定义文件
        
        # 1. 实例化 ComfyUI 内置的空潜空间节点
        node = nodes.EmptyLatentImage()
        
        # 2. 调用它的方法 (查看 ComfyUI 源码得知该方法叫 generate)
        # 它会自动处理 height // 8 等逻辑，确保形状是正确的
        result = node.generate(
            width=params.get("width", 512),
            height=params.get("height", 512),
            batch_size=params.get("batch_size", 1)
        )
        
        # result 的格式是 ({"samples": tensor},)
        return {"latent": result[0]}