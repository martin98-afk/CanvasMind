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
    name = "YOLO目标检测及关键点检测"
    category = "目标检测"
    description = "使用YOLOv8模型进行目标检测和关键点检测"
    requirements = "ultralytics,opencv-python,numpy,pillow"
    inputs = [
        PortDefinition(name="input_image", label="输入图像", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
        PortDefinition(name="model", label="模型文件", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="detections", label="检测结果", type=ArgumentType.JSON),
        PortDefinition(name="keypoints", label="关键点信息", type=ArgumentType.JSON),
        PortDefinition(name="output_image", label="标注图像", type=ArgumentType.IMAGE),
    ]
    properties = {
        "device": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="cpu",
            label="运行设备",
            choices=["cpu", "cuda"]
        ),
        "conf_threshold": PropertyDefinition(
            type=PropertyType.RANGE,
            default="0.50",
            label="置信度阈值",
            min=0.0,
            max=1.0,
            step=0.05,
        ),
        "iou_threshold": PropertyDefinition(
            type=PropertyType.RANGE,
            default="0.70",
            label="NMS IoU阈值",
            min=0.0,
            max=1.0,
            step=0.05,
        ),
    }

    def load_model(self, model_name: str, device: str):
        from ultralytics import YOLO
        self.model = YOLO(model_name)
        self.device = device
        self.logger.info(f"YOLO model {model_name} loaded on {self.device}")

    def run(self, params, inputs=None):
        from ultralytics import YOLO
        from PIL import Image
        import numpy as np
        import io
        import base64
        import cv2

        # 加载模型
        self.load_model(inputs.model, params.device)

        # 获取输入图像
        input_image = inputs.input_image
        if input_image is None:
            raise ValueError("未提供图像！")

        # 转换为PIL图像
        if isinstance(input_image, str):
            # 如果是Base64字符串，转换为PIL图像
            from io import BytesIO
            image_data = base64.b64decode(input_image)
            input_image = Image.open(BytesIO(image_data))

        # 执行推理
        results = self.model.predict(source=input_image, device=params.device, conf=params.conf_threshold, iou=params.iou_threshold)

        # 解析结果
        detections = []
        keypoints = []
        annotated_image = None

        for result in results:
            # 绘制标注图像
            annotated_image = result.plot()

            # 解析检测结果
            for box in result.boxes:
                # 检测框信息
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cls = box.cls[0].item()
                conf = box.conf[0].item()

                # 添加检测框信息
                detections.append({
                    "bbox": [x1, y1, x2, y2],
                    "class": cls,
                    "confidence": conf
                })
            if result.keypoints is not None:
                for keypoint in result.keypoints:
                    # 关键点信息
                    points = keypoint.xy[0].tolist()
                    kps = {f"keypoint_{i}": [x, y] for i, (x, y) in enumerate(points)}
                    keypoints.append({
                        "keypoints": kps
                    })

        return {
            "detections": detections,
            "keypoints": keypoints,
            "output_image": annotated_image
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={
            "device": "cpu",
            "conf_threshold": 0.5,
            "iou_threshold": 0.7
        },
        inputs={
            "input_image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAASw...",
            "model": "yolov8n.pt"
        },
        global_vars={},
        node_id="test_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)
