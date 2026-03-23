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
    """YOLO 视频语义分割推理组件"""
    
    name = "YOLO 语义分割视频推理"
    category = "YOLO/语义分割"
    description = "YOLO语义分割视频推理组件用于对输入视频进行逐帧语义分割预测，基于训练好的YOLOv8分割模型。输入为视频文件和模型文件（.pt），输出为带有分割结果视频。"
    requirements = "torch,Pillow,ultralytics,numpy,opencv-python"
    
    # 输入端口定义
    inputs = [
        PortDefinition(name="video", label="输入视频", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
        PortDefinition(name="model", label="模型文件", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]
    
    # 输出端口定义
    outputs = [
        PortDefinition(name="result_video.mp4", label="分割结果视频", type=ArgumentType.FILE),
    ]
    
    # 属性定义
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
        "output_fps": PropertyDefinition(
            type=PropertyType.INT,
            default=0,
            label="输出帧率（0=保持原视频帧率）",
        ),
    }

    def run(self, params, inputs=None):
        """
        执行 YOLO 视频语义分割推理流程
        输入：视频文件 + 训练好的分割模型
        输出：分割结果视频
        
        处理流程：
        1. 验证输入文件和模型文件
        2. 加载 YOLO 模型
        3. 读取源视频（使用 OpenCV）
        4. 逐帧进行语义分割推理
        5. 生成结果视频（带分割标注）
        """
        import cv2
        import numpy as np
        from PIL import Image
        import torch
        from ultralytics import YOLO
        import os
        import tempfile
        from pathlib import Path as PathLib

        # ========== 1. 获取输入 ==========
        video_path = inputs.video
        model_path = inputs.model

        if not video_path:
            raise ValueError("必须提供输入视频！")
        if not model_path:
            raise ValueError("必须提供模型文件！")

        # 2. 验证文件路径
        video_path = PathLib(video_path)
        if not video_path.exists():
            raise ValueError(f"视频文件不存在: {video_path}")
        
        model_path = PathLib(model_path)
        if not model_path.exists():
            raise ValueError(f"模型文件不存在: {model_path}")

        # 3. 加载 YOLO 模型
        self.logger.info(f"加载模型: {model_path}")
        try:
            model = YOLO(str(model_path))
        except Exception as e:
            raise RuntimeError(f"模型加载失败: {str(e)}")

        # 4. 设置设备
        device = params.device
        if device == "cuda" and not torch.cuda.is_available():
            self.logger.warning("CUDA 不可用，自动切换为 CPU")
            device = "cpu"

        # 5. 打开源视频
        self.logger.info(f"打开视频: {video_path}")
        cap = cv2.VideoCapture(str(video_path.resolve()))
        if not cap.isOpened():
            raise ValueError(f"无法打开视频文件: {video_path}")

        # 获取视频基本信息
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # 使用指定帧率或保持原帧率
        output_fps = params.output_fps if params.output_fps > 0 else fps
        if output_fps <= 0:
            output_fps = fps
        
        self.logger.info(f"视频信息: {width}x{height}, {fps}fps, 共{total_frames}帧")

        # 6. 创建输出视频写入器
        # 使用临时目录存储输出视频
        temp_dir = tempfile.mkdtemp(prefix="yolo_video_")
        
        # 结果视频路径
        result_video_path = os.path.join(temp_dir, "result_video.mp4")

        # 初始化视频写入器
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out_result = cv2.VideoWriter(result_video_path, fourcc, output_fps, (width, height))

        if not out_result.isOpened():
            cap.release()
            raise RuntimeError("无法创建结果视频写入器")

        # 7. 逐帧处理视频
        self.logger.info(f"开始视频推理，预计处理 {total_frames} 帧...")
        frame_idx = 0
        processed_frames = 0
        
        # 用于生成一致的颜色映射（固定随机种子）
        np.random.seed(42)
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_idx += 1
            
            # 转换为 RGB 格式（YOLO 使用 RGB）
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # 执行推理
            try:
                results = model.predict(
                    source=frame_rgb,
                    conf=params.conf,
                    iou=params.iou,
                    imgsz=params.img_size,
                    device=device,
                    save=False,
                    verbose=False
                )
                
                result = results[0]
                
                # ========== 生成结果图像 ==========
                result_plot = result.plot()
                if result_plot is not None and len(result_plot) > 0:
                    # result.plot() 可能返回 RGB 或 BGR，需要转换为 BGR 用于 OpenCV
                    if isinstance(result_plot, np.ndarray):
                        if result_plot.shape[2] == 3:
                            # 检查通道顺序（ultralytics 新版本返回 RGB）
                            if result_plot.dtype == np.uint8:
                                # 转换为 BGR
                                result_frame = cv2.cvtColor(result_plot, cv2.COLOR_RGB2BGR)
                            else:
                                result_frame = result_plot
                        else:
                            result_frame = result_plot
                    else:
                        result_frame = np.array(result_plot)
                    
                    # 确保尺寸一致（防止推理过程中尺寸变化）
                    if result_frame.shape[:2] != (height, width):
                        result_frame = cv2.resize(result_frame, (width, height))
                else:
                    # 如果推理失败，使用原帧
                    result_frame = frame
                
                out_result.write(result_frame)
                
                processed_frames += 1
                
                # 进度日志（每10帧或10%报告一次）
                if frame_idx % 10 == 0 or frame_idx == total_frames:
                    progress = (frame_idx / total_frames) * 100 if total_frames > 0 else 100
                    self.logger.info(f"进度: {frame_idx}/{total_frames} 帧 ({progress:.1f}%)")
                    
                    # 更新进度条显示
                    self.emit_message(
                        method="display_progress",
                        params={"progress": {"data": {"current_value": int(progress), "min": 0, "max": 100}}}
                    )
                
            except Exception as e:
                self.logger.warning(f"处理第 {frame_idx} 帧时出错: {str(e)}")
                # 出错时写入原帧
                out_result.write(frame)
                continue

        # 8. 释放资源
        cap.release()
        out_result.release()

        # 9. 验证输出文件
        if not os.path.exists(result_video_path):
            raise RuntimeError("结果视频生成失败")

        # 10. 读取输出视频为二进制流
        self.logger.info(f"✅ 视频推理完成！处理了 {processed_frames}/{total_frames} 帧")
        
        # 读取结果视频的二进制内容
        with open(result_video_path, 'rb') as f:
            result_video_bytes = f.read()
        
        # 返回二进制流（端口名称带 .mp4 后缀）
        result_dict = {
            "result_video.mp4": result_video_bytes
        }
        
        # 清理临时文件
        try:
            import shutil
            shutil.rmtree(temp_dir)
        except Exception as e:
            self.logger.warning(f"清理临时文件失败: {str(e)}")
        
        return result_dict

    def _generate_mask_visualization(self, result, original_frame, alpha):
        """
        生成分割掩码的可视化图像
        
        Args:
            result: YOLO 推理结果对象
            original_frame: 原始帧图像（numpy array, BGR格式）
            alpha: 透明度（0-1）
        
        Returns:
            可视化后的掩码图像（BGR格式）
        """
        import cv2
        import numpy as np
        
        # 检查是否有分割掩码
        if not hasattr(result, 'masks') or result.masks is None:
            return None
        
        masks_data = result.masks.data
        if masks_data is None or len(masks_data) == 0:
            return None
        
        # 获取原始图像尺寸
        if isinstance(original_frame, np.ndarray):
            h, w = original_frame.shape[:2]
        else:
            return None
        
        # 转换掩码数据为 numpy 数组
        masks = masks_data.cpu().numpy()
        
        # 创建彩色掩码
        mask_vis = np.zeros((h, w, 3), dtype=np.uint8)
        
        # 为每个掩码分配不同颜色
        num_masks = len(masks)
        # 使用固定颜色映射（更美观的颜色）
        colors = self._generate_distinct_colors(min(num_masks, 80))
        
        for i, mask in enumerate(masks):
            # 调整掩码大小以匹配原始图像
            mask_uint8 = (mask * 255).astype(np.uint8)
            mask_resized = cv2.resize(mask_uint8, (w, h), interpolation=cv2.INTER_NEAREST)
            
            # 获取颜色
            color = colors[i % len(colors)]
            
            # 应用掩码
            mask_binary = mask_resized > 127
            mask_vis[mask_binary] = color
        
        # 应用透明度混合
        if alpha < 1.0:
            # 原图转换为 float
            original_float = original_frame.astype(np.float32)
            mask_float = mask_vis.astype(np.float32)
            
            # 混合
            blended = original_float * (1 - alpha) + mask_float * alpha
            mask_vis = blended.astype(np.uint8)
        
        # 转换回 BGR（如果需要）
        # 注意：这里返回的已经是 BGR 格式
        return mask_vis

    def _generate_distinct_colors(self, n):
        """
        生成 n 个差异明显的颜色
        
        Args:
            n: 需要的颜色数量
        
        Returns:
            颜色数组 (n, 3)，BGR 格式
        """
        import cv2
        import numpy as np
        
        if n <= 0:
            return np.array([], dtype=np.uint8).reshape(0, 3)
        
        # 使用 HSV 色彩空间均匀分布，确保颜色差异明显
        colors_hsv = np.zeros((n, 3), dtype=np.float32)
        colors_hsv[:, 0] = np.linspace(0, 180, n, endpoint=False)  # Hue: 0-180 (OpenCV)
        colors_hsv[:, 1] = 255  # Saturation: 最大
        colors_hsv[:, 2] = 200  # Value: 较高亮度
        
        # 转换 HSV 到 BGR
        colors_bgr = np.zeros((n, 3), dtype=np.uint8)
        for i in range(n):
            hsv_pixel = colors_hsv[i].astype(np.uint8)
            bgr_pixel = cv2.cvtColor(
                np.array([[hsv_pixel]], dtype=np.uint8), 
                cv2.COLOR_HSV2BGR
            )[0][0]
            colors_bgr[i] = bgr_pixel
        
        return colors_bgr


# ==================== 单元测试 ====================
if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    
    # 创建测试视频（模拟）
    from PIL import Image
    import numpy as np
    import os
    
    # 创建临时测试视频
    test_video_path = "test_video.mp4"
    if not os.path.exists(test_video_path):
        # 创建一个简单的测试视频（10帧）
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(test_video_path, fourcc, 10, (640, 480))
        
        for i in range(30):
            # 创建渐变帧
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            frame[:, :, 0] = int((i / 30) * 255)  # 蓝色渐变
            frame[:, :, 1] = int((i / 30) * 255)  # 绿色渐变
            frame[:, :, 2] = int((i / 30) * 255)  # 红色渐变
            out.write(frame)
        
        out.release()
        print(f"已创建测试视频: {test_video_path}")
    
    # 测试组件（需要提供有效的模型文件路径）
    model = Component()
    result = model.debug(
        params={
            "conf": 0.25,
            "iou": 0.7,
            "img_size": 640,
            "device": "cpu",
            "output_fps": 10,
        },
        inputs={
            "video": test_video_path,
            "model": ""  # 需要提供有效的模型文件路径，如 "yolov8n-seg.pt"
        },
        global_vars={},
        node_id="test_video_segment_infer_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print("\n组件执行结果:")
    print(f"结果视频: {result.get('result_video', 'N/A')}")
