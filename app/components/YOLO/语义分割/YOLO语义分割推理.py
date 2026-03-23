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
    name = "YOLO 语义分割图像推理"
    category = "YOLO/语义分割"
    description = "YOLO语义分割推理组件用于对输入图像进行语义分割预测，基于训练好的YOLOv8分割模型，输入为图像文件和模型文件（.pt），输出为带有分割结果的图像和分割掩码。"
    requirements = "torch,Pillow,ultralytics,numpy"
    inputs = [
        PortDefinition(name="image", label="输入图像", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
        PortDefinition(name="model", label="模型文件", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="result_image", label="分割结果图像", type=ArgumentType.IMAGE),
        PortDefinition(name="mask_image", label="分割掩码", type=ArgumentType.IMAGE),
    ]
    properties = {
        "conf": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.25,
            label="置信度阈值",
        ),
        "iou": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.7,
            label="IOU阈值",
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
        "save_mask": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="保存分割掩码",
        ),
        "mask_alpha": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.5,
            label="掩码透明度",
        ),
    }

    def run(self, params, inputs=None):
        """
        执行 YOLO 语义分割推理流程
        输入：图像文件 + 训练好的分割模型
        输出：分割结果图像、分割掩码
        """
        from ultralytics import YOLO
        from PIL import Image
        import numpy as np
        import torch

        # 1. 获取输入
        image_path = inputs.image
        model_path = inputs.model

        if not image_path:
            raise ValueError("必须提供输入图像！")
        if not model_path:
            raise ValueError("必须提供模型文件！")

        # 2. 确保图像路径存在
        image_path = Path(image_path)
        if not image_path.exists():
            raise ValueError(f"图像文件不存在: {image_path}")

        model_path = Path(model_path)
        if not model_path.exists():
            raise ValueError(f"模型文件不存在: {model_path}")

        # 3. 加载模型
        self.logger.info(f"加载模型: {model_path}")
        model = YOLO(str(model_path))

        # 4. 设置设备
        device = params.device
        if device == "cuda" and not torch.cuda.is_available():
            self.logger.warning("CUDA 不可用，自动切换为 CPU")
            device = "cpu"

        # 5. 执行推理
        self.logger.info(f"开始推理: {image_path}")
        results = model.predict(
            source=str(image_path.resolve()),
            conf=params.conf,
            iou=params.iou,
            imgsz=params.img_size,
            device=device,
            save=False,
            verbose=False
        )

        # 6. 获取结果
        result = results[0]
        
        # 7. 生成带分割结果的图像
        result_img = None
        result_plot = result.plot()
        if result_plot is not None and len(result_plot) > 0:
            result_img = result_plot
            # 确保是 PIL Image
            if isinstance(result_img, np.ndarray):
                result_img = Image.fromarray(result_img)

        # 8. 生成分割掩码
        mask_img = None
        if params.save_mask and hasattr(result, 'masks') and result.masks is not None:
            # 获取原始图像
            original_img = Image.open(image_path)
            img_array = np.array(original_img)
            
            # 获取掩码数据
            masks = result.masks.data.cpu().numpy()
            
            # 创建彩色掩码
            h, w = img_array.shape[:2]
            mask_vis = np.zeros((h, w, 3), dtype=np.uint8)
            
            # 为每个掩码分配不同颜色
            np.random.seed(42)  # 固定种子保证颜色一致
            colors = np.random.randint(0, 255, (max(len(masks), 1), 3), dtype=np.uint8)
            
            for i, mask in enumerate(masks):
                # 调整掩码大小
                mask_resized = np.array(Image.fromarray(mask.astype(np.uint8)).resize(
                    (w, h), Image.NEAREST
                ))
                color = colors[i % len(colors)]
                mask_vis[mask_resized > 0] = color
            
            # 应用透明度
            if params.mask_alpha < 1.0:
                # 将掩码叠加到原图
                overlay = img_array.copy().astype(np.float32)
                mask_overlay = mask_vis.astype(np.float32)
                alpha = params.mask_alpha
                blended = overlay * (1 - alpha) + mask_overlay * alpha
                mask_vis = blended.astype(np.uint8)
            
            mask_img = Image.fromarray(mask_vis)
            self.logger.info(f"生成分割掩码，包含 {len(masks)} 个分割区域")

        return {
            "result_image": result_img,
            "mask_image": mask_img
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    
    # 创建测试图像
    from PIL import Image
    import numpy as np
    
    # 创建测试用图像
    test_img_path = Path("test_image.jpg")
    if not test_img_path.exists():
        test_img = Image.new('RGB', (640, 480), color=(73, 109, 137))
        test_img.save(test_img_path)
        print(f"已创建测试图像: {test_img_path}")
    
    model = Component()
    result = model.debug(
        params={
            "conf": 0.25,
            "iou": 0.7,
            "img_size": 640,
            "device": "cpu",
            "save_mask": True,
            "mask_alpha": 0.5,
        },
        inputs={
            "image": str(test_img_path),
            "model": ""  # 需要提供有效的模型文件路径
        },
        global_vars={},
        node_id="test_segment_infer_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)
