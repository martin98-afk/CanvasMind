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


class QwenTTSComponent(BaseComponent):
    name = "通义千问 TTS 语音合成"
    category = "API调用/语音合成"
    description = "调用阿里云 DashScope 通义千问 TTS 模型将文字转换为语音"
    requirements = "requests"

    inputs = [
        PortDefinition(name="text", label="要转换的文字", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    
    outputs = [
        PortDefinition(name="output_audio", label="生成的音频URL", type=ArgumentType.FILE),
    ]

    properties = {
        "api_key": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="DashScope API Key",
        ),
        "model": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="tts-1",
            label="模型",
            choices=["tts-1", "tts-1-ultra"]
        ),
        "voice": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="xiaoyun",
            label="音色",
            choices=["xiaoyun", "xiaogang", "xiaoxian", "xiaoyuan", "ruoxi", "yuting"]
        ),
        "speed": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=1.0,
            label="语速",
        ),
        "pitch": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.0,
            label="音调",
        ),
        "volume": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=1.0,
            label="音量",
        ),
        "output_format": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="mp3",
            label="输出格式",
            choices=["mp3", "wav", "pcm"]
        ),
    }

    def run(self, params, inputs=None):
        import requests
        import json
        
        # 1. 获取参数和输入
        api_key = params.get("api_key")
        if not api_key:
            raise Exception("请在属性栏设置 DashScope API Key")

        text = inputs.get("text", "")
        if not text:
            raise Exception("请输入要转换的文字")
            
        model = params.get("model", "tts-1")
        voice = params.get("voice", "xiaoyun")
        speed = params.get("speed", 1.0)
        pitch = params.get("pitch", 0.0)
        volume = params.get("volume", 1.0)
        output_format = params.get("output_format", "mp3")

        # 2. 构建请求
        url = 'https://dashscope.aliyuncs.com/api/v1/services/audio/tts/generation'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        data = {
            "model": model,
            "input": {
                "text": text
            },
            "parameters": {
                "voice": voice,
                "speed": speed,
                "pitch": pitch,
                "volume": volume,
                "format": output_format
            }
        }

        # 3. 发送请求
        self.logger.info(f"正在发送 TTS 请求，模型: {model}, 音色: {voice}")
        try:
            response = requests.post(url, headers=headers, json=data, timeout=60)
            response_json = response.json()
            
            # 错误处理
            if response.status_code != 200:
                error_msg = response_json.get('message', '未知错误')
                error_code = response_json.get('code', 'UnknownError')
                raise Exception(f"API 请求失败: [{error_code}] {error_msg}")

            # 4. 解析返回结果获取音频 URL
            # 同步模式直接返回 base64 音频
            output_data = response_json.get("output", {})
            
            # 尝试多种可能的返回格式
            audio_data = output_data.get("data") or output_data.get("audio") or {}
            audio_url = audio_data.get("url")
            
            if audio_url:
                self.logger.info(f"生成成功，音频URL: {audio_url}")
                return {"output_audio": audio_url}
            
            # 如果没有 URL，检查是否有 base64 数据
            audio_base64 = audio_data.get("audio") or audio_data.get("base64")
            if audio_base64:
                import base64
                # 解码并保存为临时文件
                audio_bytes = base64.b64decode(audio_base64)
                
                # 保存到文件并返回路径
                import tempfile
                import os
                with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{output_format}') as f:
                    f.write(audio_bytes)
                    audio_path = f.name
                
                self.logger.info(f"生成成功，音频已保存")
                return {"output_audio": audio_path}
            
            # 如果是异步任务，获取 task_id
            task_id = output_data.get("task_id")
            if task_id:
                self.logger.info(f"任务已提交，Task ID: {task_id}，开始轮询...")
                return self._poll_task(api_key, task_id, output_format)
            
            raise Exception("API 未返回有效的音频数据")

        except Exception as e:
            self.logger.error(f"TTS 执行出错: {str(e)}")
            raise e
    
    def _poll_task(self, api_key, task_id, output_format):
        import requests
        import time
        import tempfile
        
        query_url = f'https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}'
        headers = {
            'Authorization': f'Bearer {api_key}'
        }
        
        max_retries = 60
        for i in range(max_retries):
            time.sleep(2)
            
            status_res = requests.get(query_url, headers=headers)
            status_json = status_res.json()
            
            output = status_json.get("output", {})
            status = output.get("task_status")
            
            if status == "SUCCEEDED":
                audio_url = output.get("audio_url")
                if audio_url:
                    return {"output_audio": audio_url}
                
                # 检查 base64
                audio_data = output.get("data", {})
                audio_base64 = audio_data.get("audio") or audio_data.get("base64")
                if audio_base64:
                    import base64
                    audio_bytes = base64.b64decode(audio_base64)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{output_format}') as f:
                        f.write(audio_bytes)
                        return {"output_audio": f.name}
                        
            elif status == "FAILED":
                raise Exception(f"语音合成失败: {output.get('message')}")
            
            self.logger.info(f"任务状态: {status} ({i*2}s)")
            
        raise Exception("任务执行超时")
