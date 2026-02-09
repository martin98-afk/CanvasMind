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


class ComfyLoadImage(BaseComponent):
    name = "加载图像"
    category = "comfyui节点/基础节点"
    description = "加载图像文件，支持多帧(GIF/WebP)及自动Mask提取"
    requirements = "torch,numpy,pillow,# folder_paths"

    inputs = [
        PortDefinition(name="image", label="输入图像", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]
    
    outputs = [
        PortDefinition(name="image", label="IMAGE", type=ArgumentType.OBJECT, sub_type="IMAGE"),
        PortDefinition(name="mask", label="MASK", type=ArgumentType.OBJECT, sub_type="MASK"),
    ]

    properties = {
    }

    def run(self, params, inputs=None):
        import torch
        import numpy as np
        from PIL import Image, ImageOps, ImageSequence
        import os

        # 假设环境中有 folder_paths，如果没有需根据实际环境调整
        try:
            import folder_paths
        except ImportError:
            folder_paths = None

        # 1. 获取文件名参数
        image_name = str(inputs.get("image", "example.png"))
        # 2. 解析文件路径
        # 注意：这里依赖 ComfyUI 的 folder_paths 模块
        # 如果在非 ComfyUI 环境运行，需要手动指定 image_path
        if folder_paths:
            image_path = folder_paths.get_annotated_filepath(image_name)
        else:
            # 简单的回退逻辑，假设在当前目录或 input 目录下
            if os.path.exists(image_name):
                image_path = image_name
            elif os.path.exists(os.path.join("input", image_name)):
                image_path = os.path.join("input", image_name)
            else:
                raise FileNotFoundError(f"找不到图像文件: {image_name}")

        self.logger.info(f"正在加载图像: {image_path}")

        # 3. 打开图像 (替换原有的 node_helpers.pillow 包装，直接使用 PIL)
        img = Image.open(image_path)

        output_images = []
        output_masks = []
        w, h = None, None

        # 4. 遍历帧 (处理静态图或 GIF/WebP)
        for i in ImageSequence.Iterator(img):
            # 处理 EXIF 旋转
            i = ImageOps.exif_transpose(i)

            # 处理 16-bit 灰度图 (Mode 'I')
            if i.mode == 'I':
                i = i.point(lambda i: i * (1 / 255))
            
            # 转换为 RGB 用于图像输出
            image = i.convert("RGB")

            # 记录第一帧尺寸，后续帧必须一致
            if len(output_images) == 0:
                w = image.size[0]
                h = image.size[1]

            if image.size[0] != w or image.size[1] != h:
                continue

            # 图像归一化 [0, 1] 并转 Tensor (HWC -> NHWC)
            image_np = np.array(image).astype(np.float32) / 255.0
            image_tensor = torch.from_numpy(image_np)[None,]
            
            # 5. Mask 提取逻辑 (Alpha 通道)
            if 'A' in i.getbands():
                # 有 Alpha 通道
                mask_np = np.array(i.getchannel('A')).astype(np.float32) / 255.0
                mask = 1. - torch.from_numpy(mask_np) # ComfyUI 习惯 Mask 是反转的 (1=遮挡?) 或根据具体需求调整
            elif i.mode == 'P' and 'transparency' in i.info:
                # 调色板模式且有透明度信息
                mask_np = np.array(i.convert('RGBA').getchannel('A')).astype(np.float32) / 255.0
                mask = 1. - torch.from_numpy(mask_np)
            else:
                # 无 Alpha，创建全 0 (黑色) Mask，尺寸设为 64x64 (节省内存，ComfyUI 会自动 resize)
                mask = torch.zeros((64, 64), dtype=torch.float32, device="cpu")
            
            output_images.append(image_tensor)
            output_masks.append(mask.unsqueeze(0))

            # MPO 格式只取第一帧
            if getattr(img, "format", "") == "MPO":
                break 

        # 6. 堆叠 Tensor
        if len(output_images) > 1:
            output_image = torch.cat(output_images, dim=0)
            output_mask = torch.cat(output_masks, dim=0)
        else:
            output_image = output_images[0]
            output_mask = output_masks[0]

        self.logger.info(f"图像加载完成. Shape: {output_image.shape}")

        return {
            "image": output_image,
            "mask": output_mask
        }