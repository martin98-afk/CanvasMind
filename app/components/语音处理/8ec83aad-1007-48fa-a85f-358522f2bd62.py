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


class DynamicComponent(BaseComponent):
    name = "语音识别为文字"
    category = "语音处理"
    description = "兼容字节流输入或文件路径输入，将语音转为文字内容"
    # 增加 pydub 模块用于处理各种格式的音频文件
    requirements = "vosk,requests,pydub"

    inputs = [
        PortDefinition(name="bytes", label="语音字节流", type=ArgumentType.JSON, connection=ConnectionType.SINGLE),
        PortDefinition(name="file", label="语音文件", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output1", label="识别结果", type=ArgumentType.TEXT),
    ]
    properties = {}

    def run(self, params, inputs=None):
        import os
        import requests
        import zipfile
        import json
        from vosk import Model, KaldiRecognizer
        from pydub import AudioSegment

        RATE = 44100  # 统一处理采样率
        BASE_DIR = "./"
        
        # --- 1. 确定输入源并转换为 frames 列表 ---
        frames = []
        
        # 优先处理文件输入
        if inputs.get("file"):
            file_path = inputs.file
            try:
                # 使用 pydub 自动识别格式并转换
                audio = AudioSegment.from_file(file_path)
                # 强制转为 Vosk 要求的单声道、16bit、44100Hz
                audio = audio.set_frame_rate(RATE).set_channels(1).set_sample_width(2)
                raw_data = audio.raw_data
                # 将 raw_data 切成 4000 字节的小块
                chunk_size = 16000
                frames = [raw_data[i:i + chunk_size] for i in range(0, len(raw_data), chunk_size)]
            except Exception as e:
                return {"output1": f"文件解析失败: {str(e)}"}
        
        # 如果文件为空，则尝试读取字节流输入
        elif inputs.get("bytes"):
            frames = inputs.bytes
            if not isinstance(frames, list):
                return {"output1": "错误：字节流输入必须是 List[bytes] 格式"}
        
        else:
            return {"output1": "未接收到任何音频输入（字节流或文件）"}

        # --- 2. 模型下载与加载逻辑 ---
        def download_and_extract_zip(url, download_folder, extract_folder=None):
            if extract_folder is None:
                extract_folder = download_folder
            os.makedirs(download_folder, exist_ok=True)
            os.makedirs(extract_folder, exist_ok=True)
            try:
                zip_filename = os.path.join(download_folder, url.split('/')[-1])
                print(f"正在下载模型...")
                response = requests.get(url, stream=True)
                response.raise_for_status()
                with open(zip_filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                with zipfile.ZipFile(zip_filename, 'r') as zip_ref:
                    zip_ref.extractall(extract_folder)
                return True
            except Exception as e:
                print(f"模型下载错误: {e}")
                return False

        models_dir = os.path.join(BASE_DIR, 'models', 'VOSK')
        model_dir = os.path.join(models_dir, 'vosk-model-small-cn-0.22')

        if not os.path.exists(model_dir):
            download_and_extract_zip(
                'https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip',
                os.path.dirname(model_dir), 
                os.path.dirname(model_dir)
            )
            try:
                os.remove(os.path.join(os.path.dirname(model_dir), 'vosk-model-small-cn-0.22.zip'))
            except:
                pass

        # 加载模型并识别
        vosk_model = Model(model_dir)
        rec = KaldiRecognizer(vosk_model, RATE)
        rec.SetWords(True)
        print("开始识别音频内容")
        str_ret = ""
        for data in frames:
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                if 'text' in result:
                    str_ret += result['text']
                    self.emit_message(
                        method="stream.output",
                        params={
                            "output1": {"data": result['text'], "data_type": "str", "plugin": "display_str"}
                        }
                    )

        result = json.loads(rec.FinalResult())
        if 'text' in result:
            str_ret += result['text']
            self.emit_message(
                method="stream.output",
                params={
                    "output1": {"data": result['text'], "data_type": "str", "plugin": "display_str"}
                }
            )
        # 整理结果：去除空格
        str_ret = "".join(str_ret.split())
        return {
            "output1": str_ret
        }