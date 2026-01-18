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
    name = "K采样器(全版本模型对象输入)"
    category = "生成模型"
    description = "兼容 SD1.5/XL/SD3 的通用采样器。自动识别模型架构，支持潜空间重绘与实时预览。"
    requirements = "diffusers,torch,transformers,accelerate,Pillow,numpy"

    inputs = [
        PortDefinition(name="prompt", label="正向提示词", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="negative_prompt", label="负向提示词", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="latent_in", label="潜空间输入(可选)", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
        PortDefinition(name="model", label="模型对象", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output_image", label="生成的图像", type=ArgumentType.IMAGE),
        PortDefinition(name="latent_out", label="潜空间输出", type=ArgumentType.ARRAY),
    ]
    
    properties = {
        "scheduler": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="Euler a",
            label="采样器 (SD1.5/XL选此)",
            choices=["Euler a", "Euler", "DPM++ 2M Karras", "DDIM", "PNDM"]
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
            default="7.0",
            label="CFG Scale",
            min=0.0,
            max=20.0,
            step=0.5,
        ),
        "seed": PropertyDefinition(
            type=PropertyType.INT,
            default=-1,
            label="随机种子",
        ),
        "denoise": PropertyDefinition(
            type=PropertyType.RANGE,
            default="1.00",
            label="去噪强度",
            min=0.0,
            max=1.0,
            step=0.01,
        ),
        "preview_step": PropertyDefinition(
            type=PropertyType.INT,
            default=5,
            label="预览频率(步)",
        ),
        "wid": PropertyDefinition(
            type=PropertyType.INT,
            default=512,
            label="宽度",
        ),
        "heig": PropertyDefinition(
            type=PropertyType.INT,
            default=512,
            label="高度",
        ),
    }

    def _get_scheduler(self, name, config, is_sd3=False):
        # 局部导入调度器
        from diffusers import (
            EulerAncestralDiscreteScheduler, EulerDiscreteScheduler, 
            DPMSolverMultistepScheduler, DDIMScheduler,
            FlowMatchEulerDiscreteScheduler
        )
        
        # 如果是 SD3 模型或配置中包含 shift 参数（FlowMatch 特征）
        if is_sd3 or "shift" in config:
            return FlowMatchEulerDiscreteScheduler.from_config(config)
        
        schedulers = {
            "Euler a": EulerAncestralDiscreteScheduler.from_config(config),
            "Euler": EulerDiscreteScheduler.from_config(config),
            "DPM++ 2M Karras": DPMSolverMultistepScheduler.from_config(config, use_karras_sigmas=True),
            "DDIM": DDIMScheduler.from_config(config),
        }
        return schedulers.get(name, schedulers["Euler a"])

    def _send_preview(self, latents, vae):
        """支持动态缩放系数的预览发送，所有依赖函数内导入"""
        import io
        import base64
        import torch
        import numpy as np
        from PIL import Image
        
        try:
            with torch.no_grad():
                # 获取缩放系数：SD1.5=0.18215, SDXL=0.13025, SD3=1.0
                scaling_factor = getattr(vae.config, "scaling_factor", 0.18215)
                latents = 1 / scaling_factor * latents
                
                image = vae.decode(latents).sample
                image = (image / 2 + 0.5).clamp(0, 1)
                image = image.cpu().permute(0, 2, 3, 1).float().numpy()
                image = (image[0] * 255).astype(np.uint8)
                pil_img = Image.fromarray(image).resize((256, 256))
                
                buffered = io.BytesIO()
                pil_img.save(buffered, format="JPEG", quality=70)
                img_str = base64.b64encode(buffered.getvalue()).decode()
                
                self.emit_message(
                    method="display_image",
                    params={"output": {"data": f"data:image/jpeg;base64,{img_str}", "data_type": "image"}},
                )
        except Exception:
            pass

    def run(self, params, inputs=None):
        # 1. 核心库函数内导入
        import torch
        import numpy as np
        from PIL import Image
        from diffusers import (
            StableDiffusionPipeline, 
            StableDiffusionImg2ImgPipeline,
            StableDiffusion3Pipeline, 
            StableDiffusion3Img2ImgPipeline
        )

        # 2. 获取并校验模型对象
        pipe = inputs.get("model")
        if pipe is None:
            raise ValueError("未接收到有效的模型对象输入")

        # 3. 架构自动识别
        is_sd3 = isinstance(pipe, (StableDiffusion3Pipeline, StableDiffusion3Img2ImgPipeline))
        # 自动获取 VAE 缩放系数
        scaling_factor = getattr(pipe.vae.config, "scaling_factor", 0.18215)
        
        # 4. 解析参数
        prompt = inputs.get("prompt", "")
        n_prompt = inputs.get("negative_prompt", "")
        latent_ndarray = inputs.get("latent_in")
        
        steps = int(float(params.get("steps", 20)))
        cfg = float(params.get("cfg", 7.0))
        denoise = float(params.get("denoise", 1.0))
        seed = int(params.get("seed", -1))
        preview_step = int(params.get("preview_step", 5))
        
        width = int(params.get("wid", 512) // 8 * 8)
        height = int(params.get("heig", 512) // 8 * 8)

        # 5. 随机数发生器
        if seed == -1:
            seed = np.random.randint(0, 2**16 - 1)
        generator = torch.Generator(pipe.device).manual_seed(seed)

        # 6. 设置调度器 (Scheduler)
        scheduler_name = params.get("scheduler", "Euler a")
        pipe.scheduler = self._get_scheduler(scheduler_name, pipe.scheduler.config, is_sd3)

        # 7. 定义实时预览回调
        def callback_on_step_end(pipe_obj, step, timestep, callback_kwargs):
            if step % preview_step == 0:
                self._send_preview(callback_kwargs.get("latents"), pipe_obj.vae)
            return callback_kwargs

        # 公共推理参数
        common_args = {
            "prompt": prompt,
            "negative_prompt": n_prompt,
            "num_inference_steps": steps,
            "guidance_scale": cfg,
            "generator": generator,
            "output_type": "latent",
            "callback_on_step_end": callback_on_step_end,
            "callback_on_step_end_tensor_inputs": ['latents']
        }

        # 8. 执行推理逻辑
        with torch.inference_mode():
            # 自动探测主网络精度（兼容 FP8/量化模型）
            target_dtype = pipe.transformer.dtype if is_sd3 else pipe.unet.dtype

            if latent_ndarray is not None:
                # 处理输入潜空间 Tensor
                init_latents = torch.from_numpy(latent_ndarray).to(pipe.device, dtype=target_dtype)
                
                if denoise < 1.0:
                    # 进入 Img2Img 流程（重绘模式）
                    # 动态创建 Pipeline 类，共享原有权重
                    if is_sd3:
                        img_pipe = StableDiffusion3Img2ImgPipeline(**pipe.components)
                    else:
                        img_pipe = StableDiffusionImg2ImgPipeline(**pipe.components)
                    
                    result_latent = img_pipe(
                        image=init_latents, 
                        strength=denoise,
                        **common_args
                    ).images
                else:
                    # denoise = 1.0，将输入 latent 作为初始噪声起点进行采样
                    result_latent = pipe(latents=init_latents, **common_args).images
            else:
                # 纯文生图流程
                result_latent = pipe(
                    width=width, 
                    height=height, 
                    **common_args
                ).images

            # 9. 后置处理：解码 Latents 为图像
            # 使用正确的缩放系数还原潜空间
            final_latents = 1 / scaling_factor * result_latent
            
            # VAE 解码 (确保精度匹配，VAE 通常运行在 fp16 或 fp32)
            decoded = pipe.vae.decode(final_latents.to(pipe.vae.dtype)).sample
            decoded = (decoded / 2 + 0.5).clamp(0, 1).cpu().permute(0, 2, 3, 1).float().numpy()
            
            # 转换为 PIL 图像对象
            final_image = Image.fromarray((decoded[0] * 255).astype(np.uint8))

        # 10. 返回结果
        return {
            "output_image": final_image,
            "latent_out": result_latent.cpu().numpy()
        }