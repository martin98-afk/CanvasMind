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


class Component(BaseComponent):
    name = "YOLO 语义分割训练"
    category = "YOLO/语义分割"
    description = "YOLO语义分割训练组件用于基于YOLOv8分割模型对标准YOLO格式数据集（含train/val图像与标签）进行训练，输入为数据集ZIP文件或目录及可选预训练模型文件，输出为训练好的模型文件（.pt）和包含预测结果的验证图像，参数包括模型类型、训练轮数、批量大小、图像尺寸、运行设备和任务类型等可配置项。"
    requirements = "torch,Pillow,ultralytics,torchvision"
    inputs = [
        PortDefinition(name="dataset_dir", label="数据集目录", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
        PortDefinition(name="pre_model", label="预训练模型", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="model.pt", label="训练好的模型", type=ArgumentType.FILE),
        PortDefinition(name="validation_image", label="验证图像（含预测结果）", type=ArgumentType.IMAGE),
    ]
    properties = {
        "model_name": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="yolov8n-seg.pt",
            label="预训练模型",
            choices=["yolov8n-seg.pt", "yolov8s-seg.pt", "yolov8m-seg.pt", "yolov8l-seg.pt", "yolov8x-seg.pt"]
        ),
        "epochs": PropertyDefinition(
            type=PropertyType.INT,
            default=100,
            label="训练轮数",
        ),
        "batch_size": PropertyDefinition(
            type=PropertyType.INT,
            default=9,
            label="批量大小",
        ),
        "img_size": PropertyDefinition(
            type=PropertyType.INT,
            default=640,
            label="图像尺寸",
        ),
        "device": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="cpu",
            label="运行设备",
            choices=["cpu", "cuda"]
        ),
        "task_name": PropertyDefinition(
            type=PropertyType.TEXT,
            default="segment",
            label="任务类型",
        ),
        "dataset_name": PropertyDefinition(
            type=PropertyType.TEXT,
            default="dataset",
            label="数据集文件夹名",
        ),
        "patience": PropertyDefinition(
            type=PropertyType.INT,
            default=50,
            label="早停轮数",
        ),
        "optimizer": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="auto",
            label="优化器",
            choices=["auto", "SGD", "Adam", "AdamW", "NAdam", "RAdam", "RMSProp"]
        ),
        "seg": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=1.0,
            label="分割损失权重",
        ),
    }

    def run(self, params, inputs=None):
        """
        执行 YOLO 语义分割训练流程
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

        # 1. 获取输入数据集路径（ZIP 文件或目录）
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
        train_img_dir = data_dir / params.dataset_name / "train" / "images"
        train_lbl_dir = data_dir / params.dataset_name / "train" / "labels"
        val_img_dir = data_dir / params.dataset_name / "valid" / "images"
        val_lbl_dir = data_dir / params.dataset_name / "valid" / "labels"
        self.logger.info(f"训练图像目录: {train_img_dir}")

        if not train_img_dir.exists() or not train_lbl_dir.exists():
            raise ValueError("训练数据目录结构不正确，需包含 train/images 和 train/labels")
        if not val_img_dir.exists() or not val_lbl_dir.exists():
            raise ValueError("验证数据目录结构不正确，需包含 val/images 和 val/labels")

        # 4. 构建 data.yaml
        data_yaml = data_dir / params.dataset_name / "data.yaml"

        # 5. 加载模型
        model_name = inputs.pre_model or params.model_name
        self.logger.info(f"加载模型: {model_name}")
        model = YOLO(model_name)

        # 6. 设置设备
        device = params.device
        if device == "cuda" and not torch.cuda.is_available():
            self.logger.warning("CUDA 不可用，自动切换为 CPU")
            device = "cpu"

        # 7. 构建训练参数字典
        train_params = {
            "data": str(data_yaml.resolve()),
            "epochs": params.epochs,
            "imgsz": params.img_size,
            "batch": params.batch_size,
            "device": device,
            "save": True,
            "amp": False,
            "save_period": 10,
            "patience": params.patience,
            "optimizer": params.optimizer,
            "project": str(Path("runs").resolve()),
            "name": params.task_name,
        }

        # 8. 开始训练
        try:
            self.logger.info("开始训练...")
            results = model.train(**train_params)
            self.logger.info("训练完成！")
        except Exception as e:
            self.logger.error(f"模型训练失败: {str(e)}")
            raise

        # 9. 训练完成后，动态查找最新保存的模型目录
        project_dir = Path("runs")
        if not project_dir.exists():
            raise RuntimeError("训练项目目录不存在！")

        # 获取所有以 name 开头的子目录（如 segment, segment1, segment2...）
        seg_dirs = []
        for item in project_dir.iterdir():
            if item.is_dir() and item.name.startswith(params.task_name):
                seg_dirs.append(item)

        if not seg_dirs:
            raise RuntimeError(f"未找到训练输出目录，预期在 {project_dir} 下以 {params.task_name} 开头的目录")

        # 按创建时间排序，取最新的
        latest_dir = max(seg_dirs, key=lambda x: x.stat().st_ctime)
        self.logger.info(f"最新训练目录: {latest_dir}")

        # 10. 构建模型路径
        trained_model_path = latest_dir / "weights" / "best.pt"
        if not trained_model_path.exists():
            raise RuntimeError(f"未找到最佳模型文件：{trained_model_path}")

        # 11. 读取验证图像（ultralytics 会生成 val_batch*_pred.jpg）
        # 语义分割模型的验证图像通常命名为 val_batch*_labels.jpg 或 val_batch*_pred.jpg
        img_path = latest_dir / "val_batch0_pred.jpg"
        if not img_path.exists():
            # 尝试其他可能的文件名
            for pattern in ["val_batch0_labels.jpg", "val_batch1_pred.jpg", "val_batch1_labels.jpg"]:
                alt_path = latest_dir / pattern
                if alt_path.exists():
                    img_path = alt_path
                    break

        img = None
        if img_path.exists():
            img = Image.open(img_path)
            self.logger.info(f"验证图像已加载: {img_path}")
        else:
            self.logger.warning(f"未找到验证图像: {img_path}")

        return {
            "model.pt": str(trained_model_path),
            "validation_image": img
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={
            "model_name": "yolov8n-seg.pt",
            "epochs": 1,
            "batch_size": 4,
            "img_size": 320,
            "device": "cpu",
            "task_name": "segment",
            "dataset_name": "dataset",
            "patience": 50,
            "optimizer": "auto",
            "seg": 1.0,
        },
        inputs={
            "dataset_dir": "dummy.zip",  # 模拟标准 YOLO 格式 zip 包
            "pre_model": ""  # 空值将使用 model_name
        },
        global_vars={},
        node_id="test_segment_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)
