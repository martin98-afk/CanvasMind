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


class Component(BaseComponent):
    name = "Base64 转图片"
    category = "图像处理"
    description = "将 Base64 编码的字符串解码为图像文件"
    requirements = "Pillow"
    inputs = [
        PortDefinition(name="input1", label="Base64 字符串", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output1", label="输出图像", type=ArgumentType.IMAGE),
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

        try:
            # 获取 Base64 字符串
            base64_str = inputs.input1.strip()
            if not base64_str:
                raise ValueError("输入的 Base64 字符串为空")

            # 去除 data URL 前缀（如 data:image/png;base64,）
            if base64_str.startswith("data:"):
                base64_str = base64_str.split(",", 1)[1]

            # 解码 Base64 数据
            img_data = base64.b64decode(base64_str)

            # 使用 BytesIO 创建内存文件流
            img_buffer = BytesIO(img_data)

            # 使用 PIL 打开图像
            image = Image.open(img_buffer)

            # 保存图像对象（支持 PNG、JPEG 等格式）
            # 注意：这里返回的是 Image 对象，框架会自动处理为文件流或下载
            return {
                "output1": image
            }

        except Exception as e:
            self.logger.error(f"Base64 解码失败: {str(e)}")
            raise RuntimeError(f"Base64 转图像失败：{str(e)}")