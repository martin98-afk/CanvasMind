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


class ComfyWan22VideoLatent(BaseComponent):
    name = "Wan2.2视频潜空间生成"
    category = "comfyui节点/视频生成"
    description = "生成适用于 Wan 2.2 的 48通道、16倍压缩的 5D 视频潜空间"
    requirements = "torch,numpy"

    inputs = [
    ]
    outputs = [
        PortDefinition(name="latent", label="LATENT", type=ArgumentType.OBJECT, sub_type="LATENT"),
    ]

    properties = {
        "widt": PropertyDefinition(
            type=PropertyType.INT,
            default=832,
            label="宽度 (必须是16的倍数)",
        ),
        "heigh": PropertyDefinition(
            type=PropertyType.INT,
            default=480,
            label="高度 (必须是16的倍数)",
        ),
        "length": PropertyDefinition(
            type=PropertyType.INT,
            default=81,
            label="总帧数 (建议81, 121)",
        ),
        "batch_size": PropertyDefinition(
            type=PropertyType.INT,
            default=1,
            label="Batch Size",
        ),
    }

    def run(self, params, inputs=None):
        import torch

        # 1. 获取参数
        width = params.get("widt", 832)
        height = params.get("heigh", 480)
        length = params.get("length", 81)
        batch_size = params.get("batch_size", 1)

        # 2. 【关键】根据 Wan 2.2 的 16倍压缩率计算尺寸
        # 832 // 16 = 52
        # 480 // 16 = 30
        latent_width = width // 16
        latent_height = height // 16
        
        # 3. 时间压缩率保持 (N-1)//4 + 1
        # 81 帧 -> 21 帧潜空间
        latent_length = (length - 1) // 4 + 1

        self.logger.info(f"生成 Wan2.2 专用画布:")
        self.logger.info(f"输入尺寸: {width}x{height}, {length}帧")
        self.logger.info(f"潜空间维度: [Batch:{batch_size}, Channels:48, Frames:{latent_length}, H:{latent_height}, W:{latent_width}]")

        # 4. 创建 48 通道的全零张量
        # 必须是 48 通道，否则 KSampler 必报 Tensor a (16) match Tensor b (48) 错误
        samples = torch.zeros([
            batch_size, 
            48,             # Wan 2.2 核心通道数
            latent_length,  
            latent_height,  
            latent_width    
        ], device="cpu") 

        return {
            "latent": {"samples": samples}
        }