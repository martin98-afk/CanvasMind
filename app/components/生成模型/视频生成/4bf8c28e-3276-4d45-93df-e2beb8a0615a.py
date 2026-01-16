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


class WanSamplerComponent(BaseComponent):
    name = "Wan 采样器 (含预览)"
    category = "生成模型/视频生成"
    description = "执行 Wan2.1/2.2 采样，支持实时中间过程图像预览"
    requirements = "diffusers,torch,transformers,accelerate,Pillow,numpy,tqdm"
    
    inputs = [
        PortDefinition(name="transformer", label="Transformer", type=ArgumentType.OBJECT),
        PortDefinition(name="scheduler", label="调度器", type=ArgumentType.OBJECT),
        PortDefinition(name="vae", label="VAE模型 (用于预览)", type=ArgumentType.OBJECT),
        PortDefinition(name="pos_embeds", label="正向提示词编码", type=ArgumentType.OBJECT),
        PortDefinition(name="neg_embeds", label="反向提示词编码", type=ArgumentType.OBJECT),
    ]
    
    outputs = [
        PortDefinition(name="latents", label="潜空间数据", type=ArgumentType.OBJECT),
        PortDefinition(name="last_preview", label="最终预览图", type=ArgumentType.IMAGE),
    ]

    properties = {
        "wid": PropertyDefinition(type=PropertyType.INT, default=832, label="宽"),
        "heig": PropertyDefinition(type=PropertyType.INT, default=480, label="高"),
        "num_frames": PropertyDefinition(type=PropertyType.INT, default=81, label="帧数"),
        "steps": PropertyDefinition(type=PropertyType.INT, default=30, label="步数"),
        "cfg": PropertyDefinition(type=PropertyType.FLOAT, default=5.0, label="CFG"),
        "seed": PropertyDefinition(type=PropertyType.INT, default=-1, label="种子"),
        "preview_step": PropertyDefinition(type=PropertyType.INT, default=5, label="预览频率(步)"),
    }

    def _send_preview(self, latents, vae):
        """Wan 专用的潜空间实时预览 (取中间帧解码)"""
        import torch
        import numpy as np
        from PIL import Image
        import io
        import base64

        try:
            with torch.no_grad():
                # 1. Wan Latent 是 5D: [B, C, F, H, W]
                # 预览时我们只取中间那一帧，减少 VAE 解码压力
                mid_frame_idx = latents.shape[2] // 2
                # 保持 5D 形状以便 VAE 处理: [1, 16, 1, H, W]
                preview_latent = latents[:, :, [mid_frame_idx], :, :]

                # 2. VAE 解码 (Wan VAE 内部已处理 scaling)
                # 注意：预览时关闭 tiling 以提高速度，如果显存极其紧张则开启
                image = vae.decode(preview_latent, return_dict=False)[0]
                
                # 3. 后处理成图像 [B, C, F, H, W] -> [H, W, C]
                image = (image / 2 + 0.5).clamp(0, 1)
                image = image[0, :, 0, :, :].cpu().permute(1, 2, 0).float().numpy()
                image = (image * 255).astype(np.uint8)
                
                pil_img = Image.fromarray(image)
                # 缩放预览图尺寸，节省传输带宽
                pil_img.thumbnail((320, 320))
                
                # 4. 编码为 Base64
                buffered = io.BytesIO()
                pil_img.save(buffered, format="JPEG", quality=70)
                img_str = base64.b64encode(buffered.getvalue()).decode()
                
                # 5. 推送流式消息
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
                return pil_img
        except Exception as e:
            # 预览失败不影响主流程
            return None

    def run(self, params, inputs=None):
        import torch
        import random
        from tqdm import tqdm

        # 初始化输入
        transformer = inputs["transformer"]
        scheduler = inputs["scheduler"]
        vae = inputs["vae"]
        pos = inputs["pos_embeds"]
        neg = inputs["neg_embeds"]
        device = transformer.device
        dtype = transformer.dtype

        # 1. 维度计算
        latent_h = params.wid // 8
        latent_w = params.heig // 8
        latent_f = (params.num_frames - 1) // 4 + 1
        
        # 2. 准备噪声
        seed = params.seed if params.seed != -1 else random.randint(0, 1000000)
        generator = torch.Generator(device=device).manual_seed(seed)
        latents = torch.randn((1, 16, latent_f, latent_h, latent_w), 
                              generator=generator, device=device, dtype=dtype)

        # 3. 配置调度器 (确保 shift 设置正确)
        scheduler.set_timesteps(params.steps, device=device)
        timesteps = scheduler.timesteps
        encoder_hidden_states = torch.cat([neg, pos], dim=0)

        # 4. 采样循环
        self.logger.info(f"开始采样生成，Seed: {seed}")
        last_pil = None
        
        with torch.no_grad():
            for i, t in enumerate(tqdm(timesteps)):
                # 准备 CFG 输入
                latent_model_input = torch.cat([latents] * 2)
                
                # 模型推理 (Transformer)
                noise_pred = transformer(
                    hidden_states=latent_model_input,
                    timestep=t.expand(latent_model_input.shape[0]),
                    encoder_hidden_states=encoder_hidden_states,
                    return_dict=False,
                )[0]

                # 应用 CFG
                noise_pred_uncond, noise_pred_text = noise_pred.chunk(2)
                noise_pred = noise_pred_uncond + params.cfg * (noise_pred_text - noise_pred_uncond)

                # 调度器步进
                latents = scheduler.step(noise_pred, t, latents, return_dict=False)[0]

                # 实时预览逻辑
                if (i + 1) % params.preview_step == 0 or i == len(timesteps) - 1:
                    last_pil = self._send_preview(latents, vae)

        return {
            "latents": latents,
            "last_preview": last_pil
        }