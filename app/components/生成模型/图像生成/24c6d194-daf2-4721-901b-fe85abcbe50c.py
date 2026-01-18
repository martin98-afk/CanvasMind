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


class KSamplerComponent(BaseComponent):
    name = "K采样器"
    category = "生成模型/图像生成"
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
        "denoise": PropertyDefinition(
            type=PropertyType.RANGE,
            default="1.00",
            label="去噪强度",
            min=0.0,
            max=1.0,
            step=0.01,
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
                        "output": {
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
        from diffusers import StableDiffusionImg2ImgPipeline, StableDiffusionPipeline
        from PIL import Image

        # 1. 解析参数
        model_id = params.get("model_id")
        prompt = inputs.get("prompt", "")
        n_prompt = inputs.get("negative_prompt", "")
        width = int(float(params.get("wid", 512)) // 8 * 8)
        height = int(float(params.get("heig", 512)) // 8 * 8)
        steps = int(float(params.get("steps", 20)))
        preview_step = int(params.preview_step)
        cfg = float(params.get("cfg", 7.0))
        seed = int(params.get("seed", -1))
        denoise = float(params.get("denoise", 1.0))
        scheduler_name = params.get("scheduler", "Euler a")

        if seed == -1:
            seed = np.random.randint(0, 2**16 - 1)
        generator = torch.Generator("cuda").manual_seed(int(seed))

        # 2. 模型加载与缓存
        # 无论文生图还是图生图，共用一套权重，根据需要转换 Pipeline 类型
        if model_id not in self._pipeline_cache:
            self.logger.info(f"正在加载模型: {model_id}")
            pipe = StableDiffusionPipeline.from_pretrained(
                model_id, torch_dtype=torch.float16, safety_checker=None
            ).to("cuda")
            self._pipeline_cache[model_id] = pipe
        else:
            pipe = self._pipeline_cache[model_id]

        pipe.scheduler = self._get_scheduler(scheduler_name, pipe.scheduler.config)

        # 3. 核心逻辑：判断是 Text2Img 还是 Img2Img (Latent重绘)
        latent_ndarray = inputs.get("latent_in")
        
        # 准备执行参数
        pipe_args = {
            "prompt": prompt,
            "negative_prompt": n_prompt,
            "num_inference_steps": steps,
            "guidance_scale": cfg,
            "generator": generator,
            "output_type": "latent",
        }

        # 实时回调
        def callback(pipe_ref, step, timestep, callback_kwargs):
            if step % preview_step == 0:
                self._send_preview(callback_kwargs.get("latents"), pipe_ref)
            return callback_kwargs
        
        pipe_args["callback_on_step_end"] = callback
        pipe_args["callback_on_step_end_tensor_inputs"] = ['latents']

        if latent_ndarray is not None and denoise < 1.0:
            # --- 图生图 / Latent 重绘模式 ---
            self.logger.info(f"进入潜空间重绘模式, Denoise: {denoise}")
            # 将 NumPy 转回 Tensor
            init_latents = torch.from_numpy(latent_ndarray).to("cuda", dtype=torch.float16)
            
            # 使用 Img2Img 的逻辑，但直接传入 Latents
            # 我们需要临时将 pipe 转为 Img2ImgPipeline (共享组件，不增加内存)
            img2img_pipe = StableDiffusionImg2ImgPipeline(**pipe.components)
            
            # 在 Img2Img 中，denoise 决定了跳过多少步
            # 注意：diffusers 的 Img2Img 接受 image 参数，可以是 Tensor 格式的 Latents
            # 必须缩放回像素值空间或直接处理，这里直接传 Latent Tensor 是可以的
            result_latent = img2img_pipe(
                image=init_latents, 
                strength=denoise, 
                **pipe_args
            ).images
        else:
            # --- 文生图 / 全噪声模式 ---
            self.logger.info("进入全噪声采样模式")
            if latent_ndarray is not None:
                # 如果 denoise=1.0，直接使用输入的噪声
                pipe_args["latents"] = torch.from_numpy(latent_ndarray).to("cuda", dtype=torch.float16)
            else:
                # 否则由 pipe 生成随机噪声
                pipe_args["width"] = width
                pipe_args["height"] = height
            
            result_latent = pipe(**pipe_args).images

        # 4. 结果处理
        with torch.no_grad():
            # 解码预览图
            decoded = pipe.vae.decode(result_latent / 0.18215).sample
            decoded = (decoded / 2 + 0.5).clamp(0, 1).cpu().permute(0, 2, 3, 1).float().numpy()
            final_image = Image.fromarray((decoded[0] * 255).astype(np.uint8))

        return {
            "output_image": final_image,
            "latent_out": result_latent.cpu().numpy()
        }