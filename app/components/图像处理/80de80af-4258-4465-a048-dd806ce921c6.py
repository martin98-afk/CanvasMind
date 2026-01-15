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
    name = "图片转array"
    category = "图像处理"
    description = "将输入的图片转换为 NumPy 数组格式"
    requirements = "numpy, pillow"
    inputs = [
        PortDefinition(name="image", label="输入图片", type=ArgumentType.IMAGE),
    ]
    outputs = [
        PortDefinition(name="array", label="NumPy数组", type=ArgumentType.ARRAY),
    ]
    properties = {}

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import numpy as np
        from PIL import Image

        # 获取输入图片（PIL Image 或路径）
        input_image = inputs.image

        # 如果传入的是文件路径（str），则打开；如果是 PIL.Image.Image，则直接使用
        if isinstance(input_image, str):
            image = Image.open(input_image)
        elif isinstance(input_image, Image.Image):
            image = input_image
        else:
            raise ValueError("输入图片格式不支持，应为 PIL.Image 或图片路径")

        # 转换为 RGB（避免 RGBA 或灰度图导致 shape 不一致）
        image = image.convert("RGB")

        # 转为 NumPy 数组
        array = np.array(image)

        self.logger.info(f"图片已转换为数组，shape: {array.shape}")

        return {
            "array": array  # CanvasMind ARRAY 类型期望 list 形式
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={},
        inputs={"image": "example.jpg"},  # 可替换为实际图片路径或 PIL.Image 对象
        global_vars={},
        node_id="test_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)
