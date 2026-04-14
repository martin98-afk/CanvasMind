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
    """YOLO 视频关键点检测推理组件"""
    
    name = "YOLO 关键点检测视频推理"
    category = "YOLO/关键点检测"
    description = "YOLO关键点检测视频推理组件用于对输入视频进行逐帧关键点检测预测，基于训练好的YOLOv8关键点检测模型。输入为视频文件和模型文件（.pt），输出为带有关键点标注的视频和检测结果JSON。"
    requirements = "torch,Pillow,ultralytics,numpy,opencv-python"
    
    # 输入端口定义
    inputs = [
        PortDefinition(name="video", label="输入视频", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
        PortDefinition(name="model", label="模型文件", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]
    
    # 输出端口定义
    outputs = [
        PortDefinition(name="result_video.mp4", label="检测结果视频", type=ArgumentType.FILE),
        PortDefinition(name="keypoints_json", label="关键点检测结果", type=ArgumentType.JSON),
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
        执行 YOLO 视频关键点检测推理流程
        输入：视频文件 + 训练好的关键点检测模型
        输出：检测结果视频、关键点检测结果JSON
        """
        import cv2
        import numpy as np
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
        temp_dir = tempfile.mkdtemp(prefix="yolo_video_pose_")
        result_video_path = os.path.join(temp_dir, "result_video.mp4")

        # 初始化视频写入器
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out_result = cv2.VideoWriter(result_video_path, fourcc, output_fps, (width, height))

        if not out_result.isOpened():
            cap.release()
            raise RuntimeError("无法创建结果视频写入器")

        # 7. 逐帧处理视频
        self.logger.info(f"开始视频推理，预计处理 {total_frames} 帧...")
        
        # 用于存储所有关键点检测结果
        all_keypoints = []
        frame_idx = 0
        processed_frames = 0
        
        # 定义骨骼连接（默认 COCO 17 点）
        skeleton = [
            [16, 14], [14, 12], [17, 15], [15, 13], [12, 13],
            [6, 12], [7, 13], [6, 7], [6, 8], [7, 9],
            [8, 10], [9, 11], [2, 1], [1, 0], [0, 2], [0, 1], [4, 2], [3, 1]
        ]
        
        # 骨骼颜色
        pose_palette = np.array([
            [255, 128, 0], [255, 153, 51], [255, 178, 102], [255, 204, 153],
            [255, 0, 0], [255, 51, 51], [255, 82, 82], [255, 0, 0],
            [0, 255, 0], [51, 255, 51], [102, 255, 102], [0, 255, 0],
            [0, 0, 255], [51, 51, 255], [102, 102, 255], [0, 0, 255],
            [255, 255, 0], [255, 255, 51]
        ], dtype=np.uint8)
        
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
                
                # ========== 收集关键点检测结果 ==========
                frame_keypoints = []
                if result.keypoints is not None:
                    keypoints_data = result.keypoints.data.cpu().numpy()
                    for person_idx, person_kpts in enumerate(keypoints_data):
                        keypoint_list = []
                        valid_kpts = []
                        for kpt_idx, kpt in enumerate(person_kpts):
                            x, y, conf = kpt[0], kpt[1], kpt[2]
                            keypoint_list.append({
                                "index": kpt_idx,
                                "x": float(x),
                                "y": float(y),
                                "confidence": float(conf)
                            })
                            if conf > params.conf:
                                valid_kpts.append([float(x), float(y)])
                        
                        frame_keypoints.append({
                            "person_id": person_idx,
                            "keypoints": keypoint_list,
                            "num_keypoints": len(valid_kpts)
                        })
                
                all_keypoints.append({
                    "frame": frame_idx,
                    "detections": frame_keypoints
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
                    result_frame = self._draw_keypoints_on_frame(
                        frame, result, params.conf, 
                        params.line_thickness, params.point_size
                    )
                
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
        
        # 统计信息
        total_detections = sum(len(f["detections"]) for f in all_keypoints)
        total_keypoints = sum(sum(d["num_keypoints"] for d in f["detections"]) for f in all_keypoints)
        
        result_dict = {
            "result_video.mp4": result_video_bytes,
            "keypoints_json": {
                "video_info": {
                    "width": width,
                    "height": height,
                    "fps": fps,
                    "total_frames": total_frames,
                    "processed_frames": processed_frames
                },
                "statistics": {
                    "total_people_detected": total_detections,
                    "total_keypoints_detected": total_keypoints
                },
                "frames": all_keypoints
            }
        }
        
        # 清理临时文件
        try:
            import shutil
            shutil.rmtree(temp_dir)
        except Exception as e:
            self.logger.warning(f"清理临时文件失败: {str(e)}")
        
        return result_dict

    def _draw_keypoints_on_frame(self, frame, result, conf_threshold, line_thickness, point_size):
        """在帧上绘制关键点（备用方案）"""
        import numpy as np
        
        frame = frame.copy()
        h, w = frame.shape[:2]
        
        if result.keypoints is None:
            return frame
        
        keypoints_data = result.keypoints.data.cpu().numpy()
        
        # COCO 骨骼连接
        skeleton = [
            [16, 14], [14, 12], [17, 15], [15, 13], [12, 13],
            [6, 12], [7, 13], [6, 7], [6, 8], [7, 9],
            [8, 10], [9, 11], [2, 1], [1, 0], [0, 2], [0, 1]
        ]
        
        # 颜色
        colors = [
            (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
            (255, 0, 255), (0, 255, 255), (128, 0, 0), (0, 128, 0),
            (0, 0, 128), (128, 128, 0), (128, 0, 128), (0, 128, 128)
        ]
        
        for person_kpts in keypoints_data:
            # 绘制骨骼连接
            for link_idx, (i, j) in enumerate(skeleton):
                if i < len(person_kpts) and j < len(person_kpts):
                    pt1 = person_kpts[i]
                    pt2 = person_kpts[j]
                    
                    if pt1[2] > conf_threshold and pt2[2] > conf_threshold:
                        x1, y1 = int(pt1[0]), int(pt1[1])
                        x2, y2 = int(pt2[0]), int(pt2[1])
                        color = colors[link_idx % len(colors)]
                        cv2.line(frame, (x1, y1), (x2, y2), color, line_thickness)
            
            # 绘制关键点
            for kpt_idx, kpt in enumerate(person_kpts):
                if kpt[2] > conf_threshold:
                    x, y = int(kpt[0]), int(kpt[1])
                    color = colors[kpt_idx % len(colors)]
                    cv2.circle(frame, (x, y), point_size, color, -1)
        
        return frame


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
            "line_thickness": 2,
            "point_size": 3,
        },
        inputs={
            "video": test_video_path,
            "model": "yolov8n-pose.pt"  # 使用 YOLO 关键点检测模型
        },
        global_vars={},
        node_id="test_video_pose_infer_node",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print("\n组件执行结果:")
    print(f"结果视频: {'已生成' if result.get('result_video.mp4') else 'N/A'}")
    print(f"关键点检测结果: {result.get('keypoints_json', 'N/A')}")
