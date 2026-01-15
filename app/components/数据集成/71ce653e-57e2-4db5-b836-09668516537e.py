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
    name = "视频读取"
    category = "数据集成"
    description = "读取本地视频文件并返回按帧解码的图像列表（NumPy数组）"
    requirements = "opencv-python"
    inputs = [
        PortDefinition(name="video_path", label="视频文件路径", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="frames", label="图像帧列表", type=ArgumentType.ARRAY),
        PortDefinition(name="frame_count", label="总帧数", type=ArgumentType.INT),
    ]

    properties = {
        "sample_rate": PropertyDefinition(
            type=PropertyType.INT,
            default=1,
            label="采样率（每隔多少帧取一帧）",
        ),
        "max_frames": PropertyDefinition(
            type=PropertyType.INT,
            default=0,
            label="最大读取帧数（0 表示不限制）",
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import cv2
        import os
        from pathlib import Path

        video_path = inputs.video_path
        if not os.path.exists(video_path):
            self.logger.error(f"视频文件不存在: {video_path}")
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            self.logger.error(f"无法打开视频文件: {video_path}")
            raise ValueError(f"无法打开视频文件: {video_path}")

        frames = []
        frame_idx = 0
        total_read = 0
        sample_rate = params.sample_rate
        max_frames = params.max_frames

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # 按采样率跳过帧
            if frame_idx % sample_rate == 0:
                # OpenCV 默认是 BGR，转换为 RGB 更通用
                save_path = Path(f"{frame_idx}.jpg").resolve()
                cv2.imwrite(save_path, frame)
                frames.append(str(save_path))
                total_read += 1

                # 检查是否达到最大帧数限制
                if max_frames > 0 and total_read >= max_frames:
                    break

            frame_idx += 1

        cap.release()

        self.logger.info(f"成功读取 {len(frames)} 帧图像，原始视频共 {frame_idx} 帧")
        return {
            "frames": frames,
            "frame_count": len(frames)
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={"sample_rate": 5, "max_frames": 10},
        inputs={"video_path": "/path/to/your/video.mp4"},
        global_vars={},
        node_id="test_video_reader",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print(result)
