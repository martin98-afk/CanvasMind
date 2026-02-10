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


class AudioPreProcessorComponent(BaseComponent):
    name = "语音转字节流"
    category = "语音处理"
    description = "加载音频文件并转换为识别组件需要的44100Hz单声道字节流"
    requirements = "pydub"

    inputs = [
        PortDefinition(name="file_path", label="音频文件路径", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output1", label="音频切片(JSON)", type=ArgumentType.JSON),
    ]
    properties = {
        "chunk_size": PropertyDefinition(
            type=PropertyType.INT,
            default=4000,
            label="切片大小",
        ),
    }
    def run(self, params, inputs=None):
        from pydub import AudioSegment
        import io
        import os
        file_path = inputs.get("file_path")
        chunk_size = params.get("chunk_size", 4000)
        
        if not file_path or not os.path.exists(file_path):
            raise Exception(f"文件不存在: {file_path}")

        # 1. 使用 pydub 加载音频
        try:
            audio = AudioSegment.from_file(file_path)
        except Exception as e:
            raise Exception(f"无法解析音频文件: {e}. 请确保系统中安装了 ffmpeg")

        # 2. 转换为 Vosk 组件要求的格式: 44100Hz, 单声道, 16bit(sample_width=2)
        audio = audio.set_frame_rate(44100).set_channels(1).set_sample_width(2)
        
        # 3. 获取原始二进制数据
        raw_data = audio.raw_data
        
        # 4. 将长数据切分成列表（frames）
        # 注意：虽然类型是 JSON，但在 Python 节点间传递时，List[bytes] 是可以被接收方处理的
        frames = []
        for i in range(0, len(raw_data), chunk_size):
            frames.append(raw_data[i:i + chunk_size])

        return {
            "output1": frames
        }