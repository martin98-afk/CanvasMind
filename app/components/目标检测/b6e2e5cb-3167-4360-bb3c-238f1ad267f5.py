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
    requirements = "torch, torchvision, ultralytics, pillow"
    inputs = [
        PortDefinition(name="input_image", label="输入图像", type=ArgumentType.IMAGE),
    ]
    outputs = [
        PortDefinition(name="detections", label="检测结果", type=ArgumentType.JSON),
        PortDefinition(name="keypoints", label="关键点信息", type=ArgumentType.JSON),
        PortDefinition(name="model", label="模型", type=ArgumentType.TORCHMODEL),
    ]
    properties = {
        "model_name": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="yolov8n",
            label="YOLO模型",
            choices=["yolov8n", "yolov8s", "yolov8m", "yolov8l", "yolov8x"]
        ),
        "device": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="cpu",
            label="运行设备",
            choices=["cpu", "cuda"]
        ),
        "conf_threshold": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.5,
            label="置信度阈值"
        ),
        "iou_threshold": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.7,
            label="NMS IoU阈值"
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

        # 加载模型
        self.load_model(params.model_name, params.device)

        # 获取输入图像
        input_image = inputs.input_image
        if input_image is None:
            raise ValueError("未提供图像！")

        # 转换为PIL图像
        if isinstance(input_image, str):
            # 如果是Base64字符串，转换为PIL图像
            from io import BytesIO
            import base64
            image_data = base64.b64decode(input_image)
            input_image = Image.open(BytesIO(image_data))

        # 执行推理
        results = self.model.predict(source=input_image, device=params.device, conf=params.conf_threshold, iou=params.iou_threshold)

        # 解析结果
        detections = []
        keypoints = []

        for result in results:
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
            "model": self.model
        }