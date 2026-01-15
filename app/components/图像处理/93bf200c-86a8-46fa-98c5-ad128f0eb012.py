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
    name = "获取图像遮罩"
    category = "图像处理"
    description = "从RGBA图像中提取透明度通道（A通道）"
    requirements = "numpy,opencv-python"
    inputs = [
        PortDefinition(name="image", label="输入图像", type=ArgumentType.IMAGE),
    ]
    outputs = [
        PortDefinition(name="alpha_channel", label="透明度通道", type=ArgumentType.IMAGE),
    ]
    properties = {
        "output_depth": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="8",
            label="输出深度",
            choices=["8", "16", "32"]
        ),
    }

    def run(self, params, inputs=None):
        """
        从RGBA图像中提取透明度通道
        """
        import cv2
        import numpy as np

        # 获取输入图像
        input_image = np.array(inputs.get("image"))

        # 获取配置参数
        output_depth = int(params.get("output_depth"))

        # 日志记录
        self.logger.info(f"开始处理图像，输出深度: {output_depth}")

        # 确保是RGBA图像
        if len(input_image.shape) < 3 or input_image.shape[2] < 4:
            raise ValueError("输入图像必须是RGBA格式")

        # 提取Alpha通道
        alpha_channel = input_image[:, :, 3]

        # 转换输出深度
        if output_depth == 8:
            alpha_channel = cv2.convertScaleAbs(alpha_channel, alpha=(255.0/255.0))
        elif output_depth == 16:
            alpha_channel = cv2.convertScaleAbs(alpha_channel, alpha=(65535.0/255.0))
        elif output_depth == 32:
            alpha_channel = alpha_channel.astype(np.float32) / 255.0

        return {
            "alpha_channel": alpha_channel
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={"output_depth": "8"},
        inputs={"image": "test_image.png"},
        node_id="alpha_channel_extractor",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True,
        global_vars={}
    )
    print(result)
