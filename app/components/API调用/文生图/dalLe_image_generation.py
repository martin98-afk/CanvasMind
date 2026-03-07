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


class DALLEImageGenerationComponent(BaseComponent):
    name = "DALL-E 文生图"
    category = "API调用/文生图"
    description = "调用 OpenAI DALL-E 模型生成图像"
    requirements = "requests,Pillow"

    inputs = [
        PortDefinition(name="prompt", label="正向提示词", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="negative_prompt", label="反向提示词(可选)", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    
    outputs = [
        PortDefinition(name="output_image", label="生成的图像", type=ArgumentType.IMAGE),
    ]

    properties = {
        "api_key": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="OpenAI API Key",
        ),
        "model": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="dall-e-3",
            label="模型名称",
            choices=["dall-e-3", "dall-e-2"]
        ),
        "size": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="1024x1024",
            label="分辨率",
            choices=["1024x1024", "1792x1024", "1024x1792"]
        ),
        "quality": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="standard",
            label="质量",
            choices=["standard", "hd"]
        ),
        "style": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="natural",
            label="风格",
            choices=["natural", "vivid", "animated"]
        ),
        "n": PropertyDefinition(
            type=PropertyType.INT,
            default=1,
            label="生成数量",
        ),
    }

    def run(self, params, inputs=None):
        import requests
        import io
        from PIL import Image
        
        # 1. 获取参数和输入
        api_key = params.get("api_key")
        if not api_key:
            raise Exception("请在属性栏设置 OpenAI API Key")

        prompt = inputs.get("prompt", "")
        if not prompt:
            raise Exception("请输入提示词")
            
        model = params.get("model", "dall-e-3")
        size = params.get("size", "1024x1024")
        quality = params.get("quality", "standard")
        style = params.get("style", "natural")
        n = params.get("n", 1)

        # 2. 构建请求
        url = 'https://api.openai.com/v1/images/generations'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        # DALL-E 3 不支持 negative_prompt
        data = {
            "model": model,
            "prompt": prompt,
            "n": n,
            "size": size,
        }
        
        # 只有 DALL-E 3 支持 quality 和 style
        if model == "dall-e-3":
            data["quality"] = quality
            data["style"] = style

        # 3. 发送请求
        self.logger.info(f"正在发送 DALL-E 请求，模型: {model}, 分辨率: {size}")
        try:
            response = requests.post(url, headers=headers, json=data, timeout=120)
            response_json = response.json()
            
            # 错误处理
            if response.status_code != 200:
                error_msg = response_json.get('error', {}).get('message', '未知错误')
                raise Exception(f"API 请求失败: {error_msg}")

            # 4. 解析返回结果获取图片 URL
            images = response_json.get("data", [])
            if not images:
                raise Exception("API 未返回任何图像数据")
            
            # 返回第一张图片
            image_url = images[0].get("url")
            if not image_url:
                # DALL-E 3 可能返回 base64
                image_b64 = images[0].get("b64_json")
                if image_b64:
                    import base64
                    img_data = base64.b64decode(image_b64)
                    final_image = Image.open(io.BytesIO(img_data))
                    return {"output_image": final_image}
                raise Exception("API 未返回有效的图像数据")

            self.logger.info(f"生成成功，正在下载图片: {image_url}")

            # 5. 下载图片并转换为 PIL 对象
            img_res = requests.get(image_url, timeout=30)
            if img_res.status_code == 200:
                final_image = Image.open(io.BytesIO(img_res.content))
                return {
                    "output_image": final_image
                }
            else:
                raise Exception("图片下载失败")

        except Exception as e:
            self.logger.error(f"DALL-E 执行出错: {str(e)}")
            raise e
