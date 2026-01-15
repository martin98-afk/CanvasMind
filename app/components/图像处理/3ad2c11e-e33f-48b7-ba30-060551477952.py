# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py"
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


class ImagePadForOutpainting(BaseComponent):
    name = "图像扩图填充"
    category = "图像处理"
    description = "为图像添加边距，生成用于扩图的画布和遮罩"
    requirements = "Pillow"
    
    inputs = [
        PortDefinition(name="image", label="输入图像", type=ArgumentType.IMAGE),
    ]
    outputs = [
        PortDefinition(name="padded_image", label="扩图画布", type=ArgumentType.IMAGE),
        PortDefinition(name="mask", label="遮罩图", type=ArgumentType.IMAGE),
    ]
    
    properties = {
        "left": PropertyDefinition(
            type=PropertyType.INT,
            default=0,
            label="左扩展",
        ),
        "right": PropertyDefinition(
            type=PropertyType.INT,
            default=0,
            label="右扩展",
        ),
        "top": PropertyDefinition(
            type=PropertyType.INT,
            default=0,
            label="上扩展",
        ),
        "bottom": PropertyDefinition(
            type=PropertyType.INT,
            default=0,
            label="下扩展",
        ),
        "feathering": PropertyDefinition(
            type=PropertyType.INT,
            default=20,
            label="边缘羽化",
        ),
    }

    def run(self, params, inputs=None):
        from PIL import Image, ImageFilter
        img = inputs.get("image")
        
        left = int(params.get("left", 0))
        right = int(params.get("right", 0))
        top = int(params.get("top", 0))
        bottom = int(params.get("bottom", 0))
        
        # 1. 创建新画布
        new_width = img.width + left + right
        new_height = img.height + top + bottom
        
        # 扩图背景通常设为黑色或图像边缘延伸
        padded_img = Image.new("RGB", (new_width, new_height), (0, 0, 0))
        padded_img.paste(img, (left, top))
        
        # 2. 创建遮罩 (扩出的部分为白色 255，原有部分为黑色 0)
        mask = Image.new("L", (new_width, new_height), 255)
        # 将原始图片位置设为黑色（表示不重绘）
        mask.paste(Image.new("L", (img.width, img.height), 0), (left, top))
        
        # 3. 边缘羽化（可选，为了让过渡更自然）
        if params.get("feathering") > 0:
            mask = mask.filter(ImageFilter.GaussianBlur(params.get("feathering")))

        return {
            "padded_image": padded_img,
            "mask": mask
        }