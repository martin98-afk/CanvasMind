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


class ComfyLTXVideoLatent(BaseComponent):
    description = ""
    requirements = "torch"
    name = "LTX视频潜空间生成"
    category = "comfyui节点/LTX模型适配"
    
    inputs = [
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
        "length": PropertyDefinition(
            type=PropertyType.INT,
            default=81,
            label="总帧数 (建议81, 121)",
        ),
        "batch_size": PropertyDefinition(
            type=PropertyType.INT,
            default=1,
            label="张数",
        ),
    }
    outputs = [
        PortDefinition(name="latent", label="视频潜空间", type=ArgumentType.OBJECT),
    ]

    def run(self, params, inputs=None):
        import torch
        width = params.get("widt", 864) # LTX建议是32的倍数
        height = params.get("heigh", 480)
        length = params.get("length", 81)

        # 1. 空间 32 倍压缩
        latent_width = width // 32
        latent_height = height // 32
        
        # 2. 时间 8 倍压缩 (LTX 公式: (N-1)//8 + 1)
        latent_length = (length - 1) // 8 + 1

        # 3. 强制 128 通道
        samples = torch.zeros([
            params.get("batch_size", 1), 
            128,            # LTX 核心要求：128通道
            latent_length, 
            latent_height, 
            latent_width
        ], device="cpu")

        return {"latent": {"samples": samples}}