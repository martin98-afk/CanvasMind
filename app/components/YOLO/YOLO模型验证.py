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
    """YOLO 模型验证/评估组件"""
    
    name = "YOLO 模型验证"
    category = "YOLO/模型评估"
    description = "YOLO模型验证组件用于对训练好的YOLO模型进行全面评估。输入为模型文件（.pt）和验证数据集，输出包括mAP、precision、recall等评估指标，以及混淆矩阵和PR曲线的可视化图像。支持目标检测、分割和分类三种任务类型的评估。"
    requirements = "torch,Pillow,ultralytics,numpy,opencv-python,seaborn,matplotlib"
    
    # 输入端口定义
    inputs = [
        PortDefinition(name="model", label="模型文件", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
        PortDefinition(name="dataset", label="验证数据集", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]
    
    # 输出端口定义
    outputs = [
        PortDefinition(name="metrics", label="评估指标", type=ArgumentType.JSON),
        PortDefinition(name="pr_curve.png", label="PR曲线图像", type=ArgumentType.IMAGE),
        PortDefinition(name="confusion_matrix.png", label="混淆矩阵图像", type=ArgumentType.IMAGE),
        PortDefinition(name="validation_image", label="验证结果图像", type=ArgumentType.IMAGE),
    ]
    
    # 属性定义
    properties = {
        "task_type": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="detect",
            label="任务类型",
            choices=["detect", "segment", "classify"]
        ),
        "device": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="cpu",
            label="运行设备",
            choices=["cpu", "cuda"]
        ),
        "iou_threshold": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.6,
            label="IoU阈值",
        ),
        "dataset_name": PropertyDefinition(
            type=PropertyType.TEXT,
            default="dataset",
            label="数据集文件夹名",
        ),
    }

    def run(self, params, inputs=None):
        """
        执行 YOLO 模型验证/评估流程
        输入：模型文件 + 验证数据集
        输出：评估指标、PR曲线图像、混淆矩阵图像、验证结果图像
        """
        import os
        import zipfile
        import json
        import tempfile
        from pathlib import Path
        from ultralytics import YOLO
        from PIL import Image
        import torch
        import numpy as np

        # 1. 获取输入
        model_path = inputs.model
        dataset_input = inputs.dataset

        if not model_path:
            raise ValueError("必须提供模型文件！")

        # 2. 验证模型文件
        model_path = Path(model_path)
        if not model_path.exists():
            raise ValueError(f"模型文件不存在: {model_path}")

        # 3. 处理数据集（如果是ZIP文件则解压）
        data_dir = Path(".")
        if dataset_input:
            dataset_path = Path(dataset_input)
            data_dir = dataset_path.parent
            
            if dataset_path.suffix.lower() == ".zip":
                with zipfile.ZipFile(dataset_path, 'r') as zip_ref:
                    zip_ref.extractall(data_dir)

        # 4. 加载模型
        self.logger.info(f"加载模型: {model_path}")
        try:
            model = YOLO(str(model_path))
        except Exception as e:
            raise RuntimeError(f"模型加载失败: {str(e)}")

        # 5. 设置设备
        device = params.device
        if device == "cuda" and not torch.cuda.is_available():
            self.logger.warning("CUDA 不可用，自动切换为 CPU")
            device = "cpu"

        # 6. 根据任务类型设置数据配置
        task_type = params.task_type
        
        # 检查数据集结构
        data_yaml = data_dir / params.dataset_name / "data.yaml"
        if data_yaml.exists():
            data_config = str(data_yaml.resolve())
        else:
            # 直接使用数据集目录
            data_config = str((data_dir / params.dataset_name).resolve())

        self.logger.info(f"任务类型: {task_type}")
        self.logger.info(f"数据配置: {data_config}")

        # 7. 执行验证
        self.logger.info("开始模型验证...")
        try:
            results = model.val(
                data=data_config,
                task=task_type,
                imgsz=640,
                batch=16,
                device=device,
                iou=params.iou_threshold,
                plots=True,
                verbose=True
            )
        except Exception as e:
            self.logger.error(f"模型验证失败: {str(e)}")
            raise

        # 8. 提取评估指标
        metrics = self._extract_metrics(results, task_type)
        
        self.logger.info("=" * 50)
        self.logger.info("评估结果:")
        for key, value in metrics.items():
            if isinstance(value, float):
                self.logger.info(f"  {key}: {value:.4f}")
            else:
                self.logger.info(f"  {key}: {value}")
        self.logger.info("=" * 50)

        # 9. 生成可视化图像
        pr_curve_img = self._generate_pr_curve(results, task_type)
        confusion_matrix_img = self._generate_confusion_matrix(results, task_type)
        validation_img = self._generate_validation_image(results)

        # 10. 保存JSON结果
        if params.save_json:
            output_dir = Path("runs/val_results")
            output_dir.mkdir(parents=True, exist_ok=True)
            json_path = output_dir / f"{task_type}_metrics.json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(metrics, f, indent=2, ensure_ascii=False)
            self.logger.info(f"评估结果已保存: {json_path}")

        return {
            "metrics": metrics,
            "pr_curve.png": pr_curve_img,
            "confusion_matrix.png": confusion_matrix_img,
            "validation_image": validation_img
        }

    def _extract_metrics(self, results, task_type):
        """提取评估指标"""
        metrics = {
            "task_type": task_type
        }
        
        try:
            if task_type == "detect":
                # 目标检测指标
                metrics["mAP50"] = float(getattr(results, 'map50', 0))
                metrics["mAP50-95"] = float(getattr(results, 'map', 0))
                metrics["precision"] = float(getattr(results, 'mp', 0))
                metrics["recall"] = float(getattr(results, 'mr', 0))
                
                # 各类别指标（如果有）
                if hasattr(results, 'box') and results.box is not None:
                    box_metrics = results.box
                    metrics["box_precision"] = float(getattr(box_metrics, 'ap50', [0])[0] if hasattr(box_metrics, 'ap50') else 0)
                    metrics["box_recall"] = float(getattr(box_metrics, 'r', [0])[0] if hasattr(box_metrics, 'r') else 0)
                    
            elif task_type == "segment":
                # 分割指标
                metrics["mAP50"] = float(getattr(results, 'map50', 0))
                metrics["mAP50-95"] = float(getattr(results, 'map', 0))
                metrics["mAP50_seg"] = float(getattr(results, 'map50_seg', 0))
                metrics["mAP_seg"] = float(getattr(results, 'map_seg', 0))
                metrics["precision"] = float(getattr(results, 'mp', 0))
                metrics["recall"] = float(getattr(results, 'mr', 0))
                
                # 分割特有指标
                if hasattr(results, 'seg') and results.seg is not None:
                    seg_metrics = results.seg
                    metrics["seg_precision"] = float(getattr(seg_metrics, 'ap50', [0])[0] if hasattr(seg_metrics, 'ap50') else 0)
                    metrics["seg_recall"] = float(getattr(seg_metrics, 'r', [0])[0] if hasattr(seg_metrics, 'r') else 0)
                    
            elif task_type == "classify":
                # 分类指标
                metrics["top1_accuracy"] = float(getattr(results, 'top1', 0))
                metrics["top5_accuracy"] = float(getattr(results, 'top5', 0))
                
            # 通用指标
            metrics["fitness"] = float(getattr(results, 'fitness', 0))
            
        except Exception as e:
            self.logger.warning(f"提取指标时出错: {str(e)}")
        
        return metrics

    def _generate_pr_curve(self, results, task_type):
        """生成PR曲线图像"""
        import matplotlib.pyplot as plt
        import numpy as np
        
        fig, ax = plt.subplots(1, 1, figsize=(8, 6))
        
        try:
            if task_type == "detect":
                if hasattr(results, 'box') and hasattr(results.box, 'ap50'):
                    ap50 = results.box.ap50
                    recall = results.box.rc
                    precision = results.box.pc
                    
                    ax.plot(recall, precision, 'b-', linewidth=2, label='PR Curve')
                    ax.fill_between(recall, precision, alpha=0.2)
                    ax.set_xlabel('Recall')
                    ax.set_ylabel('Precision')
                    ax.set_title(f'Precision-Recall Curve (mAP@0.5: {np.mean(ap50):.3f})')
                    ax.legend()
                    ax.grid(True, alpha=0.3)
                    
            elif task_type == "segment":
                if hasattr(results, 'seg') and hasattr(results.seg, 'ap50'):
                    ap50 = results.seg.ap50
                    recall = results.seg.rc
                    precision = results.seg.pc
                    
                    ax.plot(recall, precision, 'g-', linewidth=2, label='Seg PR Curve')
                    ax.fill_between(recall, precision, alpha=0.2, color='green')
                    ax.set_xlabel('Recall')
                    ax.set_ylabel('Precision')
                    ax.set_title(f'Segmentation PR Curve (mAP@0.5: {np.mean(ap50):.3f})')
                    ax.legend()
                    ax.grid(True, alpha=0.3)
                    
            elif task_type == "classify":
                # 分类任务不显示PR曲线
                ax.text(0.5, 0.5, 'Classification Task\n(Top-1/Top-5 Accuracy)', 
                       ha='center', va='center', fontsize=14)
                ax.set_title('Classification Results')
                ax.axis('off')
                
        except Exception as e:
            self.logger.warning(f"生成PR曲线时出错: {str(e)}")
            ax.text(0.5, 0.5, 'PR Curve Generation Failed', ha='center', va='center')
            ax.axis('off')
        
        plt.tight_layout()
        
        # 保存到临时文件
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            plt.savefig(f.name, dpi=150, bbox_inches='tight')
            img = Image.open(f.name)
            plt.close()
        
        return img

    def _generate_confusion_matrix(self, results, task_type):
        """生成混淆矩阵图像"""
        import matplotlib.pyplot as plt
        import numpy as np
        
        fig, ax = plt.subplots(1, 1, figsize=(8, 6))
        
        try:
            if task_type == "detect":
                # 尝试从结果中提取混淆矩阵
                if hasattr(results, 'confusion_matrix'):
                    cm = results.confusion_matrix.matrix
                    ax.imshow(cm, cmap='Blues')
                    ax.set_xlabel('Predicted')
                    ax.set_ylabel('True')
                    ax.set_title('Detection Confusion Matrix')
                    
                    # 添加数值标注
                    for i in range(min(cm.shape[0], 10)):
                        for j in range(min(cm.shape[1], 10)):
                            ax.text(j, i, f'{cm[i, j]:.0f}', 
                                   ha='center', va='center', fontsize=8)
                else:
                    ax.text(0.5, 0.5, 'Confusion Matrix\nNot Available', 
                           ha='center', va='center', fontsize=14)
                    ax.axis('off')
                    
            elif task_type == "segment":
                # 分割混淆矩阵
                ax.text(0.5, 0.5, 'Segmentation\nConfusion Matrix', 
                       ha='center', va='center', fontsize=14)
                ax.axis('off')
                ax.set_title('Segmentation Confusion Matrix')
                
            elif task_type == "classify":
                # 分类混淆矩阵
                if hasattr(results, 'confusion_matrix'):
                    cm = results.confusion_matrix.matrix
                    im = ax.imshow(cm, cmap='Blues')
                    ax.set_xlabel('Predicted Class')
                    ax.set_ylabel('True Class')
                    ax.set_title('Classification Confusion Matrix')
                    plt.colorbar(im, ax=ax)
                else:
                    ax.text(0.5, 0.5, 'Confusion Matrix\nNot Available', 
                           ha='center', va='center', fontsize=14)
                    ax.axis('off')
                    
        except Exception as e:
            self.logger.warning(f"生成混淆矩阵时出错: {str(e)}")
            ax.text(0.5, 0.5, 'Confusion Matrix\nGeneration Failed', 
                   ha='center', va='center', fontsize=14)
            ax.axis('off')
        
        plt.tight_layout()
        
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            plt.savefig(f.name, dpi=150, bbox_inches='tight')
            img = Image.open(f.name)
            plt.close()
        
        return img

    def _generate_validation_image(self, results):
        """生成验证结果图像"""
        from PIL import Image
        import numpy as np
        import tempfile
        
        try:
            # 尝试从验证结果中获取图像
            if hasattr(results, 'save_dir') and results.save_dir:
                save_dir = Path(results.save_dir)
                
                # 查找验证图像
                for pattern in ["val_batch0_pred.jpg", "val_batch0_labels.jpg", "results.png"]:
                    img_path = save_dir / pattern
                    if img_path.exists():
                        return Image.open(img_path)
            
            # 如果没有找到，生成一个简单的结果图
            fig, ax = plt.subplots(1, 1, figsize=(10, 6))
            ax.text(0.5, 0.5, 'Validation Complete\nSee metrics for details', 
                   ha='center', va='center', fontsize=16, 
                   transform=ax.transAxes)
            ax.axis('off')
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                plt.savefig(f.name, dpi=100, bbox_inches='tight')
                img = Image.open(f.name)
                plt.close()
            
            return img
            
        except Exception as e:
            self.logger.warning(f"生成验证图像时出错: {str(e)}")
            # 返回空白图像
            return Image.new('RGB', (640, 480), color='white')


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    
    model = Component()
    result = model.debug(
        params={
            "task_type": "detect",
            "device": "cpu",
            "img_size": 640,
            "batch_size": 16,
            "iou_threshold": 0.6,
            "conf_threshold": 0.001,
            "save_json": True,
            "dataset_name": "dataset",
        },
        inputs={
            "model": "yolov8n.pt",
            "dataset": ""
        },
        global_vars={},
        node_id="test_val_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print("\n评估结果:")
    print(f"指标: {result.get('metrics')}")
