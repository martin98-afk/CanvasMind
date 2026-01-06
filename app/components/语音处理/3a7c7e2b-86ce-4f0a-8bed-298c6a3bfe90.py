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


class DynamicComponent(BaseComponent):
    name = "音频录制"
    category = "语音处理"
    description = "录制用户麦克风声音"
    requirements = "pyaudio,numpy"

    inputs = [

    ]
    outputs = [
        PortDefinition(name="output1", label="output1", type=ArgumentType.JSON),
    ]
    properties = {

    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import pyaudio
        import numpy as np
        FORMAT = pyaudio.paInt16  # 音频流的格式
        RATE = 44100  # 采样率，单位Hz
        CHUNK = 4000  # 单位帧
        THRESHOLDNUM = 30  # 静默时间，超过这个个数就保存文件
        THRESHOLD = 200  # 设定停止采集阈值

        audio = pyaudio.PyAudio()
        stream = audio.open(format=FORMAT,
                            channels=1,
                            rate=RATE,
                            input=True,
                            frames_per_buffer=CHUNK)
    
        frames = []
        print("开始录音...")
        count = 0
        while count < THRESHOLDNUM:
            data = stream.read(CHUNK, exception_on_overflow=False)
            np_data = np.frombuffer(data, dtype=np.int16)
            frame_energy = np.mean(np.abs(np_data))
            # print(frame_energy)
            # 如果能量低于阈值持续时间过长，则停止录音
            if frame_energy < THRESHOLD:
                count += 1
            elif count > 0:
                count -= 1

            frames.append(data)
        print(f"停止录音!")
        stream.stop_stream()
        stream.close()
        audio.terminate()

        return {
            "output1": frames
        }
