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
    name = "K采样器"
    category = "生成模型"
    description = "复现 ComfyUI 核心采样逻辑，支持实时预览和多种采样器"
    requirements = "diffusers,torch,transformers,accelerate,Pillow,numpy"
    
    # 类级别变量，用于在 Subprocess 常驻模式下缓存模型
    _pipeline_cache = {}

    inputs = [
        PortDefinition(name="prompt", label="正向提示词", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="negative_prompt", label="负向提示词", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="latent_in", label="潜空间输入", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output_image", label="生成的图像", type=ArgumentType.IMAGE),
        PortDefinition(name="latent_out", label="潜空间输出", type=ArgumentType.ARRAY),
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
        from diffusers import (
            EulerAncestralDiscreteScheduler, EulerDiscreteScheduler, 
            DPMSolverMultistepScheduler, DDIMScheduler
        )
        schedulers = {
            "Euler a": EulerAncestralDiscreteScheduler.from_config(config),
            "Euler": EulerDiscreteScheduler.from_config(config),
            "DPM++ 2M Karras": DPMSolverMultistepScheduler.from_config(config, use_karras_sigmas=True),
            "DDIM": DDIMScheduler.from_config(config),
        }
        return schedulers.get(name, schedulers["Euler a"])

    def _send_preview(self, latents, pipe):
        """发送实时预览"""
        import io
        import base64
        import torch
        import numpy as np
        from PIL import Image
        try:
            with torch.no_grad():
                # 潜空间解码
                latents = 1 / 0.18215 * latents
                image = pipe.vae.decode(latents).sample
                image = (image / 2 + 0.5).clamp(0, 1)
                image = image.cpu().permute(0, 2, 3, 1).float().numpy()
                image = (image[0] * 255).astype(np.uint8)
                pil_img = Image.fromarray(image).resize((256, 256))
                
                buffered = io.BytesIO()
                pil_img.save(buffered, format="JPEG", quality=70)
                img_str = base64.b64encode(buffered.getvalue()).decode()
                
                # 构建流式协议消息
                self.emit_custom_message(
                    method="stream.output",
                    params={
                        "output_image": {
                            "data": f"data:image/jpeg;base64,{img_str}",
                            "data_type": "image"
                        }
                    },
                    extra={"display": True}
                )
        except Exception as e:
            pass

    def run(self, params, inputs=None):
        import torch
        import numpy as np
        from diffusers import StableDiffusionPipeline
        from PIL import Image

        # 1. 解析参数
        model_id = params.get("model_id")
        prompt = inputs.get("prompt", "")
        n_prompt = inputs.get("negative_prompt", "")
        width = int(float(params.get("wid", 512)) // 8 * 8)
        height = int(float(params.get("heig", 512)) // 8 * 8)
        steps = int(float(params.get("steps", 20)))
        cfg = float(params.get("cfg", 7.0))
        seed = int(params.get("seed", -1))
        scheduler_name = params.get("scheduler", "Euler a")

        if seed == -1:
            seed = np.random.randint(0, 2**16 - 1)
        generator = torch.Generator("cuda").manual_seed(int(seed))

        # 2. 转换输入的 Latent (从字节流还原)
        latent_ndarray = inputs.get("latent_in")
        latents = None
        if latent_ndarray is not None:
            self.logger.info("检测到输入 Latent，正在载入...")
            # 转回 Torch 张量送入显存
            latents = torch.from_numpy(latent_ndarray).to("cuda", dtype=torch.float16)

        # 3. 加载模型
        if model_id not in self._pipeline_cache:
            pipe = StableDiffusionPipeline.from_pretrained(
                model_id, torch_dtype=torch.float16, safety_checker=None
            ).to("cuda")
            self._pipeline_cache[model_id] = pipe
        else:
            pipe = self._pipeline_cache[model_id]

        pipe.scheduler = self._get_scheduler(scheduler_name, pipe.scheduler.config)

        # 4. 实时回调
        def callback(pipe_ref, step, timestep, callback_kwargs):
            if step % 5 == 0:
                self._send_preview(callback_kwargs.get("latents"), pipe_ref)
            return callback_kwargs

        # 5. 执行采样
        self.logger.info("开始执行 K-Sampling...")
        # output_type="latent" 让它返回 Tensor 而不是 PIL 图像
        output = pipe(
            prompt=prompt,
            negative_prompt=n_prompt,
            width=width,
            height=height,
            num_inference_steps=steps,
            guidance_scale=cfg,
            generator=generator,
            latents=latents,
            callback_on_step_end=callback,
            callback_on_step_end_tensor_inputs=['latents'],
            output_type="latent"
        ).images # 这里的 .images 实际上是 Tensor [1, 4, h/8, w/8]

        # 6. 生成最终结果
        # A. 生成预览图（用于本节点的 Image 显示）
        with torch.no_grad():
            final_img_tensor = pipe.vae.decode(output / 0.18215).sample
            final_img_tensor = (final_img_tensor / 2 + 0.5).clamp(0, 1).cpu().permute(0, 2, 3, 1).float().numpy()
            final_image = Image.fromarray((final_img_tensor[0] * 255).astype(np.uint8))

        # B. 转换 Latent 为 NumPy 字节流（用于输出给下游节点）
        # 必须先 .cpu().numpy()
        latent_out_bytes = output.cpu().numpy()

        return {
            "output_image": final_image,
            "latent_out": latent_out_bytes
        }