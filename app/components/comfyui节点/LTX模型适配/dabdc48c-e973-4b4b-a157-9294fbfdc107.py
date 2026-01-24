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


class ComfyLTXVideoSampler(BaseComponent):
    requirements = "torch,comfy,nodes,Pillow,numpy,opencv-python"
    name = "LTX2视频采样器(音频驱动版)"
    category = "comfyui节点/LTX模型适配"
    description = "专为 LTX2 优化的采样器，支持首帧图像注入、音频潜空间条件注入、实时进度和单帧预览"
    
    inputs = [
        PortDefinition(name="model", label="MODEL", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="positive", label="正向提示词", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="negative", label="负向提示词", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="latent", label="128通道画布", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        # 唱歌/数字人专用输入
        PortDefinition(name="start_frame_latent", label="人物首帧Latent", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="audio_latent", label="音频Latent", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="latent", label="视频LATENT", type=ArgumentType.OBJECT),
        PortDefinition(name="preview_image", label="首帧预览图", type=ArgumentType.IMAGE),
    ]
    
    properties = {
        "steps": PropertyDefinition(type=PropertyType.INT, default=30, label="步数"),
        "cfg": PropertyDefinition(type=PropertyType.RANGE, default="1.0", label="CFG", min=0.0, max=10.0, step=0.1),
        "sampler_name": PropertyDefinition(
            type=PropertyType.CHOICE, default="euler", label="采样器",
            choices=["euler", "uni_pc", "heun", "dpmpp_2m"]
        ),
        "scheduler": PropertyDefinition(
            type=PropertyType.CHOICE, default="normal", label="调度器",
            choices=["normal", "sgm_uniform", "simple", "karras"]
        ),
        "denoise": PropertyDefinition(type=PropertyType.RANGE, default="1.00", label="去噪强度", min=0.0, max=1.0, step=0.01),
        "seed": PropertyDefinition(type=PropertyType.INT, default=-1, label="种子"),
        "preview_step": PropertyDefinition(type=PropertyType.INT, default=5, label="预览频率(步)"),
    }

    def ensure_comfy_exist(self):
        import os, sys
        path = self.global_variable.comfy_extension
        if path not in sys.path:
            sys.path.append(path)
        os.chdir(path)
    
    def run(self, params, inputs):
        self.ensure_comfy_exist()
        import torch
        import numpy as np
        import io, base64
        from PIL import Image
        import comfy.model_management as mm
        import nodes

        # --- 暴力降维工具函数 ---
        def tensor_to_pil(tensor):
            arr = (tensor.cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
            while arr.ndim > 3:
                if arr.shape[0] == 0: break
                arr = arr[0]
            if arr.ndim == 3 and arr.shape[0] == 1:
                arr = np.squeeze(arr, axis=0)
            return Image.fromarray(arr)

        # 1. 获取基础输入
        model = inputs.get("model")
        vae = inputs.get("vae")
        positive = inputs.get("positive")
        negative = inputs.get("negative")
        latent = inputs.get("latent")
        
        # 深度拷贝画布 [B, 128, F, H, W]
        video_samples = latent["samples"].clone()
        
        # 获取首帧和音频
        start_frame_latent = inputs.get("start_frame_latent")
        audio_latent = inputs.get("audio_latent")

        # 2. 【核心逻辑】注入首帧图像
        if start_frame_latent is not None:
            self.logger.info("正在注入人物首帧特征...")
            s_samples = start_frame_latent["samples"]
            # 确保首帧是 5 维 [B, 128, 1, H, W]
            if s_samples.ndim == 4:
                s_samples = s_samples.unsqueeze(2)
            # 覆盖视频画布的第一帧
            video_samples[:, :, 0:1, :, :] = s_samples[:, :, 0:1, :, :]

        # 3. 【核心逻辑】注入音频条件 (Talking Head 模式)
        if audio_latent is not None:
            self.logger.info("正在注入音频潜空间条件...")
            # LTX2 的音频通常是作为 conditioning 的一部分传给 Cross-Attention
            # 这里的 positive 格式通常是 [[tensor, {"pooled_output": ..., "audio_latent": ...}]]
            new_positive = []
            for p in positive:
                cond_tensor = p[0]
                cond_dict = p[1].copy()
                cond_dict["audio_latent"] = audio_latent # 注入音频
                new_positive.append([cond_tensor, cond_dict])
            positive = new_positive

        # 4. 参数解析
        steps = int(params.get("steps", 30))
        cfg = float(params.get("cfg", 1.0))
        sampler_name = params.get("sampler_name", "euler")
        scheduler = params.get("scheduler", "normal")
        denoise = float(params.get("denoise", 1.0))
        preview_step = int(params.get("preview_step", 5))
        seed = int(params.get("seed", -1))
        if seed == -1: seed = np.random.randint(2**31)

        with torch.no_grad():
            self.logger.info("调度 LTX2 模型至 GPU...")
            mm.load_models_gpu([model])
    
            # --- 5. 实时预览与进度回调 ---
            def preview_callback(step, x0, x, total_steps):
                # 更新进度条
                current_progress = int((step / total_steps) * 100)
                self.emit_message(
                    method="display_progress",
                    params={"progress": {"data": {"current_value": current_progress, "min": 0, "max": 100}}}
                )

                # 发送预览图 (仅预览第一帧)
                if step % preview_step == 0:
                    with torch.no_grad():
                        try:
                            # x0 形状为 [B, 128, F, H, W]
                            preview_frame = x0[:, :, 0:1, :, :] 
                            decoded = vae.decode(preview_frame)
                            pil_img = tensor_to_pil(decoded).resize((512, 512))
                            
                            buffered = io.BytesIO()
                            pil_img.save(buffered, format="JPEG", quality=60)
                            img_str = base64.b64encode(buffered.getvalue()).decode()
                            self.emit_message(
                                method="display_image",
                                params={"output": {"data": f"data:image/jpeg;base64,{img_str}"}}
                            )
                        except Exception:
                            pass

            # 6. 调用采样 (Hook 模式)
            import comfy.sample
            sampler_node = nodes.KSampler()
            original_sample = comfy.sample.sample
            def hooked_sample(*args, **kwargs):
                kwargs['callback'] = preview_callback
                return original_sample(*args, **kwargs)
    
            comfy.sample.sample = hooked_sample
            try:
                result = sampler_node.sample(
                    model, seed, steps, cfg, sampler_name, scheduler, 
                    positive, negative, {"samples": video_samples}, denoise
                )
            finally:
                comfy.sample.sample = original_sample
    
            # 7. 最终处理
            final_latent = result[0]
            self.emit_message(
                method="display_progress",
                params={"progress": {"data": {"current_value": 100, "min": 0, "max": 100}}}
            )

            self.logger.info("执行最终 LTX2 VAE 解码(预览帧)...")
            # 最终预览图也建议用 tiled，防止 128 通道 OOM
            first_frame_pixels = vae.decode_tiled(final_latent["samples"][:, :, 0:1, :, :], tile_x=512, tile_y=512)
            final_image = tensor_to_pil(first_frame_pixels)

            # 8. 显存回收 (LTX2 非常大，必须强制回收)
            try:
                mm.unload_all_models()
                mm.soft_empty_cache()
                torch.cuda.empty_cache()
            except:
                pass

        return {
            "latent": final_latent,
            "preview_image": final_image
        }