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


class Component(BaseComponent):
    name = "图片转base64编码"
    category = "图像处理"
    description = "将图像对象转换为Base64字符串，支持设置输出格式及压缩质量。"
    requirements = "Pillow"
    inputs = [
        PortDefinition(name="input1", label="输入图片", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output1", label="Base64文本", type=ArgumentType.TEXT),
    ]
    
    # 定义 UI 属性
    properties = {
        "format": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="PNG",
            label="保存格式",
            choices=["PNG", "JPEG", "WEBP"]
        ),
        "quality": PropertyDefinition(
            type=PropertyType.RANGE,
            default="75.0",
            label="图像品质 (仅JPEG/WEBP有效)",
            min=1.0,
            max=100.0,
            step=1.0,
        ),
        "optimize": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="启用压缩优化",
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 包含 format, quality, optimize
        inputs: 包含 input1 (PIL.Image 对象)
        """
        import base64
        from io import BytesIO

        img = inputs.input1
        if img is None:
            return {"output1": ""}

        # 获取参数
        img_format = params.format
        img_quality = int(params.quality)
        img_optimize = params.optimize

        # 处理 JPEG 的透明通道问题（JPEG 不支持 RGBA）
        if img_format == "JPEG" and img.mode in ("RGBA", "P", "LA"):
            # 创建白色背景
            from PIL import Image
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                background.paste(img, mask=img.split()[3]) # 使用 alpha 通道作为掩码
            else:
                background.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[3])
            img = background
        elif img_format == "JPEG" and img.mode != "RGB":
            img = img.convert("RGB")

        buffer = BytesIO()
        
        # 准备保存参数
        save_args = {
            "format": img_format,
            "optimize": img_optimize
        }
        
        # 只有 JPEG 和 WEBP 支持 quality 参数
        if img_format in ["JPEG", "WEBP"]:
            save_args["quality"] = img_quality

        # 保存到内存
        img.save(buffer, **save_args)
        
        # 编码为 base64
        img_bytes = buffer.getvalue()
        base64str = base64.b64encode(img_bytes).decode("utf-8")
        
        # 如果需要带 Data URI 前缀，可以开启下面这行
        # base64str = f"data:image/{img_format.lower()};base64,{base64str}"

        return {
            "output1": base64str
        }