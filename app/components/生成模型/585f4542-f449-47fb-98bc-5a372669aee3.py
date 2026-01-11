# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py"
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


class KSamplerComponent(BaseComponent):
    name = "K采样器 (优化版)"
    category = "生成模型"
    description = "复现 ComfyUI 核心采样逻辑，支持实时预览和多种采样器"
    requirements = "diffusers,torch,transformers,accelerate,Pillow,numpy"
    
    # 类级别变量，用于在 Subprocess 常驻模式下缓存模型
    _pipeline_cache = {}

    inputs = [
        PortDefinition(name="prompt", label="正向提示词", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="negative_prompt", label="负向提示词", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output_image", label="生成的图像", type=ArgumentType.IMAGE),
    ]
    
    properties = {
        "model_id": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="runwayml/stable-diffusion-v1-5",
            label="模型路径",
            choices=["runwayml/stable-diffusion-v1-5", "stabilityai/stable-diffusion-2-1"]
        ),
        "scheduler": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="Euler a",
            label="采样器 (Scheduler)",
            choices=["Euler a", "Euler", "DPM++ 2M Karras", "DDIM", "PNDM"]
        ),
        "wid": PropertyDefinition(
            type=PropertyType.RANGE,
            default="512.0",
            label="宽度",
            min=300.0,
            max=1000.0,
            step=10.0,
        ),
        "heig": PropertyDefinition(
            type=PropertyType.RANGE,
            default="512.0",
            label="高度",
            min=300.0,
            max=1000.0,
            step=10.0,
        ),
        "steps": PropertyDefinition(
            type=PropertyType.RANGE,
            default="20.0",
            label="迭代步数",
            min=0.0,
            max=50.0,
            step=1.0,
        ),
        "cfg": PropertyDefinition(
            type=PropertyType.RANGE,
            default="7.0",
            label="提示词引导系数(CFG)",
            min=0.0,
            max=100.0,
            step=1.0,
        ),
        "seed": PropertyDefinition(
            type=PropertyType.INT,
            default=-1,
            label="随机种子",
        ),
        "preview_step": PropertyDefinition(
            type=PropertyType.INT,
            default=5,
            label="预览频率(步)",
        ),
    }

    def _get_scheduler(self, name, config):
        """动态切换采样器"""
        from diffusers import (
            EulerAncestralDiscreteScheduler, EulerDiscreteScheduler, 
            DPMSolverMultistepScheduler, DDIMScheduler, PNDMScheduler
        )
        schedulers = {
            "Euler a": EulerAncestralDiscreteScheduler.from_config(config),
            "Euler": EulerDiscreteScheduler.from_config(config),
            "DPM++ 2M Karras": DPMSolverMultistepScheduler.from_config(config, use_karras_sigmas=True),
            "DDIM": DDIMScheduler.from_config(config),
            "PNDM": PNDMScheduler.from_config(config),
        }
        return schedulers.get(name, schedulers["Euler a"])

    def _send_preview(self, latents, pipe):
        """将中间 Latent 转换为预览图并发送"""
        import io
        import base64
        import torch
        import numpy as np
        from PIL import Image
        
        with torch.no_grad():
            # 这里的简单解码：使用 VAE 快速解码
            # 如果为了性能，可以只取 Latent 的前三个通道作为 RGB 预览
            latents = 1 / 0.18215 * latents
            image = pipe.vae.decode(latents).sample
            image = (image / 2 + 0.5).clamp(0, 1)
            image = image.cpu().permute(0, 2, 3, 1).float().numpy()
            image = (image[0] * 255).astype(np.uint8)
            pil_img = Image.fromarray(image).resize((256, 256)) # 预览图不需要太大
            
            buffered = io.BytesIO()
            pil_img.save(buffered, format="JPEG", quality=70)
            img_str = base64.b64encode(buffered.getvalue()).decode()
            
            # 使用特定格式通知主进程拦截
            self.emit_custom_message(
                method="stream.output",
                params={
                    "output_image": {
                        "data": f"data:image/jpeg;base64,{img_str}",
                        "data_type": "str"
                    }
                }
            )

    def run(self, params, inputs=None):
        import torch
        import numpy as np
        from diffusers import StableDiffusionPipeline

        # 1. 获取参数并规范化（确保是 8 的倍数）
        model_id = params.get("model_id")
        prompt = inputs.get("prompt", "a beautiful landscape")
        n_prompt = inputs.get("negative_prompt", "")
        width = (params.get("wid", 512) // 8) * 8
        height = (params.get("heig", 512) // 8) * 8
        steps = int(params.get("steps", 20))
        cfg = params.get("cfg", 7.5)
        seed = params.get("seed", -1)
        scheduler_name = params.get("scheduler", "Euler a")
        preview_step = params.get("preview_step", 5)

        if seed == -1:
            seed = np.random.randint(0, 2**16 - 1)
        generator = torch.Generator("cuda").manual_seed(int(seed))

        # 2. 缓存化模型加载
        if model_id not in self._pipeline_cache:
            self.logger.info(f"正在加载模型 {model_id}...")
            pipe = StableDiffusionPipeline.from_pretrained(
                model_id, torch_dtype=torch.float16, safety_checker=None
            ).to("cuda")
            self._pipeline_cache[model_id] = pipe
        else:
            pipe = self._pipeline_cache[model_id]

        # 3. 切换采样器
        pipe.scheduler = self._get_scheduler(scheduler_name, pipe.scheduler.config)

        # 4. 定义实时回调函数
        def latents_callback(pipe_ref, step, timestep, callback_kwargs):
            if step % preview_step == 0:
                latents = callback_kwargs.get("latents")
                self._send_preview(latents, pipe_ref)
            return callback_kwargs

        # 5. 执行推理
        self.logger.info(f"开始采样生成, Seed: {seed}")
        result = pipe(
            prompt=prompt,
            negative_prompt=n_prompt,
            width=width,
            height=height,
            num_inference_steps=steps,
            guidance_scale=cfg,
            generator=generator,
            callback_on_step_end=latents_callback,
            callback_on_step_end_tensor_inputs=['latents']
        )

        image = result.images[0]
        self.logger.info("图像生成完成")

        # 6. 返回图像 (你的框架会自动处理 PIL 对象)
        return {"output_image": image}