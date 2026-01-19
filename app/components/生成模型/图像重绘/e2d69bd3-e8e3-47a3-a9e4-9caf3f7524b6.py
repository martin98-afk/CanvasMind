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


class MaskPreprocess(BaseComponent):
    requirements = "numpy,Pillow"
    name = "遮罩预处理"
    category = "生成模型/图像重绘"
    description = "对遮罩进行扩张(Grow)和模糊(Blur)，使重绘边缘更自然"
    
    inputs = [
        PortDefinition(name="mask", label="输入遮罩", type=ArgumentType.IMAGE),
    ]
    outputs = [
        PortDefinition(name="mask", label="处理后的遮罩", type=ArgumentType.IMAGE),
    ]
    properties = {
        "expand": PropertyDefinition(type=PropertyType.INT, default=6, label="扩张像素(Grow)"),
        "blur": PropertyDefinition(type=PropertyType.INT, default=6, label="模糊半径(Blur)"),
    }

    def run(self, params, inputs=None):
        from PIL import Image, ImageFilter, ImageOps
        import numpy as np
        
        mask = inputs.get("mask")
        if mask is None: return {"mask": None}
        
        # 确保是 L 模式 (黑白)
        mask = mask.convert("L")
        
        expand = params.get("expand", 0)
        blur = params.get("blur", 0)
        
        # 1. Expand (扩张) - 使用形态学膨胀逻辑
        if expand > 0:
            # 使用 PIL 的 MaxFilter 模拟 Mask Grow
            mask = mask.filter(ImageFilter.MaxFilter(expand * 2 + 1))
            
        # 2. Blur (模糊)
        if blur > 0:
            mask = mask.filter(ImageFilter.GaussianBlur(radius=blur))
            
        return {"mask": mask}