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


class ImageResizer(BaseComponent):
    name = "图像尺寸调整"
    category = "图像处理"
    description = "调整图像尺寸，支持比例保持和YOLO风格填充"
    requirements = "Pillow>=9.0.0"

    inputs = [
        PortDefinition(name="image", label="输入图像", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="resized_image", label="调整尺寸后的图像", type=ArgumentType.IMAGE),
    ]

    properties = {
        "w": PropertyDefinition(
            type=PropertyType.INT,
            default=512,
            label="目标宽度",
        ),
        "h": PropertyDefinition(
            type=PropertyType.INT,
            default=512,
            label="目标高度",
        ),
        "keep_ratio": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="保持比例",
        ),
        "fill_color": PropertyDefinition(
            type=PropertyType.TEXT,
            default="black",
            label="填充颜色",
        ),
    }

    def run(self, params, inputs=None):
        """
        实现图像尺寸调整功能，支持比例保持和YOLO风格填充

        参数:
            params: 包含以下属性:
                - w: 目标宽度 (int)
                - h: 目标高度 (int)
                - keep_ratio: 是否保持比例 (bool)
                - fill_color: 填充颜色 (str)
            inputs: 包含:
                - image: PIL.Image 对象

        返回: 
            resized_image: 调整后的图像对象
        """
        try:
            from PIL import Image, ImageOps

            # 获取原始尺寸
            original_image = inputs.image
            original_width, original_height = original_image.size

            # 计算目标尺寸
            target_w, target_h = self._calculate_target_size(
                original_width, original_height, 
                params.w, params.h, params.keep_ratio
            )

            # 执行图像调整
            resized_image = original_image.resize(
                (target_w, target_h), 
                Image.Resampling.BILINEAR
            )

            # 如果需要填充到目标尺寸
            if target_w != params.w or target_h != params.h:
                # 计算填充偏移
                offset_x = (params.w - target_w) // 2
                offset_y = (params.h - target_h) // 2

                # 创建填充图像
                resized_image = ImageOps.pad(
                    resized_image, 
                    (params.w, params.h), 
                    color=params.fill_color
                )

            return {
                "resized_image": resized_image
            }

        except Exception as e:
            self.logger.error(f"图像调整失败: {str(e)}")
            raise

    def _calculate_target_size(self, w, h, target_w, target_h, keep_ratio):
        """根据比例计算目标尺寸"""
        if not keep_ratio:
            return target_w, target_h

        # 计算原始宽高比
        aspect_ratio = w / h

        # 计算目标宽高比
        target_ratio = target_w / target_h

        # 根据比例调整尺寸
        if aspect_ratio > target_ratio:
            # 宽度优先：保持宽度，计算高度
            new_w = target_w
            new_h = int(target_w / aspect_ratio)
        else:
            # 高度优先：保持高度，计算宽度
            new_h = target_h
            new_w = int(target_h * aspect_ratio)

        return new_w, new_h

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")

    # 测试用例示例
    model = ImageResizer()
    result = model.debug(
        params={
            "w": 640,
            "h": 640,
            "keep_ratio": True,
            "fill_color": "black"
        },
        inputs={
            "image": "test.png"
        },
        global_vars={},
        node_id="resize_node"
    )
    print(result)
