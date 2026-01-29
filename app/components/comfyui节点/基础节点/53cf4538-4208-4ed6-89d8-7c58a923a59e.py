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


class ComfyLoadImageFromPIL(BaseComponent):
    requirements = "torch,Pillow,numpy"
    name = "图像转tensor"
    category = "comfyui节点/基础节点"
    description = "直接将输入的 PIL Image 转换为 ComfyUI 可用的 Tensor 和 Mask"

    # 输入直接接收一个 PIL Image 对象
    inputs = [
        PortDefinition(name="pil_image", label="输入图像(PIL)", type=ArgumentType.IMAGE),
    ]
    
    # 输出标准的 Comfy 格式
    outputs = [
        PortDefinition(name="image", label="IMAGE", type=ArgumentType.OBJECT),
        PortDefinition(name="mask", label="MASK", type=ArgumentType.OBJECT),
    ]

    properties = {}

    def run(self, params, inputs):
        import torch
        import numpy as np
        from PIL import Image, ImageOps

        # 1. 获取输入对象
        pil_image = inputs.get("pil_image")
        
        if pil_image is None:
            raise ValueError("未接收到有效的 PIL 图像输入")

        # 2. 预处理 (参考 ComfyUI LoadImage 源码逻辑)
        # 修正图片方向 (Exif)
        i = ImageOps.exif_transpose(pil_image)

        # 3. 处理遮罩 (Alpha 通道)
        mask = None
        if 'A' in i.getbands():
            # 提取 Alpha 通道并归一化到 0-1
            mask = np.array(i.getchannel('A')).astype(np.float32) / 255.0
            # ComfyUI 的逻辑：1.0 是遮罩区域(重绘区域)，0.0 是保留区域
            # 原图 Alpha: 1.0 是不透明(保留)，0.0 是透明(重绘)
            # 所以需要反转：mask = 1.0 - alpha
            mask = 1. - torch.from_numpy(mask)
        elif i.mode == 'P' and 'transparency' in i.info:
            mask = np.array(i.convert('RGBA').getchannel('A')).astype(np.float32) / 255.0
            mask = 1. - torch.from_numpy(mask)
        else:
            # 如果没有 Alpha 通道，创建一个全黑(全0)的遮罩，代表全图保留
            # 注意：这里给一个最小尺寸占位，后续节点通常会 resize
            mask = torch.zeros((64, 64), dtype=torch.float32, device="cpu")

        # 4. 处理图像 (RGB)
        image = i.convert("RGB")
        image = np.array(image).astype(np.float32) / 255.0
        # 转换为 Tensor 并增加 Batch 维度: (H, W, C) -> (1, H, W, C)
        image_tensor = torch.from_numpy(image)[None,]

        # 遮罩也需要增加 Batch 维度: (H, W) -> (1, H, W)
        if len(mask.shape) == 2:
            mask = mask.unsqueeze(0)

        return {
            "image": image_tensor,
            "mask": mask
        }