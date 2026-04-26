# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path

base_path = Path(__file__).parent.parent / "base.py" if (Path(__file__).parent.parent / "base.py").exists() else Path(__file__).parent.parent.parent / "base.py"
spec = importlib.util.spec_from_file_location("base", str(base_path))
base_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base_module)

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
    requirements = "requests,Pillow"

    inputs = [
        PortDefinition(name="prompt", label="文本提示词",
                       type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="image", label="输入图片(可选)",
                       type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
    ]

    outputs = [
        PortDefinition(name="output_text", label="生成的文本",
                       type=ArgumentType.TEXT),
        PortDefinition(name="output_image", label="生成的图像(可选)",
                       type=ArgumentType.IMAGE),
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

    # 常见图片格式映射
    IMAGE_MIME_TYPES = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.bmp': 'image/bmp',
    }

    def _get_image_as_base64(self, image):
        """将图片转换为 base64 和 mime_type"""
        import base64
        import io
        
        if isinstance(image, str):
            # 文件路径
            path = Path(image)
            if path.exists():
                mime_type = self.IMAGE_MIME_TYPES.get(path.suffix.lower(), 'image/png')
                with open(path, 'rb') as f:
                    data = f.read()
                return base64.b64encode(data).decode('utf-8'), mime_type
            else:
                # 已经是 base64 字符串
                return image, 'image/png'
        elif isinstance(image, bytes):
            # 原始字节数据，默认当作 PNG
            return base64.b64encode(image).decode('utf-8'), 'image/png'
        elif hasattr(image, 'save'):
            # PIL Image 对象
            mime_type = getattr(image, 'format', 'PNG').lower()
            mime_type = f'image/{mime_type}' if mime_type != 'jpeg' else 'image/jpeg'
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format=mime_type.split('/')[-1].upper())
            return base64.b64encode(img_byte_arr.getvalue()).decode('utf-8'), mime_type
        
        # 默认返回
        return str(image), 'image/png'

    def run(self, params, inputs=None):
        import requests
        import base64
        import io
        from PIL import Image

        # 1. 获取参数和输入
        api_key = params.get("api_key")
        if not api_key:
            raise Exception("请在属性栏设置 Google AI API Key")

        prompt = inputs.get("prompt", "") if inputs else ""
        image = inputs.get("image") if inputs else None

        model = params.get("model", "gemini-2.0-flash-exp")
        mode = params.get("mode", "text")
        temperature = params.get("temperature", 0.9)
        max_tokens = params.get("max_tokens", 2048)
        top_p = params.get("top_p", 0.95)

        # 空 prompt 检查（图片模式除外）
        if not prompt and not image and mode == "text":
            raise Exception("请提供文本提示词或输入图片")

        # 2. 构建请求
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}'

        # 3. 构建 contents
        contents = []
        
        if image:
            img_base64, mime_type = self._get_image_as_base64(image)
            content_block = {"parts": [{"inline_data": {"mime_type": mime_type, "data": img_base64}}]}
            contents.append(content_block)
            
            # 如果有 prompt，追加到图片之后
            if prompt:
                contents.append({"parts": [{"text": prompt}]})
        elif prompt:
            contents.append({"parts": [{"text": prompt}]})

        # 构建请求数据
        data = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": top_p,
            }
        }

        # 图像生成模式
        if mode == "image":
            data["generationConfig"]["responseModalities"] = ["image", "text"]

        # 4. 发送请求
        self.logger.info(f"正在发送 Gemini 请求，模型: {model}, 模式: {mode}")

        try:
            response = requests.post(url, headers={'Content-Type': 'application/json'}, json=data, timeout=120)
            response_json = response.json()

            # 错误处理
            if response.status_code != 200:
                error_msg = response_json.get("error", {}).get("message", response.text)
                raise Exception(f"API 请求失败: {error_msg}")

            # 检查 promptFeedback 错误
            prompt_feedback = response_json.get("promptFeedback")
            if prompt_feedback:
                block_reason = prompt_feedback.get("blockReason")
                if block_reason:
                    raise Exception(f"内容被拦截: {block_reason}")

            # 5. 解析返回结果
            candidates = response_json.get("candidates", [])
            if not candidates:
                raise Exception("API 未返回有效数据")

            result_text = ""
            result_image = None

            for candidate in candidates:
                parts = candidate.get("content", {}).get("parts", [])
                for part in parts:
                    if "text" in part:
                        result_text += part["text"]
                    elif "inlineData" in part:
                        img_data = part["inlineData"]["data"]
                        img_bytes = base64.b64decode(img_data)
                        result_image = Image.open(io.BytesIO(img_bytes))

            self.logger.info("生成成功")

            output = {"output_text": result_text}
            if result_image:
                output["output_image"] = result_image

            return output

        except requests.exceptions.Timeout:
            raise Exception("请求超时，请检查网络或增加超时时间")
        except requests.exceptions.RequestException as e:
            raise Exception(f"网络请求错误: {str(e)}")
        except Exception as e:
            self.logger.error(f"Gemini 执行出错: {str(e)}")
            raise