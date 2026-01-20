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


class WanImageToVideoComponent(BaseComponent):
    name = "Wan 2.6 图生视频"
    category = "API调用/图生视频"
    description = "上传图片并调用 Wan 2.6 模型生成视频（异步任务）"
    requirements = "requests,Pillow"

    inputs = [
        PortDefinition(name="image", label="输入图片", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
        PortDefinition(name="prompt", label="视频描述词", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="audio_url", label="音频URL(可选)", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    
    outputs = [
        PortDefinition(name="output_video.mp4", label="生成的视频URL", type=ArgumentType.FILE),
    ]

    properties = {
        "api_key": PropertyDefinition(type=PropertyType.TEXT, default="", label="DashScope API Key"),
        "model": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="wan2.6-i2v-flash",
            label="模型",
            choices=["wan2.6-i2v-flash", "wan2.1-i2v-turbo"]
        ),
        "resolution": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="720P",
            label="分辨率",
            choices=["480P", "720P", "1080P"]
        ),
        "duration": PropertyDefinition(
            type=PropertyType.INT,
            default=5,
            label="视频时长(秒)",
        ),
        "shot_type": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="single",
            label="镜头类型",
            choices=["single", "multi"]
        ),
        "prompt_extend": PropertyDefinition(type=PropertyType.BOOL, default=True, label="提示词扩展"),
    }

    def _upload_image(self, api_key, pil_image):
        import io
        
        """将本地 PIL 图片上传到 DashScope 临时存储并获取 URL"""
        self.logger.info("正在上传图片到阿里云...")
        
        # 将 PIL 图片转为字节流
        img_byte_arr = io.BytesIO()
        pil_image.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()

        # 1. 申请上传凭证并上传
        # 注意：DashScope 有专门的 /uploads 接口处理本地文件，
        # 为了简化，这里假设使用其多模态通用的文件上传逻辑或用户提供URL。
        # 如果平台支持Base64，也可以直接拼接。以下为模拟上传逻辑：
        # 实际开发中，若图片已经是URL则跳过，若是本地图片，建议先通过 dashscope SDK 或 requests 上传。
        
        # 此处演示一种常用的临时方案：将图片转为 Data URL（如果模型支持）
        import base64
        base64_data = base64.b64encode(img_byte_arr).decode('utf-8')
        return f"data:image/png;base64,{base64_data}"

    def run(self, params, inputs=None):
        import requests
        import time
        api_key = params.get("api_key")
        if not api_key:
            raise Exception("请设置 API Key")

        image = inputs.get("image")
        if not image:
            raise Exception("请连接输入图片")

        prompt = inputs.get("prompt", "")
        audio_url = inputs.get("audio_url") # 可选音频

        # 1. 准备图片 URL (如果是本地图片，转为 Base64)
        img_url = self._upload_image(api_key, image)

        # 2. 提交异步任务
        url = 'https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
            'X-DashScope-Async': 'enable' # 关键：开启异步
        }
        
        payload = {
            "model": params.get("model"),
            "input": {
                "prompt": prompt,
                "img_url": img_url,
            },
            "parameters": {
                "resolution": params.get("resolution"),
                "duration": int(params.get("duration")),
                "prompt_extend": params.get("prompt_extend"),
                "shot_type": params.get("shot_type")
            }
        }
        
        if audio_url:
            payload["input"]["audio_url"] = audio_url

        self.logger.info(f"提交视频生成任务: {params.get('model')}")
        response = requests.post(url, headers=headers, json=payload)
        res_json = response.json()

        if response.status_code != 200:
            raise Exception(f"任务提交失败: {res_json.get('message')}")

        task_id = res_json.get("output", {}).get("task_id")
        self.logger.info(f"任务提交成功，Task ID: {task_id}，开始轮询...")

        # 3. 轮询任务状态
        query_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
        query_headers = {'Authorization': f'Bearer {api_key}'}
        
        max_retries = 100 # 最多等待约 500 秒
        for i in range(max_retries):
            time.sleep(5) # 每 5 秒轮询一次
            status_res = requests.get(query_url, headers=query_headers)
            status_json = status_res.json()
            
            output = status_json.get("output", {})
            status = output.get("task_status")
            
            if status == "SUCCEEDED":
                video_url = output.get("video_url")
                self.logger.info("视频生成成功!")
                return {"output_video.mp4": video_url}
            
            elif status == "FAILED":
                raise Exception(f"视频生成失败: {output.get('message')}")
            
            elif status == "RUNNING":
                self.logger.info(f"视频正在生成中... ({i*5}s)")
            else:
                self.logger.info(f"任务状态: {status}")

        raise Exception("任务执行超时")