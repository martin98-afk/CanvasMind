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


class VideoSaverComponent(BaseComponent):
    name = "视频存储器"
    category = "生成模型/视频生成"
    description = "将视频帧序列保存为 MP4 文件"
    requirements = "opencv-python,numpy"

    inputs = [
        PortDefinition(name="frames", label="视频帧序列", type=ArgumentType.OBJECT),
    ]
    
    outputs = [
        PortDefinition(name="output_{now}.mp4", label="视频文件路径", type=ArgumentType.FILE),
    ]

    properties = {
        "fps": PropertyDefinition(
            type=PropertyType.INT,
            default=16,
            label="帧率 (FPS)",
        ),
        "filename_prefix": PropertyDefinition(
            type=PropertyType.TEXT,
            default="wan_video",
            label="文件名前缀",
        ),
    }

    def run(self, params, inputs=None):
        import cv2
        import numpy as np
        import os
        import time

        # 1. 获取输入数据
        # 期望格式: [F, H, W, C], uint8, RGB
        frames = inputs.get("frames")
        if frames is None or not isinstance(frames, np.ndarray):
            raise ValueError("未接收到有效的视频帧数据")

        # 2. 准备输出路径
        video_path = "output.mp4"
        # 3. 获取视频尺寸
        # frames.shape = (帧数, 高, 宽, 通道)
        num_frames, height, width, _ = frames.shape
        fps = params.get("fps", 16)

        self.logger.info(f"正在合成视频: {width}x{height}, {num_frames}帧, {fps}fps")

        try:
            # 4. 初始化 OpenCV VideoWriter
            # 使用 'mp4v' 编码器 (兼容性好)
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(video_path, fourcc, fps, (width, height))

            for i in range(num_frames):
                frame = frames[i]
                
                # 注意：OpenCV 使用 BGR 格式，而 VAE 输出通常是 RGB
                # 所以必须进行颜色通道转换
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                
                out.write(frame_bgr)

            out.release()
            
            self.logger.info(f"✅ 视频已保存至: {video_path}")
            return {"output_{now}.mp4": video_path}

        except Exception as e:
            self.logger.error(f"保存视频失败: {str(e)}")
            raise e