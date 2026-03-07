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


class GeminiMultimodalComponent(BaseComponent):
    name = "Gemini 多模态生成"
    category = "API调用/多模态生成"
    description = "调用 Google Gemini 模型进行多模态内容生成和分析"
    requirements = "requests"

    inputs = [
        PortDefinition(name="prompt", label="文本提示词", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="image", label="输入图片(可选)", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
    ]
    
    outputs = [
        PortDefinition(name="output_text", label="生成的文本", type=ArgumentType.TEXT),
        PortDefinition(name="output_image", label="生成的图像(可选)", type=ArgumentType.IMAGE),
    ]

    properties = {
        "api_key": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="Google AI API Key",
        ),
        "model": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="gemini-2.0-flash-exp",
            label="模型",
            choices=["gemini-2.0-flash-exp", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.5-flash-8b"]
        ),
        "mode": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="text",
            label="生成模式",
            choices=["text", "image"]
        ),
        "temperature": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.9,
            label="温度",
        ),
        "max_tokens": PropertyDefinition(
            type=PropertyType.INT,
            default=2048,
            label="最大Token数",
        ),
        "top_p": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.95,
            label="Top P",
        ),
    }

    def run(self, params, inputs=None):
        import requests
        import json
        import base64
        import io
        from PIL import Image
        
        # 1. 获取参数和输入
        api_key = params.get("api_key")
        if not api_key:
            raise Exception("请在属性栏设置 Google AI API Key")

        prompt = inputs.get("prompt", "")
        image = inputs.get("image")
            
        model = params.get("model", "gemini-2.0-flash-exp")
        mode = params.get("mode", "text")
        temperature = params.get("temperature", 0.9)
        max_tokens = params.get("max_tokens", 2048)
        top_p = params.get("top_p", 0.95)

        # 2. 构建请求
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}'
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        # 构建内容
        contents = []
        
        # 如果有图片，先添加图片
        if image:
            # 将 PIL Image 转为 base64
            if isinstance(image, Image.Image):
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='PNG')
                img_base64 = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
            elif isinstance(image, str) and Path(image).exists():
                with open(image, 'rb') as f:
                    img_base64 = base64.b64encode(f.read()).decode('utf-8')
            else:
                img_base64 = image
                
            contents.append({
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": img_base64
                        }
                    }
                ]
            })
        
        # 添加文本提示
        if prompt:
            # 如果已经有内容（图片），追加到最后一个 part
            if contents and "parts" in contents[-1]:
                contents[-1]["parts"].append({"text": prompt})
            else:
                contents.append({
                    "parts": [
                        {"text": prompt}
                    ]
                })
        
        data = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": top_p,
            }
        }

        # 3. 发送请求
        self.logger.info(f"正在发送 Gemini 请求，模型: {model}, 模式: {mode}")
        
        # 如果是图像生成模式
        if mode == "image":
            # Gemini 2.0 支持图像生成
            data["generationConfig"]["responseModalities"] = ["image", "text"]
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=120)
            response_json = response.json()
            
            # 错误处理
            if response.status_code != 200:
                if "error" in response_json:
                    error_msg = response_json["error"]["message"]
                    raise Exception(f"API 请求失败: {error_msg}")
                raise Exception(f"API 请求失败: {response.text}")

            # 4. 解析返回结果
            candidates = response_json.get("candidates", [])
            if not candidates:
                raise Exception("API 未返回有效数据")
            
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            
            result_text = ""
            result_image = None
            
            for part in parts:
                if "text" in part:
                    result_text += part["text"]
                if "inlineData" in part:
                    # 有图像数据
                    img_data = part["inlineData"]["data"]
                    img_bytes = base64.b64decode(img_data)
                    result_image = Image.open(io.BytesIO(img_bytes))
            
            self.logger.info(f"生成成功")
            
            # 构建输出
            output = {"output_text": result_text}
            if result_image:
                output["output_image"] = result_image
                
            return output

        except Exception as e:
            self.logger.error(f"Gemini 执行出错: {str(e)}")
            raise e
