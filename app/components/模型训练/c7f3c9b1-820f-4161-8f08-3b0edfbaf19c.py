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
    description = "使用 YOLOv8 关键点检测模型进行训练，输入为标准 YOLO 数据集目录（含 train/val 图像与标签）"
    requirements = "torch,Pillow,ultralytics"
    inputs = [
        PortDefinition(
            name="dataset_dir",
            label="数据集目录",
            type=ArgumentType.FILE,
            connection=ConnectionType.SINGLE
        ),
    ]
    outputs = [
        PortDefinition(
            name="trained_model",
            label="训练好的模型",
            type=ArgumentType.TORCHMODEL
        ),
        PortDefinition(
            name="metrics",
            label="训练指标",
            type=ArgumentType.TEXT
        ),
        PortDefinition(
            name="validation_images",
            label="验证图像（含预测结果）",
            type=ArgumentType.IMAGE,
            connection=ConnectionType.SINGLE
        ),
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
        输入：标准 YOLO 数据集目录（train/images, train/labels, val/images, val/labels）
        输出：训练模型、指标、验证图像（含预测结果）
        """
        import os
        import zipfile
        import tempfile
        from pathlib import Path
        from ultralytics import YOLO
        from PIL import Image
        import torch

        # 1. 获取输入数据集路径（ZIP 文件）
        dataset_zip = inputs.dataset_dir
        if not dataset_zip:
            raise ValueError("必须提供数据集文件（ZIP 或目录）！")

        # 2. 解压数据集到临时目录
        zip_path = Path(dataset_zip)
        data_dir = zip_path.parent

        # 如果是 ZIP 文件，解压
        if zip_path.suffix.lower() == ".zip":
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(data_dir)
        else:
            # 假设是目录，直接复制
            if not zip_path.is_dir():
                raise ValueError("输入必须是 ZIP 文件或包含 train/val 的目录")
            # 复制目录内容
            for item in zip_path.iterdir():
                if item.is_dir():
                    (data_dir / item.name).mkdir(parents=True)
                    for file in item.iterdir():
                        file.rename(data_dir / item.name / file.name)
                else:
                    item.rename(data_dir / item.name)

        # 3. 检查数据目录结构
        train_img_dir = data_dir / "dataset" / "train" / "images"
        train_lbl_dir = data_dir / "dataset" / "train" / "labels"
        val_img_dir = data_dir / "dataset" / "valid" / "images"
        val_lbl_dir = data_dir / "dataset" / "valid" / "labels"
        self.logger.info(train_img_dir)

        if not train_img_dir.exists() or not train_lbl_dir.exists():
            raise ValueError("训练数据目录结构不正确，需包含 train/images 和 train/labels")
        if not val_img_dir.exists() or not val_lbl_dir.exists():
            raise ValueError("验证数据目录结构不正确，需包含 val/images 和 val/labels")

        # 4. 构建 data.yaml
        data_yaml = data_dir / "dataset" / "data.yaml"

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
                project=Path(params.save_dir).parent,
                name=Path(params.save_dir).name
            )
        except Exception as e:
            self.logger.error(f"模型训练失败: {str(e)}")
            raise

        # 8. 获取训练结果
        trained_model_path = Path(params.save_dir) / "best.pt"
        if not trained_model_path.exists():
            raise RuntimeError("模型训练完成但未生成最佳模型文件！")

        # 9. 读取验证图像（ultralytics 会生成 val_batch*.jpg）
        val_images_dir = Path(params.save_dir) / "val_batch"
        val_images = []
        if val_images_dir.exists():
            for img_path in val_images_dir.iterdir():
                if img_path.suffix.lower() in [".jpg", ".jpeg", ".png"]:
                    img = Image.open(img_path)
                    val_images.append(img)

        # 10. 返回结果
        return {
            "trained_model": model,  # 可直接用于推理
            "metrics": f"训练完成，最终 mAP@0.5: {results.results_dict.get('metrics/mAP_0.5', 'N/A'):.4f}",
            "model_path": str(trained_model_path),
            "val_images": val_images  # 返回验证图像列表
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
            "dataset": "dummy.zip"  # 模拟标准 YOLO 格式 zip 包
        },
        global_vars={},
        node_id="test_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)