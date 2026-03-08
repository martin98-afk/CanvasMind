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


class WhisperTranscribeComponent(BaseComponent):
    name = "Whisper 语音转文字"
    category = "API调用/语音识别"
    description = "调用 OpenAI Whisper 模型将音频转换为文字"
    requirements = "requests"

    inputs = [
        PortDefinition(name="audio_file", label="音频文件", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
        PortDefinition(name="audio_url", label="或音频URL", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    
    outputs = [
        PortDefinition(name="transcript", label="转写文本", type=ArgumentType.TEXT),
    ]

    properties = {
        "api_key": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="OpenAI API Key",
        ),
        "model": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="whisper-1",
            label="模型",
            choices=["whisper-1", "gpt-4o-mini-transcribe", "gpt-4o-transcribe"]
        ),
        "language": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="语言(空则自动检测)",
        ),
        "response_format": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="json",
            label="输出格式",
            choices=["json", "text", "srt", "vtt", "verbose_json"]
        ),
        "temperature": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.0,
            label="温度(0-1)",
        ),
        "prompt": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="提示词(可选)",
        ),
    }

    def run(self, params, inputs=None):
        import requests
        import io
        
        # 1. 获取参数和输入
        api_key = params.get("api_key")
        if not api_key:
            raise Exception("请在属性栏设置 OpenAI API Key")

        audio_file = inputs.get("audio_file")
        audio_url = inputs.get("audio_url")
        
        if not audio_file and not audio_url:
            raise Exception("请提供音频文件或音频URL")
            
        model = params.get("model", "whisper-1")
        language = params.get("language", "")
        response_format = params.get("response_format", "json")
        temperature = params.get("temperature", 0.0)
        prompt = params.get("prompt", "")

        # 2. 构建请求
        url = 'https://api.openai.com/v1/audio/transcriptions'
        headers = {
            'Authorization': f'Bearer {api_key}'
        }
        
        # 根据是否有文件选择不同方式
        if audio_file:
            # 文件方式上传
            files = {
                'file': (audio_file, open(audio_file, 'rb'), 'audio/mpeg')
            }
            data = {
                'model': model,
                'response_format': response_format,
            }
            if language:
                data['language'] = language
            if temperature:
                data['temperature'] = temperature
            if prompt:
                data['prompt'] = prompt
                
            self.logger.info(f"正在转写音频文件: {audio_file}")
            
            try:
                response = requests.post(url, headers=headers, files=files, data=data, timeout=120)
            finally:
                # 关闭文件
                files['file'][1].close()
        else:
            # URL 方式 - 使用翻译 API (支持 URL)
            # Whisper 1 也支持通过 URL 方式
            url = 'https://api.openai.com/v1/audio/translations'
            
            # 将 URL 转为请求格式
            data = {
                'model': model,
                'file': audio_url,  # 某些 API 版本可能需要不同的处理
                'response_format': response_format,
            }
            if language:
                data['language'] = language
            if temperature:
                data['temperature'] = temperature
            if prompt:
                data['prompt'] = prompt
            
            self.logger.info(f"正在转写音频URL: {audio_url}")
            
            # 由于 Whisper API 不直接支持 URL，需要先下载
            audio_response = requests.get(audio_url, timeout=60)
            if audio_response.status_code != 200:
                raise Exception(f"无法下载音频文件: {audio_response.status_code}")
            
            # 创建临时文件
            files = {
                'file': ('audio.mp3', io.BytesIO(audio_response.content), 'audio/mpeg')
            }
            
            try:
                response = requests.post(url, headers=headers, files=files, data=data, timeout=120)
            finally:
                files['file'][1].close()

        response_json = response.json()
        
        # 错误处理
        if response.status_code != 200:
            error_msg = response_json.get('error', {}).get('message', '未知错误')
            raise Exception(f"API 请求失败: {error_msg}")

        # 3. 解析返回结果
        if response_format == "json":
            text = response_json.get("text", "")
        elif response_format == "verbose_json":
            text = response_json.get("text", "")
        elif response_format in ["text", "srt", "vtt"]:
            text = response_json
        else:
            text = str(response_json)

        self.logger.info(f"转写成功，文本长度: {len(text)} 字符")
        
        return {"transcript": text}
