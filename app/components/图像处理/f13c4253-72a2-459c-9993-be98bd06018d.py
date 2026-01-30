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
    name = "视频拼接"
    category = "图像处理"
    description = "从视频文件中读取指定索引的帧并输出为图像"
    requirements = "opencv-python"
    inputs = [
        PortDefinition(name="input_videos", label="输入视频", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="merged_video_{{now}}.mp4", label="合并视频", type=ArgumentType.FILE),
    ]
    properties = {
        "output_fps": PropertyDefinition(
            type=PropertyType.INT,
            default=0,
            label="目标帧率",
        ),
    }
    def run(self, params, inputs=None):
        """
        执行视频拼接逻辑
        """
        import os
        import cv2
        import tempfile
        import time
        from pathlib import Path
        # 1. 获取输入
        video_paths = inputs.get("input_videos")
        print(video_paths)
        output_fps_setting = params.get("output_fps", 0)
        resize_mode = "使用第一帧尺寸(强制缩放)"

        # 过滤不存在的文件
        valid_paths = [p for p in video_paths if os.path.exists(p)]
        if not valid_paths:
            raise FileNotFoundError("所有输入的视频路径均不存在。")
        
        self.logger.info(f"准备合并 {len(valid_paths)} 个视频...")

        # 3. 准备输出路径 (通常保存到临时目录或工作流指定目录)
        # 这里创建一个临时文件作为输出
        timestamp = int(time.time())
        output_filename = f"merged_video_{timestamp}.mp4"
        # 假设当前工作目录可写，或者你可以指定绝对路径
        output_dir = tempfile.gettempdir() 
        output_path = os.path.join(output_dir, output_filename)

        # 4. 初始化变量
        out_writer = None
        target_width = 0
        target_height = 0
        target_fps = 0

        try:
            # 第一遍循环：读取第一个视频以确定基准参数
            first_cap = cv2.VideoCapture(valid_paths[0])
            if not first_cap.isOpened():
                raise RuntimeError(f"无法打开第一个视频: {valid_paths[0]}")
            
            target_width = int(first_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            target_height = int(first_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            original_fps = first_cap.get(cv2.CAP_PROP_FPS)
            first_cap.release()

            # 确定最终 FPS
            target_fps = output_fps_setting if output_fps_setting > 0 else original_fps
            
            self.logger.info(f"目标参数 - 分辨率: {target_width}x{target_height}, FPS: {target_fps}")

            # 初始化 VideoWriter
            # mp4v 是比较通用的编码，也可以尝试 avc1
            fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
            out_writer = cv2.VideoWriter(output_path, fourcc, target_fps, (target_width, target_height))

            if not out_writer.isOpened():
                raise RuntimeError("无法创建输出视频流，请检查编码格式或写入权限。")

            # 5. 开始逐个处理视频并写入
            total_frames_processed = 0
            
            for idx, v_path in enumerate(valid_paths):
                cap = cv2.VideoCapture(v_path)
                if not cap.isOpened():
                    self.logger.warning(f"跳过损坏的视频文件: {v_path}")
                    continue

                self.logger.info(f"正在处理第 {idx + 1}/{len(valid_paths)} 个视频: {os.path.basename(v_path)}")
                
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break # 视频结束
                    
                    # 检查尺寸并处理
                    h, w = frame.shape[:2]
                    if (w != target_width or h != target_height):
                        if resize_mode == "报错退出":
                            cap.release()
                            raise ValueError(f"视频 {v_path} 尺寸 ({w}x{h}) 与首个视频 ({target_width}x{target_height}) 不一致。")
                        else:
                            # 强制缩放
                            frame = cv2.resize(frame, (target_width, target_height))
                    
                    # 写入帧
                    out_writer.write(frame)
                    total_frames_processed += 1
                
                cap.release()

            self.logger.info(f"合并完成！总帧数: {total_frames_processed}, 输出路径: {output_path}")

        except Exception as e:
            self.logger.error(f"处理出错: {str(e)}")
            # 如果出错，清理可能生成的半成品
            if os.path.exists(output_path):
                try:
                    out_writer.release()
                    os.remove(output_path)
                except:
                    pass
            raise e
        finally:
            if out_writer:
                out_writer.release()

        # 6. 返回结果
        # 返回字典，key 必须对应 outputs 中的 name
        return {
            "merged_video_{{now}}.mp4": open(output_path, "rb").read()
        }


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
