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
    """YOLO 图像分类训练组件"""
    
    name = "YOLO 图像分类训练"
    category = "YOLO/分类"
    description = "YOLO图像分类训练组件用于基于YOLOv8分类模型对图像数据集进行训练。输入为分类数据集目录（按类别文件夹组织）或ZIP压缩包，以及可选的预训练模型，输出为训练好的分类模型（.pt）。参数包括模型类型、训练轮数、批量大小、图像尺寸、运行设备和优化器等可配置项。"
    requirements = "torch,Pillow,ultralytics,torchvision"
    
    # 输入端口定义
    inputs = [
        PortDefinition(name="dataset_dir", label="数据集目录", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
        PortDefinition(name="pre_model", label="预训练模型", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]
    
    # 输出端口定义
    outputs = [
        PortDefinition(name="model.pt", label="训练好的分类模型", type=ArgumentType.FILE),
        PortDefinition(name="train_results", label="训练结果", type=ArgumentType.JSON),
    ]
    
    # 属性定义
    properties = {
        "model_name": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="yolov8n-cls.pt",
            label="预训练模型",
            choices=["yolov8n-cls.pt", "yolov8s-cls.pt", "yolov8m-cls.pt", "yolov8l-cls.pt", "yolov8x-cls.pt"]
        ),
        "epochs": PropertyDefinition(
            type=PropertyType.INT,
            default=100,
            label="训练轮数",
        ),
        "device": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="cpu",
            label="运行设备",
            choices=["cpu", "cuda"]
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
    }

    def run(self, params, inputs=None):
        """
        执行 YOLO 图像分类训练流程
        输入：分类数据集目录（按类别文件夹组织）或 ZIP 压缩包
        输出：训练好的分类模型
        """
        import os
        import zipfile
        from pathlib import Path
        from ultralytics import YOLO
        import torch
        import json

        # 1. 获取输入数据集路径
        dataset_input = inputs.dataset_dir
        if not dataset_input:
            raise ValueError("必须提供数据集目录！")

        dataset_path = Path(dataset_input)
        data_dir = dataset_path.parent

        # 如果是 ZIP 文件，解压
        if dataset_path.suffix.lower() == ".zip":
            with zipfile.ZipFile(dataset_path, 'r') as zip_ref:
                zip_ref.extractall(data_dir)
            # 更新数据集路径为解压后的目录
            extracted_name = dataset_path.stem
            dataset_path = data_dir / extracted_name

        # 2. 检查数据目录结构
        # 分类数据集结构: dataset_name/train/class_name1/, dataset_name/train/class_name2/, ...
        train_dir = data_dir / params.dataset_name / "train"
        
        self.logger.info(f"训练目录: {train_dir}")
        
        if not train_dir.exists():
            # 尝试直接使用 dataset_path
            if dataset_path.is_dir():
                train_dir = dataset_path
                self.logger.info(f"直接使用数据集目录: {train_dir}")
            else:
                raise ValueError(f"训练目录不存在: {train_dir}")

        # 获取类别列表
        class_names = sorted([d.name for d in train_dir.iterdir() if d.is_dir()])
        if not class_names:
            raise ValueError(f"未找到类别子目录: {train_dir}")
        
        num_classes = len(class_names)
        self.logger.info(f"找到 {num_classes} 个类别: {class_names}")

        # 3. 加载模型
        model_name = inputs.pre_model if inputs.pre_model else params.model_name
        self.logger.info(f"加载模型: {model_name}")
        model = YOLO(model_name)

        # 4. 设置设备
        device = params.device
        if device == "cuda" and not torch.cuda.is_available():
            self.logger.warning("CUDA 不可用，自动切换为 CPU")
            device = "cpu"

        # 5. 构建训练参数字典
        train_params = {
            "data": str(train_dir.parent),  # 传入父目录，ultralytics 会自动查找 train/val
            "epochs": params.epochs,
            "imgsz": 224,
            "batch": 16,
            "device": device,
            "save": True,
            "amp": True if device == "cuda" else False,
            "save_period": 10,
            "patience": params.patience,
            "project": str(Path("runs").resolve()),
            "name": "classify",
        }

        # 6. 开始训练
        try:
            self.logger.info("开始分类训练...")
            results = model.train(**train_params)
            self.logger.info("训练完成！")
        except Exception as e:
            self.logger.error(f"模型训练失败: {str(e)}")
            raise

        # 7. 训练完成后，查找最新保存的模型目录
        project_dir = Path("runs")
        if not project_dir.exists():
            raise RuntimeError("训练项目目录不存在！")

        # 获取所有以 name 开头的子目录
        cls_dirs = []
        for item in project_dir.iterdir():
            if item.is_dir() and item.name.startswith(params.task_name):
                cls_dirs.append(item)

        if not cls_dirs:
            raise RuntimeError(f"未找到训练输出目录，预期在 {project_dir} 下以 {params.task_name} 开头的目录")

        # 按创建时间排序，取最新的
        latest_dir = max(cls_dirs, key=lambda x: x.stat().st_ctime)
        self.logger.info(f"最新训练目录: {latest_dir}")

        # 8. 构建模型路径
        best_model_path = latest_dir / "weights" / "best.pt"
        last_model_path = latest_dir / "weights" / "last.pt"
        
        if best_model_path.exists():
            trained_model_path = best_model_path
        elif last_model_path.exists():
            trained_model_path = last_model_path
        else:
            raise RuntimeError(f"未找到模型文件：best.pt 或 last.pt")

        self.logger.info(f"训练模型路径: {trained_model_path}")

        # 9. 读取训练结果
        results_csv = latest_dir / "results.csv"
        train_results = {
            "model_path": str(trained_model_path),
            "num_classes": num_classes,
            "class_names": class_names,
            "epochs": params.epochs,
        }
        
        if results_csv.exists():
            try:
                import pandas as pd
                df = pd.read_csv(results_csv)
                # 提取最终指标
                if len(df) > 0:
                    last_row = df.iloc[-1]
                    train_results["final_top1_acc"] = float(last_row.get("metrics/accuracy_top1", 0))
                    train_results["final_top5_acc"] = float(last_row.get("metrics/accuracy_top5", 0))
                    train_results["train_loss"] = float(last_row.get("train/loss", 0))
                    self.logger.info(f"最终 Top-1 准确率: {train_results['final_top1_acc']:.4f}")
                    self.logger.info(f"最终 Top-5 准确率: {train_results['final_top5_acc']:.4f}")
            except Exception as e:
                self.logger.warning(f"读取训练结果失败: {str(e)}")

        return {
            "model.pt": str(trained_model_path),
            "train_results": train_results
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={
            "model_name": "yolov8n-cls.pt",
            "epochs": 1,
            "batch_size": 4,
            "img_size": 224,
            "device": "cpu",
            "task_name": "classify",
            "dataset_name": "dataset",
            "patience": 50,
            "optimizer": "auto",
            "lr0": 0.001,
            "save_period": 10,
            "augment": True,
        },
        inputs={
            "dataset_dir": "dummy.zip",
            "pre_model": ""
        },
        global_vars={},
        node_id="test_classify_train_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print("\n训练结果:")
    print(f"模型路径: {result.get('model.pt')}")
    print(f"训练结果: {result.get('train_results')}")
