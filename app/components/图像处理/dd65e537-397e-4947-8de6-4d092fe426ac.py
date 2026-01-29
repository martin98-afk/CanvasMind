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
    name = "视频指定帧获取"
    category = "图像处理"
    description = "从视频文件中读取指定索引的帧并输出为图像"
    requirements = "opencv-python"
    inputs = [
        PortDefinition(name="input_video", label="输入视频", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="image", label="视频帧图像", type=ArgumentType.IMAGE),
    ]
    properties = {
        "frame_index": PropertyDefinition(
            type=PropertyType.INT,
            default=0,
            label="截取视频帧id",
        ),
    }
    def run(self, params, inputs=None):
        """
        执行视频抽帧逻辑
        """
        import os
        import cv2
        # 3. 获取输入参数 (注意：这里必须与 inputs 和 properties 定义的 name 一致)
        # 兼容字典访问和对象属性访问（视你的框架具体实现而定，这里推荐用字典方式更稳健）
        video_path = inputs.get("input_video")
        target_frame_index = params.get("frame_index")

        self.logger.info(f"开始处理视频: {video_path}, 目标帧: {target_frame_index}")

        # 4. 健壮性检查
        if not video_path or not os.path.exists(video_path):
            error_msg = f"视频文件不存在或路径为空: {video_path}"
            self.logger.error(error_msg)
            # 根据框架要求，可以抛出异常或返回 None
            raise FileNotFoundError(error_msg)

        # 5. OpenCV 处理逻辑
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(f"无法打开视频文件: {video_path}")

        try:
            # 获取视频总帧数
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # 边界检查
            if target_frame_index >= total_frames or target_frame_index == -1:
                self.logger.warning(f"请求帧 {target_frame_index} 超出视频长度 ({total_frames})，将返回最后一帧。")
                target_frame_index = total_frames - 1
            
            # 设置读取位置（这是最快的方法，不用循环读取）
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_index)
            
            ret, frame = cap.read()
            
            if not ret:
                raise RuntimeError("无法读取视频帧 (Stream end or decode error).")
            
            # OpenCV 默认是 BGR，如果后续节点需要 RGB，建议在此转换
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            self.logger.info(f"成功提取第 {target_frame_index} 帧，尺寸: {frame.shape}")
            
            # 6. 返回结果 (key 必须与 outputs 定义的 name 一致)
            return {
                "image": frame_rgb  # 返回 numpy array
            }

        except Exception as e:
            self.logger.error(f"处理出错: {str(e)}")
            raise e
        finally:
            # 务必释放资源
            cap.release()


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={"prop1": "test"},
        inputs={"input1": "output"},
        node_id="测试模型",
        show_input_types = True,
        show_output_types = True,
        show_execution_time = True,
        global_vars = {}
    )
    print(result)
