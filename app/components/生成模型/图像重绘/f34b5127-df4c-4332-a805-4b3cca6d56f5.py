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


from io import BytesIO
import base64
from PIL import Image, ImageOps

class DynamicComponent(BaseComponent):
    name = "遮罩绘制"
    category = "生成模型/图像重绘"
    description = "运行时弹出交互窗口，供用户绘制蒙版。返回包含Alpha通道的RGBA图像和单独的Mask。"
    requirements = "Pillow"

    inputs = [
        PortDefinition(name="input_image", label="输入图像", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="masked_image", label="结果图像(RGBA)", type=ArgumentType.IMAGE),
        PortDefinition(name="image_mask", label="图像蒙版", type=ArgumentType.IMAGE),
    ]
    properties = {
        "show_image": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="展示结果预览",
        ),
        "mask_behavior": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="移除绘制内容",
            label="蒙版行为",
            choices=["保留绘制内容", "移除绘制内容"]
        ),
    }

    def _image_to_base64(self, image, fmt="PNG"):
        buffered = BytesIO()
        image.save(buffered, format=fmt)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        mime = "image/png" if fmt.upper() == "PNG" else "image/jpeg"
        return f"data:{mime};base64,{img_str}"

    def run(self, params, inputs):
        img = inputs.input_image
        
        # 1. 准备发送给前端的图片 (转为 Base64)
        # 强制使用 PNG 以保留原图可能存在的 Alpha 通道，防止叠加变黑
        base64_image = self._image_to_base64(img, fmt="PNG")

        # 2. 触发交互式 UI
        result_data = self.emit_interactive_message(
            method="draw_mask",
            params={
                "title": "请绘制图像遮罩",
                "schema": {
                    "image": base64_image,
                }
            }
        )
        
        # 获取回传的 mask 字符串
        mask_b64 = result_data.get("mask")
        if not mask_b64:
            raise ValueError("未接收到有效的蒙版数据")

        if mask_b64.startswith("data:"):
            mask_b64 = mask_b64.split(",", 1)[1]
        
        # 3. 处理回传的 Mask
        mask_bytes = base64.b64decode(mask_b64)
        # 前端通常回传的是一张背景透明、笔触有颜色的 PNG
        raw_mask = Image.open(BytesIO(mask_bytes))
        
        # 【关键步骤】强制将 Mask 缩放到原图尺寸，防止前端缩放导致的尺寸不匹配
        if raw_mask.size != img.size:
            raw_mask = raw_mask.resize(img.size, Image.LANCZOS)

        # 提取 Alpha 通道作为 Mask (假设笔触是不透明的)
        # 如果回传的是单纯的黑白图，则用 convert("L")
        if 'A' in raw_mask.getbands():
            mask_img = raw_mask.getchannel('A')
        else:
            mask_img = raw_mask.convert("L")

        # 二值化处理，确保蒙版边缘清晰（可选，根据需求调整阈值）
        mask_img = mask_img.point(lambda x: 255 if x > 0 else 0)

        # 4. 构建输出的 RGBA 图像
        # 确保原图是 RGB 模式
        rgb_img = img.convert("RGB")
        
        # 根据参数决定 Alpha 行为
        final_alpha = mask_img
        if params.mask_behavior == "移除绘制内容":
            # 如果选择"移除绘制区域"，则反转 Mask (255 -> 0)
            final_alpha = ImageOps.invert(mask_img)
        
        # 合成 RGBA：原图色彩 + 蒙版透明度
        masked_image_rgba = rgb_img.copy()
        masked_image_rgba.putalpha(final_alpha)

        # 5. 展示预览
        if params.show_image:
            # 预览必须用 PNG，否则 JPEG 会把透明背景变成黑色
            preview_b64 = self._image_to_base64(masked_image_rgba, fmt="PNG")
            self.emit_message(
                method="display_image",
                params={"output": preview_b64},
            )

        return {
            "masked_image": masked_image_rgba, # 这是一个真正的 RGBA 图像
            "image_mask": mask_img             # 这是一个灰度图 Mask (L模式)
        }