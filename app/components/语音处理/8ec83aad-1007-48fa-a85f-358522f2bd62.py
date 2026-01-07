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
    name = "语音识别为文字"
    category = "语音处理"
    description = "将用户录制的音频转为文字内容"
    requirements = "vosk,requests"

    inputs = [
        PortDefinition(name="input1", label="input1", type=ArgumentType.JSON, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output1", label="output1", type=ArgumentType.TEXT),
    ]
    properties = {

    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        RATE = 44100  # 采样率，单位Hz
        BASE_DIR = "./"
        frames = inputs.input1
        import os
        import requests
        import zipfile
        import json
        from vosk import Model, KaldiRecognizer, SetLogLevel
    
        def download_and_extract_zip(url, download_folder, extract_folder=None):
            """
            下载ZIP文件并解压到指定目录
    
            参数:
                url: ZIP文件的URL
                download_folder: 下载文件保存的目录
                extract_folder: 解压目录(默认为下载目录)
            """
            # 如果未指定解压目录，则使用下载目录
            if extract_folder is None:
                extract_folder = download_folder
    
            # 确保目录存在
            os.makedirs(download_folder, exist_ok=True)
            os.makedirs(extract_folder, exist_ok=True)
    
            try:
                # 从URL获取文件名
                zip_filename = os.path.join(download_folder, url.split('/')[-1])
    
                print(f"正在下载 {url}...")
                # 下载文件
                response = requests.get(url, stream=True)
                response.raise_for_status()  # 检查请求是否成功
    
                # 写入文件
                with open(zip_filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
    
                print(f"文件已下载到: {zip_filename}")
    
                # 解压文件
                print(f"正在解压到 {extract_folder}...")
                with zipfile.ZipFile(zip_filename, 'r') as zip_ref:
                    zip_ref.extractall(extract_folder)
    
                print("解压完成!")
    
                return True
    
            except Exception as e:
                print(f"发生错误: {e}")
                return False
    
        models_dir = os.path.join(BASE_DIR, 'models', 'VOSK')
        if not os.path.exists(models_dir):
            os.makedirs(models_dir)

        model_dir = os.path.join(BASE_DIR, 'models', 'VOSK', 'vosk-model-small-cn-0.22')
        if os.path.exists(model_dir):
            self.vosk_model = Model(model_dir)
        else:
            download_and_extract_zip('https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip',os.path.dirname(model_dir), os.path.dirname(model_dir))
            try:
                os.remove(os.path.join(os.path.dirname(model_dir), 'vosk-model-small-cn-0.22.zip'))
            except OSError:
                pass
            self.vosk_model = Model(model_dir)
        rec = KaldiRecognizer(self.vosk_model, RATE)
        rec.SetWords(True)
        str_ret = ""
        for data in frames:
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                if 'text' in result:
                    str_ret += result['text']

        result = json.loads(rec.FinalResult())
        if 'text' in result:
            str_ret += result['text']

        str_ret = "".join(str_ret.split())
        return {
            "output1": str_ret
        }
