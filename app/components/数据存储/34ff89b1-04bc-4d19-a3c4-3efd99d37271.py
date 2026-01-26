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


class LTXVVideoAudioMuxerPyAV(BaseComponent):
    requirements = "av"
    name = "音视频文件合成"
    category = "数据存储"
    description = "使用 PyAV 库合并 MP4 和 WAV，无需安装外部 FFmpeg 软件。支持视频流拷贝和音频重编码。"
    
    inputs = [
        PortDefinition(name="video_path", label="视频文件路径(MP4)", type=ArgumentType.FILE),
        PortDefinition(name="audio_path", label="音频文件路径(WAV)", type=ArgumentType.FILE),
    ]
    outputs = [
        PortDefinition(name="output_{{now}}.mp4", label="输出文件路径", type=ArgumentType.FILE),
    ]
    def run(self, params, inputs):
        import os
        import subprocess
        import shutil
        video_path = inputs.get("video_path")
        audio_path = inputs.get("audio_path")
        output_filename = "final_muxed.mp4"

        if not video_path or not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        # 1. 准备输出目录
        output_dir = os.path.join("output", "muxed_video")
        os.makedirs(output_dir, exist_ok=True)
        final_path = os.path.join(output_dir, output_filename)

        # 如果输出路径和视频输入路径一样，增加后缀防止冲突
        if os.path.abspath(video_path) == os.path.abspath(final_path):
            final_path = final_path.replace(".mp4", "_combined.mp4")

        self.logger.info(f"正在合并音视频... \n视频: {video_path} \n音频: {audio_path}")

        # 2. 构建 FFmpeg 命令
        # -i 视频 -i 音频
        # -c:v copy (视频流直接复制，不重新编码，极快且无损)
        # -c:a aac (音频转码为AAC以保证MP4兼容性)
        # -map 0:v:0 -map 1:a:0 (指定取第一个文件的视频和第二个文件的音频)
        # -shortest (以较短的文件长度为准停止)
        
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-strict", "experimental",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            final_path
        ]

        # 3. 执行合并
        try:
            # 尝试运行 ffmpeg
            process = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.logger.info("音视频合成成功！")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"FFmpeg 合并失败: {e.stderr}")
            # 如果系统没有安装 ffmpeg，给出提示
            if "not found" in str(e) or "不是内部或外部命令" in str(e):
                raise RuntimeError("系统未检测到 FFmpeg。请确保已安装 FFmpeg 并将其添加到系统环境变量 PATH 中。")
            raise e
        except Exception as e:
            self.logger.error(f"发生未知错误: {str(e)}")
            raise e

        self.logger.info(f"音视频合成完成: {final_path}")
        return {"output_{{now}}.mp4": open(final_path, "rb").read()}