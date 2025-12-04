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
    name = "YOLO 关键点检测训练"
    category = "模型训练"
    description = "使用 YOLOv8 关键点检测模型进行训练，支持自定义数据集与关键点标注"
    requirements = "Pillow,torch,ultralytics"
    inputs = [
        PortDefinition(name="train_images", label="训练图像", type=ArgumentType.FILE),
        PortDefinition(name="train_labels", label="训练标签", type=ArgumentType.FILE),
        PortDefinition(name="val_images", label="验证图像", type=ArgumentType.FILE),
        PortDefinition(name="val_labels", label="验证标签", type=ArgumentType.FILE),
    ]
    outputs = [
        PortDefinition(name="trained_model", label="训练好的模型", type=ArgumentType.TORCHMODEL),
        PortDefinition(name="metrics", label="训练指标", type=ArgumentType.TEXT),
        PortDefinition(name="model_path", label="模型保存路径", type=ArgumentType.TEXT),
    ]
    properties = {
        "model_name": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="yolov8n-pose.pt",
            label="预训练模型",
            choices=["yolov8n-pose.pt", "yolov8s-pose.pt", "yolov8m-pose.pt", "yolov8l-pose.pt", "yolov8x-pose.pt"]
        ),
        "epochs": PropertyDefinition(
            type=PropertyType.INT,
            default=100,
            label="训练轮数",
            min=1,
            max=1000,
            step=1
        ),
        "batch_size": PropertyDefinition(
            type=PropertyType.INT,
            default=16,
            label="批量大小",
            min=1,
            max=128,
            step=1
        ),
        "img_size": PropertyDefinition(
            type=PropertyType.INT,
            default=640,
            label="图像尺寸",
            min=320,
            max=1280,
            step=16
        ),
        "device": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="cpu",
            label="运行设备",
            choices=["cpu", "cuda"]
        ),
        "save_dir": PropertyDefinition(
            type=PropertyType.TEXT,
            default="./runs/pose",
            label="模型保存路径",
            help="训练结果将保存在此目录"
        ),
    }

    def run(self, params, inputs=None):
        """
        执行 YOLO 关键点检测训练流程
        """
        import os
        import tempfile
        from pathlib import Path
        from ultralytics import YOLO
        from PIL import Image
        import torch

        # 1. 检查输入
        train_images = inputs.train_images
        train_labels = inputs.train_labels
        val_images = inputs.val_images
        val_labels = inputs.val_labels

        if not train_images or not train_labels:
            raise ValueError("必须提供训练图像和标签！")

        # 2. 创建临时数据集目录
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir = Path(tmp_dir) / "data"
            data_dir.mkdir(parents=True)

            # 3. 保存图像和标签到临时目录（模拟 YOLO 数据格式）
            # 创建 images/train 和 labels/train
            train_img_dir = data_dir / "images" / "train"
            train_lbl_dir = data_dir / "labels" / "train"
            val_img_dir = data_dir / "images" / "val"
            val_lbl_dir = data_dir / "labels" / "val"

            train_img_dir.mkdir(parents=True)
            train_lbl_dir.mkdir(parents=True)
            val_img_dir.mkdir(parents=True)
            val_lbl_dir.mkdir(parents=True)

            # 保存训练图像
            for i, img_data in enumerate(train_images):
                img_path = train_img_dir / f"train_{i}.jpg"
                Image.fromarray(img_data).save(img_path)

            # 保存训练标签（假设为文本格式，如：0 0.5 0.5 0.1 0.1 ...）
            for i, label_text in enumerate(train_labels):
                lbl_path = train_lbl_dir / f"train_{i}.txt"
                with open(lbl_path, "w") as f:
                    f.write(label_text)

            # 保存验证图像和标签
            for i, img_data in enumerate(val_images):
                img_path = val_img_dir / f"val_{i}.jpg"
                Image.fromarray(img_data).save(img_path)

            for i, label_text in enumerate(val_labels):
                lbl_path = val_lbl_dir / f"val_{i}.txt"
                with open(lbl_path, "w") as f:
                    f.write(label_text)

            # 4. 构建数据配置文件
            data_yaml = data_dir / "data.yaml"
            with open(data_yaml, "w") as f:
                f.write(f"""
train: {str(train_img_dir.parent)}
val: {str(val_img_dir.parent)}

nc: 1  # 类别数（关键点检测通常为1类，可扩展）
names: ["person"]
                """)

            # 5. 加载模型
            model_name = params.model_name
            model = YOLO(model_name)

            # 6. 设置设备
            device = params.device
            if device == "cuda" and not torch.cuda.is_available():
                self.logger.warning("CUDA 不可用，自动切换为 CPU")
                device = "cpu"

            # 7. 开始训练
            try:
                results = model.train(
                    data=str(data_yaml),
                    epochs=params.epochs,
                    imgsz=params.img_size,
                    batch=params.batch_size,
                    device=device,
                    save=True,
                    save_period=10,
                    project=Path(params.save_dir).parent
                )
            except Exception as e:
                self.logger.error(f"模型训练失败: {str(e)}")
                raise

            # 8. 获取训练结果
            trained_model_path = Path(params.save_dir) / "best.pt"
            if not trained_model_path.exists():
                raise RuntimeError("模型训练完成但未生成最佳模型文件！")

            # 9. 返回结果
            return {
                "trained_model": model,  # 可直接用于推理
                "metrics": f"训练完成，最终 mAP@0.5: {results.results_dict.get('metrics/mAP_0.5', 'N/A'):.4f}",
                "model_path": str(trained_model_path)
            }
        
if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={
            "model_name": "yolov8n-pose.pt",
            "epochs": 1,
            "batch_size": 4,
            "img_size": 320,
            "device": "cpu",
            "save_dir": "./test_runs/pose"
        },
        inputs={
            "train_images": [Image.new("RGB", (640, 480)).tobytes() for _ in range(2)],
            "train_labels": ["0 0.5 0.5 0.1 0.1 0.2 0.2" for _ in range(2)],
            "val_images": [Image.new("RGB", (640, 480)).tobytes() for _ in range(1)],
            "val_labels": ["0 0.5 0.5 0.1 0.1" for _ in range(1)]
        },
        global_vars={},
        node_id="test_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)
