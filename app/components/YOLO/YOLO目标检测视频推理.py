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
    """YOLO 目标检测视频推理组件"""
    
    name = "YOLO 目标检测视频推理"
    category = "YOLO/目标检测"
    description = "YOLO目标检测视频推理组件用于对输入视频进行逐帧目标检测预测，基于训练好的YOLOv8目标检测模型。输入为视频文件和模型文件（.pt），输出为带有检测结果标注的视频。"
    requirements = "torch,Pillow,ultralytics,numpy,opencv-python"
    
    # 输入端口定义
    inputs = [
        PortDefinition(name="video", label="输入视频", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
        PortDefinition(name="model", label="模型文件", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]
    
    # 输出端口定义
    outputs = [
        PortDefinition(name="result_video.mp4", label="检测结果视频", type=ArgumentType.FILE),
        PortDefinition(name="detections_json", label="检测结果JSON", type=ArgumentType.JSON),
    ]
    
    # 属性定义
    properties = {
        "conf": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.25,
            label="置信度阈值",
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
        执行 YOLO 视频目标检测推理流程
        输入：视频文件 + 训练好的目标检测模型
        输出：检测结果视频、检测结果JSON
        """
        import cv2
        import numpy as np
        from PIL import Image
        import torch
        from ultralytics import YOLO
        import os
        import tempfile
        import json
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
        temp_dir = tempfile.mkdtemp(prefix="yolo_video_detect_")
        result_video_path = os.path.join(temp_dir, "result_video.mp4")

        # 初始化视频写入器
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out_result = cv2.VideoWriter(result_video_path, fourcc, output_fps, (width, height))

        if not out_result.isOpened():
            cap.release()
            raise RuntimeError("无法创建结果视频写入器")

        # 7. 逐帧处理视频
        self.logger.info(f"开始视频推理，预计处理 {total_frames} 帧...")
        
        # 用于存储所有检测结果
        all_detections = []
        frame_idx = 0
        processed_frames = 0
        
        # 用于类别颜色映射（固定随机种子）
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
                    iou=0.7,
                    imgsz=640,
                    device=device,
                    save=False,
                    verbose=False
                )
                
                result = results[0]
                
                # ========== 收集检测结果 ==========
                frame_detections = []
                for box in result.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    cls = int(box.cls[0].item())
                    conf = float(box.conf[0].item())
                    
                    frame_detections.append({
                        "frame": frame_idx,
                        "bbox": [x1, y1, x2, y2],
                        "class": cls,
                        "confidence": conf
                    })
                
                all_detections.append({
                    "frame": frame_idx,
                    "detections": frame_detections
                })
                
                # ========== 生成结果图像 ==========
                result_plot = result.plot()
                if result_plot is not None and len(result_plot) > 0:
                    if isinstance(result_plot, np.ndarray):
                        if result_plot.shape[2] == 3:
                            if result_plot.dtype == np.uint8:
                                result_frame = cv2.cvtColor(result_plot, cv2.COLOR_RGB2BGR)
                            else:
                                result_frame = result_plot
                        else:
                            result_frame = result_plot
                    else:
                        result_frame = np.array(result_plot)
                    
                    # 确保尺寸一致
                    if result_frame.shape[:2] != (height, width):
                        result_frame = cv2.resize(result_frame, (width, height))
                else:
                    result_frame = frame
                
                out_result.write(result_frame)
                processed_frames += 1
                
                # 进度日志
                if frame_idx % 10 == 0 or frame_idx == total_frames:
                    progress = (frame_idx / total_frames) * 100 if total_frames > 0 else 100
                    self.logger.info(f"进度: {frame_idx}/{total_frames} 帧 ({progress:.1f}%)")
                    
                    self.emit_message(
                        method="display_progress",
                        params={"progress": {"data": {"current_value": int(progress), "min": 0, "max": 100}}}
                    )
                
            except Exception as e:
                self.logger.warning(f"处理第 {frame_idx} 帧时出错: {str(e)}")
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
        
        with open(result_video_path, 'rb') as f:
            result_video_bytes = f.read()
        
        # 计算统计信息
        total_detections = sum(len(f["detections"]) for f in all_detections)
        
        result_dict = {
            "result_video.mp4": result_video_bytes,
            "detections_json": {
                "video_info": {
                    "width": width,
                    "height": height,
                    "fps": fps,
                    "total_frames": total_frames,
                    "processed_frames": processed_frames
                },
                "total_detections": total_detections,
                "frames": all_detections
            }
        }
        
        # 清理临时文件
        try:
            import shutil
            shutil.rmtree(temp_dir)
        except Exception as e:
            self.logger.warning(f"清理临时文件失败: {str(e)}")
        
        return result_dict


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    
    import cv2
    import numpy as np
    import os
    
    # 创建临时测试视频
    test_video_path = "test_video.mp4"
    if not os.path.exists(test_video_path):
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(test_video_path, fourcc, 10, (640, 480))
        
        for i in range(30):
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            frame[:, :, 0] = int((i / 30) * 255)
            frame[:, :, 1] = int((i / 30) * 255)
            frame[:, :, 2] = int((i / 30) * 255)
            out.write(frame)
        
        out.release()
        print(f"已创建测试视频: {test_video_path}")
    
    model = Component()
    result = model.debug(
        params={
            "conf": 0.25,
            "iou": 0.7,
            "img_size": 640,
            "device": "cpu",
            "output_fps": 10,
            "save_frames": False,
        },
        inputs={
            "video": test_video_path,
            "model": ""  # 需要提供有效的模型文件路径
        },
        global_vars={},
        node_id="test_video_detect_infer_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print("\n组件执行结果:")
    print(f"结果视频: {'已生成' if result.get('result_video.mp4') else 'N/A'}")
    print(f"检测结果: {result.get('detections_json', 'N/A')}")
