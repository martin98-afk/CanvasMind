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


class KSampler(BaseComponent):
    name = "K采样器终极版"
    category = "生成模型/图像生成"
    description = "对标 ComfyUI 核心逻辑，支持实时预览、多重控制和流式输出"
    requirements = "diffusers,torch,numpy,Pillow"

    inputs = [
        PortDefinition(name="model", label="模型(UNet/Transformer)", type=ArgumentType.OBJECT),
        PortDefinition(name="positive", label="正向条件", type=ArgumentType.OBJECT),
        PortDefinition(name="negative", label="负向条件", type=ArgumentType.OBJECT),
        PortDefinition(name="latent_image", label="Latent输入", type=ArgumentType.OBJECT),
        PortDefinition(name="vae", label="VAE(用于预览)", type=ArgumentType.OBJECT),
    ]

    outputs = [
        PortDefinition(name="latent", label="潜空间数据", type=ArgumentType.OBJECT),
        PortDefinition(name="image", label="最终图像", type=ArgumentType.IMAGE),
    ]

    properties = {
        "seed": PropertyDefinition(
            type=PropertyType.INT,
            default=-1,
            label="随机种子",
        ),
        "steps": PropertyDefinition(
            type=PropertyType.INT,
            default=20,
            label="步数",
        ),
        "cfg": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=7.0,
            label="CFG系数",
        ),
        "sampler_name": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="dpmpp_2m_karras",
            label="采样算法",
            choices=["euler", "euler_ancestral", "heun", "dpmpp_2m_karras", "dpmpp_2m_sde_karras", "ddim", "uni_pc"]
        ),
        "denoise": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=1.0,
            label="降噪幅度",
        ),
        "shift": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=1.0,
            label="时间步移位(Shift)",
        ),
        "preview_step": PropertyDefinition(
            type=PropertyType.INT,
            default=5,
            label="预览频率(步)",
        ),
    }

    def _send_preview(self, latents, vae):
        """发送实时预览，增加精度强制对齐"""
        import io
        import base64
        import torch
        import numpy as np
        from PIL import Image
        if vae is None:
            return
        try:
            with torch.no_grad():
                # --- 关键修复：强制将 latents 转换为 vae 的数据类型 (通常是 float32) ---
                latents = latents.to(dtype=vae.dtype, device=vae.device)
                
                latents = 1 / 0.18215 * latents
                image = vae.decode(latents).sample
                image = (image / 2 + 0.5).clamp(0, 1)
                image = image.cpu().permute(0, 2, 3, 1).float().numpy()
                image = (image[0] * 255).astype(np.uint8)
                
                pil_img = Image.fromarray(image)
                pil_img.thumbnail((256, 256)) # 预览图小一点，传输更快
                
                buffered = io.BytesIO()
                pil_img.save(buffered, format="JPEG", quality=70)
                img_str = base64.b64encode(buffered.getvalue()).decode()
                
                self.emit_message(
                    method="display_image",
                    params={
                        "output": f"data:image/jpeg;base64,{img_str}"
                    }
                )
        except Exception as e:
            self.logger.warning(f"预览生成失败: {e}")

    def run(self, params, inputs=None):
        import torch
        import numpy as np
        from diffusers import DPMSolverMultistepScheduler, EulerDiscreteScheduler, EulerAncestralDiscreteScheduler, DDIMScheduler

        # 1. 核心修复：解包 Latent 字典
        latent_in = inputs.get("latent_image")
        if isinstance(latent_in, dict):
            latents_orig = latent_in["samples"]
            noise_mask = latent_in.get("noise_mask")
        else:
            latents_orig = latent_in
            noise_mask = None

        unet = inputs.get("model")
        pos_cond = inputs.get("positive")
        neg_cond = inputs.get("negative")
        vae = inputs.get("vae")
        
        device, dtype = unet.device, unet.dtype

        # 2. 调度器与种子
        seed = params.get("seed")
        if seed == -1: seed = np.random.randint(2**16)
        generator = torch.Generator(device).manual_seed(seed)
        
        s_name = params.get("sampler_name")
        if s_name == "euler": scheduler = EulerDiscreteScheduler()
        elif s_name == "euler_ancestral": scheduler = EulerAncestralDiscreteScheduler()
        elif s_name == "ddim": scheduler = DDIMScheduler()
        else: scheduler = DPMSolverMultistepScheduler(use_karras_sigmas=True)

        # 3. 降噪与初始噪声
        steps = params.get("steps")
        denoise = params.get("denoise")
        scheduler.set_timesteps(steps, device=device)
        
        t_start = int(len(scheduler.timesteps) * (1.0 - denoise))
        timesteps = scheduler.timesteps[t_start:]
        
        initial_noise = torch.randn(latents_orig.shape, generator=generator, device=device, dtype=dtype)
        
        # 修正：如果降噪 < 1.0，根据时间步给原图加噪
        if denoise < 1.0:
            current_latents = scheduler.add_noise(latents_orig.to(device, dtype=dtype), initial_noise, timesteps[0:1])
        else:
            current_latents = initial_noise

        # 4. 条件解包
        p_emb = pos_cond[0][0] if isinstance(pos_cond, list) else pos_cond
        n_emb = neg_cond[0][0] if isinstance(neg_cond, list) else neg_cond

        # 5. 去噪循环
        with torch.no_grad():
            for i, t in enumerate(timesteps):
                if vae and i % params.get("preview_step") == 0:
                    self._send_preview(current_latents, vae)

                # 预测
                latent_model_input = torch.cat([current_latents] * 2)
                latent_model_input = scheduler.scale_model_input(latent_model_input, t)
                
                noise_pred = unet(latent_model_input, t, encoder_hidden_states=torch.cat([n_emb, p_emb])).sample
                
                # CFG
                noise_pred_uncond, noise_pred_text = noise_pred.chunk(2)
                noise_pred = noise_pred_uncond + params.get("cfg") * (noise_pred_text - noise_pred_uncond)
                
                # 步进
                current_latents = scheduler.step(noise_pred, t, current_latents).prev_sample

                # --- 噪波遮罩逻辑 ---
                if noise_mask is not None and i < len(timesteps) - 1:
                    m = noise_mask.to(device=device, dtype=dtype)
                    # 将非重绘区域还原为原图在该步应有的噪声状态
                    orig_at_t = scheduler.add_noise(latents_orig.to(device, dtype=dtype), initial_noise, timesteps[i+1:i+2])
                    current_latents = (current_latents * m) + (orig_at_t * (1.0 - m))

        # 6. 最终输出
        from PIL import Image
        final_img = None
        if vae:
            l_out = current_latents.to(dtype=vae.dtype, device=vae.device)
            decoded = vae.decode(l_out / 0.18215).sample
            decoded = (decoded / 2 + 0.5).clamp(0, 1).cpu().permute(0, 2, 3, 1).float().numpy()
            final_img = Image.fromarray((decoded[0] * 255).astype(np.uint8))

        return {"latent": current_latents, "image": final_img}