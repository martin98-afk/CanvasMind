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


class InpaintSamplerComponent(BaseComponent):
    name = "局部重绘采样器"
    category = "生成模型"
    description = "基于遮罩(Mask)对图像特定区域进行重绘或扩图"
    requirements = "diffusers,torch,transformers,accelerate,Pillow,numpy"
    
    _pipeline_cache = {}

    inputs = [
        PortDefinition(name="prompt", label="正向提示词", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="negative_prompt", label="负向提示词", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="image", label="原始图像", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
        PortDefinition(name="mask", label="遮罩图像", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
    ]
    
    outputs = [
        PortDefinition(name="output_image", label="生成的图像", type=ArgumentType.IMAGE),
        PortDefinition(name="latent_out", label="潜空间输出", type=ArgumentType.ARRAY),
    ]
    
    properties = {
        "model_id": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="runwayml/stable-diffusion-inpainting",
            label="重绘模型",
            choices=["runwayml/stable-diffusion-inpainting", "stabilityai/stable-diffusion-2-inpainting", "Lykon/dreamshaper-8-inpainting"]
        ),
        "scheduler": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="Euler a",
            label="采样器 (Scheduler)",
            choices=["Euler a", "Euler", "DPM++ 2M Karras", "DDIM"]
        ),
        "steps": PropertyDefinition(
            type=PropertyType.RANGE,
            default="20.0",
            label="迭代步数",
            min=1.0,
            max=100.0,
            step=1.0,
        ),
        "cfg": PropertyDefinition(
            type=PropertyType.RANGE,
            default="7.5",
            label="提示词引导系数(CFG)",
            min=1.0,
            max=20.0,
            step=0.5,
        ),
        "denoise": PropertyDefinition(
            type=PropertyType.RANGE,
            default="1.00",
            label="重绘强度 (Denoise)",
            min=0.0,
            max=1.0,
            step=0.01,
        ),
        "seed": PropertyDefinition(
            type=PropertyType.INT,
            default=-1,
            label="随机种子",
        ),
        "preview_step": PropertyDefinition(
            type=PropertyType.INT,
            default=5,
            label="预览频率",
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
        """发送实时预览 (复用之前的解码逻辑)"""
        import io, base64, torch, numpy as np
        from PIL import Image
        try:
            with torch.no_grad():
                # VAE 解码潜空间
                latents = 1 / 0.18215 * latents
                image = pipe.vae.decode(latents).sample
                image = (image / 2 + 0.5).clamp(0, 1).cpu().permute(0, 2, 3, 1).float().numpy()
                image = (image[0] * 255).astype(np.uint8)
                pil_img = Image.fromarray(image).resize((256, 256))
                
                buffered = io.BytesIO()
                pil_img.save(buffered, format="JPEG", quality=70)
                img_str = base64.b64encode(buffered.getvalue()).decode()
                
                self.emit_custom_message(
                    method="stream.output",
                    params={"output": {"data": f"data:image/jpeg;base64,{img_str}", "data_type": "image"}},
                    extra={"display": True}
                )
        except Exception: pass

    def run(self, params, inputs=None):
        import torch
        import numpy as np
        from diffusers import StableDiffusionInpaintPipeline
        from PIL import Image

        # 1. 获取输入数据
        init_image = inputs.get("image")
        mask_image = inputs.get("mask")
        prompt = inputs.get("prompt", "")
        n_prompt = inputs.get("negative_prompt", "")
        
        if init_image is None or mask_image is None:
            raise ValueError("局部重绘需要输入原始图像和遮罩图像")

        # 2. 参数预处理
        model_id = params.get("model_id")
        steps = int(float(params.get("steps", 20)))
        cfg = float(params.get("cfg", 7.5))
        denoise = float(params.get("denoise", 1.0))
        seed = int(params.get("seed", -1))
        if seed == -1:
            seed = np.random.randint(0, 2**16 - 1)
        generator = torch.Generator("cuda").manual_seed(seed)

        # 3. 图像尺寸对齐 (必须是8的倍数)
        width, height = init_image.size
        new_width = (width // 8) * 8
        new_height = (height // 8) * 8
        if (new_width, new_height) != (width, height):
            init_image = init_image.resize((new_width, new_height), resample=Image.LANCZOS)
            mask_image = mask_image.resize((new_width, new_height), resample=Image.NEAREST)

        # 4. 加载模型 (带缓存)
        if model_id not in self._pipeline_cache:
            self.logger.info(f"正在加载重绘模型: {model_id}")
            # 注意：Inpaint 专门使用 StableDiffusionInpaintPipeline
            pipe = StableDiffusionInpaintPipeline.from_pretrained(
                model_id, 
                torch_dtype=torch.float16,
                safety_checker=None 
            ).to("cuda")
            self._pipeline_cache[model_id] = pipe
        else:
            pipe = self._pipeline_cache[model_id]

        pipe.scheduler = self._get_scheduler(params.get("scheduler"), pipe.scheduler.config)

        # 5. 执行生成
        def callback(pipe_ref, step, timestep, callback_kwargs):
            if step % int(params.preview_step) == 0:
                self._send_preview(callback_kwargs.get("latents"), pipe_ref)
            return callback_kwargs

        output = pipe(
            prompt=prompt,
            negative_prompt=n_prompt,
            image=init_image,
            mask_image=mask_image,
            num_inference_steps=steps,
            guidance_scale=cfg,
            strength=denoise,  # 对于 Inpaint，strength 决定了对原图的改动程度
            generator=generator,
            callback_on_step_end=callback,
            callback_on_step_end_tensor_inputs=['latents'],
            output_type="pil" # 最终输出 PIL 图像
        )

        final_image = output.images[0]
        
        # 6. 返回结果 (如果需要 latent_out 供下一级使用，需要手动转一下)
        # 这里为了简单直接返回 PIL 和 None 占位，或者重新编码
        return {
            "output_image": final_image,
            "latent_out": None # Inpaint Pipeline 默认输出图像，如需 Latent 可通过 vae.encode 获取
        }