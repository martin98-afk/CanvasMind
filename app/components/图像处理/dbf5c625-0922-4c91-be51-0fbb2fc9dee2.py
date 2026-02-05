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
    name = "图片高级裁切"
    category = "图像处理"
    description = "弹出图片高级裁切交互界面，对图像进行交互式裁切"
    requirements = "Pillow"

    inputs = [
        PortDefinition(name="input_image", label="输入图像", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output_image", label="裁切图像", type=ArgumentType.IMAGE),
    ]
    properties = {

    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import base64
        from io import BytesIO
        from PIL import Image
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
            method="crop_image",
            params={"title": "请拖拽画布以选择最终裁切图像","schema": {"image": base64_image,}}
        )["image"]   # 输出结果会带前缀 data:{mime};base64, 建议后续转换用split(',')获取图像数据
        img_data = base64.b64decode(result.split(",")[1])

        # 使用 BytesIO 创建内存文件流
        img_buffer = BytesIO(img_data)

        # 使用 PIL 打开图像
        image = Image.open(img_buffer)
        
        return {"output_image": image}
