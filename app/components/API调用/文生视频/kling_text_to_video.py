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


class KlingTextToVideoComponent(BaseComponent):
    name = "可灵 AI 文生视频"
    category = "API调用/文生视频"
    description = "调用 Kling AI 模型根据文字描述生成视频"
    requirements = "requests"

    inputs = [
        PortDefinition(name="prompt", label="视频描述词", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    
    outputs = [
        PortDefinition(name="output_video", label="生成的视频URL", type=ArgumentType.FILE),
    ]

    properties = {
        "api_key": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="Kling AI API Key",
        ),
        "model": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="kling-v1-5",
            label="模型版本",
            choices=["kling-v1-5", "kling-v1", "kling-v1-5-fast"]
        ),
        "aspect_ratio": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="16:9",
            label="宽高比",
            choices=["16:9", "9:16", "1:1", "4:3", "3:4"]
        ),
        "duration": PropertyDefinition(
            type=PropertyType.INT,
            default=5,
            label="视频时长(秒)",
        ),
        "mode": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="std",
            label="生成模式",
            choices=["std", "pro"]
        ),
        "seed": PropertyDefinition(
            type=PropertyType.INT,
            default=-1,
            label="种子(-1为随机)",
        ),
    }

    def run(self, params, inputs=None):
        import requests
        import time
        
        # 1. 获取参数和输入
        api_key = params.get("api_key")
        if not api_key:
            raise Exception("请在属性栏设置 Kling AI API Key")

        prompt = inputs.get("prompt", "")
        if not prompt:
            raise Exception("请输入视频描述词")
            
        model = params.get("model", "kling-v1-5")
        aspect_ratio = params.get("aspect_ratio", "16:9")
        duration = params.get("duration", 5)
        mode = params.get("mode", "std")
        seed = params.get("seed", -1)

        # 2. 提交异步任务
        url = 'https://api.klingai.com/v1/images/generations'
        # 注意：实际 Kling API 端点可能需要根据官方文档调整
        # 这里使用常见的异步任务提交格式
        api_url = 'https://api.klingai.com/v1/videos/generations'
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        payload = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "mode": mode,
        }
        
        if seed > 0:
            payload["seed"] = seed

        self.logger.info(f"提交视频生成任务: {model}, 描述: {prompt[:50]}...")
        
        # 3. 创建任务
        response = requests.post(api_url, headers=headers, json=payload)
        res_json = response.json()

        if response.status_code != 200:
            error_msg = res_json.get('message', res_json.get('error', '未知错误'))
            raise Exception(f"任务提交失败: {error_msg}")

        # 4. 获取任务 ID
        task_id = res_json.get("data", {}).get("task_id") or res_json.get("task_id")
        if not task_id:
            # 某些 API 可能直接返回结果
            video_url = res_json.get("data", {}).get("video_url") or res_json.get("video_url")
            if video_url:
                self.logger.info("视频生成成功!")
                return {"output_video": video_url}
            raise Exception("无法获取任务ID或视频URL")

        self.logger.info(f"任务提交成功，Task ID: {task_id}，开始轮询...")

        # 5. 轮询任务状态
        query_url = f'https://api.klingai.com/v1/tasks/{task_id}'
        
        max_retries = 120  # 最多等待约 600 秒 (5分钟)
        for i in range(max_retries):
            time.sleep(5)  # 每 5 秒轮询一次
            
            status_res = requests.get(query_url, headers=headers)
            status_json = status_res.json()
            
            data = status_json.get("data", {})
            status = data.get("task_status") or data.get("status")
            self.logger.info(f"任务状态: {status} ({i*5}s)")
            
            if status == "SUCCEEDED":
                # 获取视频URL
                video_url = data.get("video_url") or data.get("result", {}).get("video_url")
                if video_url:
                    self.logger.info("视频生成成功!")
                    return {"output_video": video_url}
                raise Exception("任务成功但未返回视频URL")
            
            elif status == "FAILED":
                error_msg = data.get("message", "未知错误")
                raise Exception(f"视频生成失败: {error_msg}")
            
            elif status in ["PENDING", "RUNNING", "PROCESSING", "IN_PROGRESS"]:
                continue
            else:
                self.logger.info(f"状态: {status}")

        raise Exception("任务执行超时")
