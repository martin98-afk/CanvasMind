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


class StableDiffusionImageComponent(BaseComponent):
    name = "Stable Diffusion 文生图"
    category = "API调用/文生图"
    description = "调用 Stability AI Stable Diffusion 模型生成图像"
    requirements = "requests,Pillow"

    inputs = [
        PortDefinition(name="prompt", label="正向提示词", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="negative_prompt", label="反向提示词", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    
    outputs = [
        PortDefinition(name="output_image", label="生成的图像", type=ArgumentType.IMAGE),
    ]

    properties = {
        "api_key": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="Stability AI API Key",
        ),
        "model": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="stable-image-3.0",
            label="模型名称",
            choices=["stable-image-3.0", "stable-image-3.0-fast", "stable-diffusion-xl-1024-v1-0"]
        ),
        "aspect_ratio": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="1:1",
            label="宽高比",
            choices=["1:1", "16:9", "9:16", "4:3", "3:4", "21:9", "9:21"]
        ),
        "seed": PropertyDefinition(
            type=PropertyType.INT,
            default=0,
            label="随机种子(0为随机)",
        ),
        "prompt_boost": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="提示词增强",
        ),
    }

    def run(self, params, inputs=None):
        import requests
        import io
        from PIL import Image
        import base64
        
        # 1. 获取参数和输入
        api_key = params.get("api_key")
        if not api_key:
            raise Exception("请在属性栏设置 Stability AI API Key")

        prompt = inputs.get("prompt", "")
        if not prompt:
            raise Exception("请输入提示词")
            
        negative_prompt = inputs.get("negative_prompt", "")
        model = params.get("model", "stable-image-3.0")
        aspect_ratio = params.get("aspect_ratio", "1:1")
        seed = params.get("seed", 0)
        prompt_boost = params.get("prompt_boost", True)

        # 2. 构建请求
        url = 'https://api.stability.ai/v2beta/image-generation'
        
        # 根据模型选择正确的端点
        if "stable-image" in model:
            url = f'https://api.stability.ai/v2beta/image-generation/{model}'
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Accept': 'application/json'
        }
        
        data = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "seed": seed if seed > 0 else None,
            "prompt_boost": prompt_boost,
        }
        
        if negative_prompt:
            data["negative_prompt"] = negative_prompt

        # 3. 发送请求
        self.logger.info(f"正在发送 Stable Diffusion 请求，模型: {model}, 宽高比: {aspect_ratio}")
        try:
            response = requests.post(url, headers=headers, json=data, timeout=120)
            response_json = response.json()
            
            # 错误处理
            if response.status_code != 200:
                if "errors" in response_json:
                    error_msg = response_json["errors"][0].get("message", '未知错误')
                else:
                    error_msg = response_json.get('message', '未知错误')
                raise Exception(f"API 请求失败: {error_msg}")

            # 4. 解析返回结果获取图片
            artifacts = response_json.get("artifacts", [])
            if not artifacts:
                raise Exception("API 未返回任何图像数据")
            
            # 返回第一张图片
            base64_image = artifacts[0].get("base64")
            if not base64_image:
                raise Exception("API 未返回有效的图像数据")

            self.logger.info("生成成功，正在解码图片")

            # 5. 解码图片并转换为 PIL 对象
            img_data = base64.b64decode(base64_image)
            final_image = Image.open(io.BytesIO(img_data))
            return {
                "output_image": final_image
            }

        except Exception as e:
            self.logger.error(f"Stable Diffusion 执行出错: {str(e)}")
            raise e
