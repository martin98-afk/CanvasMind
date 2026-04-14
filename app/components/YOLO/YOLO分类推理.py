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
    """YOLO 图像分类推理组件"""
    
    name = "YOLO 图像分类"
    category = "YOLO/分类"
    description = "YOLO图像分类推理组件用于对输入图像进行分类预测，基于训练好的YOLOv8分类模型。输入为图像文件和模型文件（.pt），输出为分类结果（类别名称和置信度）和带分类标签的标注图像。"
    requirements = "torch,Pillow,ultralytics,numpy"
    
    # 输入端口定义
    inputs = [
        PortDefinition(name="image", label="输入图像", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
        PortDefinition(name="model", label="模型文件", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]
    
    # 输出端口定义
    outputs = [
        PortDefinition(name="classification_result", label="分类结果", type=ArgumentType.JSON),
        PortDefinition(name="top_class", label="最高概率类别", type=ArgumentType.TEXT),
        PortDefinition(name="top_confidence", label="最高置信度", type=ArgumentType.FLOAT),
        PortDefinition(name="annotated_image", label="标注图像", type=ArgumentType.IMAGE),
    ]
    
    # 属性定义
    properties = {
        "device": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="cpu",
            label="运行设备",
            choices=["cpu", "cuda"]
        ),
        "top_k": PropertyDefinition(
            type=PropertyType.INT,
            default=5,
            label="返回前K个结果",
        ),
    }

    def run(self, params, inputs=None):
        """
        执行 YOLO 图像分类推理流程
        输入：图像文件 + 分类模型
        输出：分类结果JSON、最高概率类别、置信度、标注图像
        """
        from ultralytics import YOLO
        from PIL import Image
        import numpy as np
        import torch
        import base64
        from io import BytesIO
        import cv2

        # 1. 获取输入
        image_input = inputs.image
        model_path = inputs.model

        if not image_input:
            raise ValueError("必须提供输入图像！")
        if not model_path:
            raise ValueError("必须提供模型文件！")

        # 2. 处理图像输入
        if isinstance(image_input, str):
            # 如果是 Base64 字符串
            if image_input.startswith("data:"):
                image_data = base64.b64decode(image_input.split(",")[1])
                input_image = Image.open(BytesIO(image_data))
            elif Path(image_input).exists():
                input_image = Image.open(image_input)
            else:
                raise ValueError(f"图像文件不存在: {image_input}")
        elif isinstance(image_input, Image.Image):
            input_image = image_input
        elif isinstance(image_input, np.ndarray):
            input_image = Image.fromarray(image_input)
        else:
            raise ValueError(f"不支持的图像输入类型: {type(image_input)}")

        # 确保图像是 RGB 模式
        if input_image.mode != 'RGB':
            input_image = input_image.convert('RGB')

        # 3. 验证模型文件
        model_path = Path(model_path)
        if not model_path.exists():
            raise ValueError(f"模型文件不存在: {model_path}")

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

        # 6. 执行推理
        self.logger.info("开始分类推理...")
        results = model.predict(
            source=input_image,
            imgsz=224,
            device=device,
            verbose=False
        )

        # 7. 解析结果
        result = results[0]
        probs = result.probs
        
        # 获取 top_k 个结果
        top_k = min(params.top_k, len(probs))
        top_indices = np.argsort(probs.data.cpu().numpy())[-top_k:][::-1]
        
        # 获取类别名称（如果可用）
        class_names = result.names if hasattr(result, 'names') else {i: f"class_{i}" for i in range(1000)}
        
        classification_results = []
        for idx in top_indices:
            cls_idx = int(idx)
            conf = float(probs.data[cls_idx].cpu().numpy())
            class_name = class_names.get(cls_idx, f"class_{cls_idx}")
            classification_results.append({
                "class_id": cls_idx,
                "class_name": class_name,
                "confidence": conf
            })
        
        # 最高概率结果
        top_class_id = int(probs.top1)
        top_confidence = float(probs.top1conf.cpu().numpy())
        top_class_name = class_names.get(top_class_id, f"class_{top_class_id}")
        
        self.logger.info(f"分类结果: {top_class_name} ({top_confidence:.4f})")

        # 8. 生成标注图像
        annotated_img = self._create_annotated_image(
            input_image, 
            classification_results, 
            show_bar=params.show_probability_bar
        )

        return {
            "classification_result": {
                "top_class_id": top_class_id,
                "top_class_name": top_class_name,
                "top_confidence": top_confidence,
                "all_results": classification_results
            },
            "top_class": top_class_name,
            "top_confidence": top_confidence,
            "annotated_image": annotated_img
        }

    def _create_annotated_image(self, image, results, show_bar=True):
        """
        创建带分类标签的标注图像
        
        Args:
            image: PIL Image
            results: 分类结果列表
            show_bar: 是否显示概率条
        
        Returns:
            PIL Image
        """
        import cv2
        import numpy as np
        
        # 转换为 numpy 数组
        img_array = np.array(image)
        
        # 添加顶部信息栏
        bar_height = 60 if show_bar else 40
        top_bar = np.ones((bar_height, img_array.shape[1], 3), dtype=np.uint8) * 255
        
        # 绘制顶部标签
        if results:
            top_result = results[0]
            text = f" {top_result['class_name']} {top_result['confidence']*100:.1f}%"
            cv2.putText(top_bar, text, (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.8, (0, 0, 0), 2)
        
        # 合并图像
        annotated = np.vstack([top_bar, img_array])
        
        # 如果需要显示概率条
        if show_bar and len(results) > 1:
            # 添加概率条区域
            bar_region = np.ones((20 * len(results), img_array.shape[1], 3), dtype=np.uint8) * 255
            
            for i, result in enumerate(results[:10]):  # 最多显示10个
                y_pos = 15 + i * 20
                # 绘制标签
                label = f"{result['class_name'][:15]}"
                cv2.putText(bar_region, label, (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 
                           0.4, (0, 0, 0), 1)
                
                # 绘制概率条背景
                bar_width = int(result['confidence'] * (img_array.shape[1] - 150))
                if bar_width > 0:
                    cv2.rectangle(bar_region, (150, y_pos - 12), 
                                 (150 + bar_width, y_pos + 2), 
                                 (0, 200, 0), -1)
                
                # 绘制置信度
                conf_text = f"{result['confidence']*100:.1f}%"
                cv2.putText(bar_region, conf_text, (img_array.shape[1] - 60, y_pos), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
            
            annotated = np.vstack([annotated, bar_region])
        
        return Image.fromarray(annotated)


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    
    from PIL import Image
    import numpy as np
    
    # 创建测试图像
    test_img_path = Path("test_classify.jpg")
    if not test_img_path.exists():
        test_img = Image.new('RGB', (224, 224), color=(100, 150, 200))
        test_img.save(test_img_path)
        print(f"已创建测试图像: {test_img_path}")
    
    model = Component()
    result = model.debug(
        params={
            "device": "cpu",
            "img_size": 224,
            "top_k": 5,
            "show_probability_bar": True,
        },
        inputs={
            "image": str(test_img_path),
            "model": "yolov8n-cls.pt"  # 使用 YOLO 分类模型
        },
        global_vars={},
        node_id="test_classify_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print("\n分类结果:")
    print(f"类别: {result.get('top_class')}")
    print(f"置信度: {result.get('top_confidence')}")
    print(f"完整结果: {result.get('classification_result')}")
