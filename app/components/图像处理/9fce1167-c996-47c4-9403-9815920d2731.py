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
    name = "多边形框选"
    category = "图像处理"
    description = "弹出多边形框选弹窗，可以在图片上点击框选多边形"
    requirements = ""

    inputs = [
        PortDefinition(name="image", label="图像", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
        PortDefinition(name="polygons", label="多边形框", type=ArgumentType.JSON, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="polygons", label="多边形框", type=ArgumentType.JSON),
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
        img = inputs.image
        polygons = inputs.polygons
        buffered = BytesIO()
        # 自动处理 RGBA 模式保存为 PNG（避免 JPEG 无法保存 alpha）
        format = "PNG"  # 强制含透明通道的图用 PNG
        img.save(buffered, format=format)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        mime = "image/jpeg" if format.upper() in ("JPG", "JPEG") else "image/png"
        base64_image = f"data:{mime};base64,{img_str}"
        result = self.emit_interactive_message(
            method="anchor_selector",
            params={
                "title": "请选择关键点锚点",
                "schema": {
                    "image": base64_image,
                    "polygons": polygons
                }
            }
        )["polygons"]
        return {
            "polygons": result
        }
