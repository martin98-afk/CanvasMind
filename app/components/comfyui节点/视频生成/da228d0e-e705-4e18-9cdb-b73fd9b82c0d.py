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


class ComfyWan21VideoLatent(BaseComponent):
    name = "Wan2.1视频潜空间生成"
    category = "comfyui节点/视频生成"
    description = "生成适用于 Wan 2.1 的 16通道、8倍压缩的 5D 视频潜空间"
    requirements = "torch,numpy"

    inputs = []
    outputs = [
        PortDefinition(name="latent", label="LATENT", type=ArgumentType.OBJECT),
    ]

    properties = {
        "width": PropertyDefinition(
            type=PropertyType.INT,
            default=832,
            label="宽度 (必须是16的倍数)",
        ),
        "height": PropertyDefinition(
            type=PropertyType.INT,
            default=480,
            label="高度 (必须是16的倍数)",
        ),
        "length": PropertyDefinition(
            type=PropertyType.INT,
            default=81,
            label="总帧数 (建议 81, 121)",
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
        width = params.get("width", 832)
        height = params.get("height", 480)
        length = params.get("length", 81)
        batch_size = params.get("batch_size", 1)

        # 2. 【关键】根据 Wan 2.1 的 VAE 规格计算尺寸
        # Wan 2.1 的空间压缩率通常为 8 (Stride 8)
        # 832 // 8 = 104
        # 480 // 8 = 60
        latent_width = width // 8
        latent_height = height // 8
        
        # 3. 时间压缩率保持 (N-1)//4 + 1
        # Wan 2.1 和 2.2 在时间维度通常保持一致的 Stride 4
        latent_length = (length - 1) // 4 + 1

        self.logger.info(f"生成 Wan2.1 专用画布:")
        self.logger.info(f"输入尺寸: {width}x{height}, {length}帧")
        self.logger.info(f"潜空间维度: [Batch:{batch_size}, Channels:16, Frames:{latent_length}, H:{latent_height}, W:{latent_width}]")

        # 4. 创建 16 通道的全零张量
        # Wan 2.1 (如 T2V-14B) 使用 16 通道 VAE
        samples = torch.zeros([
            batch_size, 
            16,             # Wan 2.1 核心差异：16通道
            latent_length,  
            latent_height,  
            latent_width    
        ], device="cpu") 

        return {
            "latent": {"samples": samples}
        }