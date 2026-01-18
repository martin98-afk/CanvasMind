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


class DynamicComponent(BaseComponent):
    name = "遮罩绘制"
    category = "生成模型/图像重绘"
    description = "运行时会弹出ui提示框，显示图像，供用户进行蒙版绘制，绘制完返回alpha通道图像"
    requirements = "Pillow"

    inputs = [
        PortDefinition(name="input_image", label="输入图像", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="masked_image", label="结果图像", type=ArgumentType.IMAGE),
        PortDefinition(name="image_mask", label="图像蒙版", type=ArgumentType.IMAGE),
    ]
    properties = {
        "show_image": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="是否展示绘制完图像",
        ),
    }

    def run(self, params, inputs):
        # 逻辑处理...
        import base64
        from io import BytesIO
        from PIL import Image, ImageOps
        img = inputs.input_image
        buffered = BytesIO()
        # 自动处理 RGBA 模式保存为 PNG（避免 JPEG 无法保存 alpha）
        format = "PNG"  # 强制含透明通道的图用 PNG
        img.save(buffered, format=format)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        mime = "image/jpeg" if format.upper() in ("JPG", "JPEG") else "image/png"
        base64_image = f"data:{mime};base64,{img_str}"
        # 触发ui出现遮罩绘制窗口
        result = self.emit_interactive_message(
            method="draw_mask",
            params={
                "title": "请绘制图像遮罩",
                "schema": {
                    "image": base64_image,
                }
            }
        )["mask"]
        
        if result.startswith("data:"):
            result = result.split(",", 1)[1]
        img_data = base64.b64decode(result)
        mask_img = Image.open(BytesIO(img_data)).convert("L")  # 灰度图，0=透明，255=绘制
        mask_img = mask_img.point(lambda x: 255 if x > 0 else 0)
        # 将原图 RGBA 拆分为 RGB + A
        rgb_img = img.convert("RGB")
        # 使用 inverted_mask 作为 alpha 通道合成（或直接乘）
        preview_img = Image.composite(
            Image.new("RGB", rgb_img.size, (0, 0, 0)),  # 黑色背景
            rgb_img,
            mask_img  # 未绘制区域保留原图，绘制区域用黑色覆盖
        )
        if params.show_image:
            # 转为 base64 并 emit
            preview_buffer = BytesIO()
            preview_img.save(preview_buffer, format="JPEG", quality=85)
            preview_b64 = base64.b64encode(preview_buffer.getvalue()).decode()
            self.emit_message(
                method="display_image",
                params={"output": {"data": f"data:image/jpeg;base64,{preview_b64}", "data_type": "image"}},
            )
        return {
            "masked_image": preview_img,
            "image_mask": mask_img
        }
