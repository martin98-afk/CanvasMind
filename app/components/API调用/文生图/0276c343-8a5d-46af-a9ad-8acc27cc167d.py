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


class WanTextToImageComponent(BaseComponent):
    name = "Wan 2.6 文生图"
    category = "API调用/文生图"
    description = "调用阿里云 DashScope Wan 2.6 模型生成图像"
    requirements = "requests,Pillow,numpy"

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
            label="DashScope API Key",
        ),
        "model": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="wan2.6-t2i",
            label="模型名称",
            choices=["wan2.6-t2i", "z-image-turbo", "wanx-v1"]
        ),
        "size": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="1024*1024",
            label="分辨率",
            choices=["1024*1024", "1280*1280", "720*1280", "1280*720"]
        ),
        "prompt_extend": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="提示词自动扩展",
        ),
        "watermark": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="添加水印",
        ),
    }

    def run(self, params, inputs=None):
        import requests
        import json
        import io
        from PIL import Image
        import numpy as np
        # 1. 获取参数和输入
        api_key = params.get("api_key")
        if not api_key:
            raise Exception("请在属性栏设置 DashScope API Key")

        prompt = inputs.get("prompt", "")
        negative_prompt = inputs.get("negative_prompt", params.get("negative_prompt", ""))
        model = params.get("model", "wan2.6-t2i")
        size = params.get("size", "1024*1024")
        prompt_extend = params.get("prompt_extend", True)
        watermark = params.get("watermark", False)

        # 2. 构建符合 DashScope 标准的请求体
        url = 'https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        data = {
            "model": model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"text": prompt}
                        ]
                    }
                ]
            },
            "parameters": {
                "prompt_extend": prompt_extend,
                "watermark": watermark,
                "n": 1,
                "negative_prompt": negative_prompt,
                "size": size
            }
        }

        # 3. 发送请求
        self.logger.info(f"正在发送 Wan 2.6 请求，模型: {model}, 分辨率: {size}")
        try:
            response = requests.post(url, headers=headers, json=data, timeout=60)
            response_json = response.json()
            
            # 错误处理
            if response.status_code != 200:
                error_msg = response_json.get('message', '未知错误')
                error_code = response_json.get('code', 'UnknownError')
                raise Exception(f"API 请求失败: [{error_code}] {error_msg}")

            # 4. 解析返回结果获取图片 URL
            # 路径: output -> choices[0] -> message -> content[0] -> image
            choices = response_json.get("output", {}).get("choices", [])
            if not choices:
                raise Exception("API 未返回任何图像数据")
            
            image_url = choices[0]["message"]["content"][0]["image"]
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
            self.logger.error(f"Wan 2.6 执行出错: {str(e)}")
            raise e