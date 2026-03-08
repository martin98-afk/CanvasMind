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


class RunwayTextToVideoComponent(BaseComponent):
    name = "Runway 文生视频"
    category = "API调用/文生视频"
    description = "调用 Runway Gen 模型根据文字描述生成视频"
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
            label="Runway API Key",
        ),
        "model": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="gen3a_turbo",
            label="模型",
            choices=["gen3a_turbo", "gen3a"]
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
        "prompt_seed": PropertyDefinition(
            type=PropertyType.INT,
            default=0,
            label="种子(0为随机)",
        ),
    }

    def run(self, params, inputs=None):
        import requests
        import time
        
        # 1. 获取参数和输入
        api_key = params.get("api_key")
        if not api_key:
            raise Exception("请在属性栏设置 Runway API Key")

        prompt = inputs.get("prompt", "")
        if not prompt:
            raise Exception("请输入视频描述词")
            
        model = params.get("model", "gen3a_turbo")
        aspect_ratio = params.get("aspect_ratio", "16:9")
        duration = params.get("duration", 5)
        prompt_seed = params.get("prompt_seed", 0)

        # 2. 提交异步任务
        url = 'https://api.runwayml.com/v1/text_to_video'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        payload = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
        }
        
        if prompt_seed > 0:
            payload["seed"] = prompt_seed

        self.logger.info(f"提交视频生成任务: {model}, 描述: {prompt[:50]}...")
        
        # 3. 创建任务
        response = requests.post(url, headers=headers, json=payload)
        res_json = response.json()

        if response.status_code != 200 and response.status_code != 201:
            error_msg = res_json.get('error', '未知错误')
            raise Exception(f"任务提交失败: {error_msg}")

        # 4. 获取任务 ID
        task_id = res_json.get("id")
        if not task_id:
            raise Exception("无法获取任务ID")

        self.logger.info(f"任务提交成功，Task ID: {task_id}，开始轮询...")

        # 5. 轮询任务状态
        query_url = f'https://api.runwayml.com/v1/tasks/{task_id}'
        
        max_retries = 120  # 最多等待约 600 秒 (5分钟)
        for i in range(max_retries):
            time.sleep(5)  # 每 5 秒轮询一次
            
            status_res = requests.get(query_url, headers=headers)
            status_json = status_res.json()
            
            status = status_json.get("status")
            self.logger.info(f"任务状态: {status} ({i*5}s)")
            
            if status == "SUCCEEDED":
                # 获取视频URL
                output_data = status_json.get("output", {})
                if isinstance(output_data, list) and len(output_data) > 0:
                    video_url = output_data[0].get("url")
                elif isinstance(output_data, dict):
                    video_url = output_data.get("url")
                else:
                    video_url = str(output_data)
                    
                self.logger.info("视频生成成功!")
                return {"output_video": video_url}
            
            elif status == "FAILED":
                error_msg = status_json.get("error", "未知错误")
                raise Exception(f"视频生成失败: {error_msg}")
            
            elif status in ["PENDING", "RUNNING", "STARTING"]:
                continue
            else:
                self.logger.info(f"未知状态: {status}")

        raise Exception("任务执行超时")
