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


class ComfyWanVideoSampler(BaseComponent):
    requirements = "torch,# comfy,# nodes,Pillow,numpy,opencv-python"
    name = "Wan视频采样器"
    category = "comfyui节点/视频生成"
    description = "专为 Wan 优化的视频采样器，支持首尾帧 Latent 注入和实时单帧预览"
    
    inputs = [
        PortDefinition(name="model", label="MODEL", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="positive", label="正向提示词", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="negative", label="负向提示词", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="latent", label="视频画布(空Latent)", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="latent", label="视频LATENT", type=ArgumentType.OBJECT),
        PortDefinition(name="first_frame_image", label="首帧预览图", type=ArgumentType.IMAGE),
    ]
    
    properties = {
        "steps": PropertyDefinition(
            type=PropertyType.INT,
            default=30,
            label="步数",
        ),
        "cfg": PropertyDefinition(
            type=PropertyType.RANGE,
            default="6.0",
            label="CFG",
            min=0.0,
            max=20.0,
            step=0.5,
        ),
        "sampler_name": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="uni_pc",
            label="采样器",
            choices=["uni_pc", "euler", "euler_ancestral", "dpmpp_2m"]
        ),
        "scheduler": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="simple",
            label="调度器",
            choices=["simple", "normal", "karras", "sgm_uniform"]
        ),
        "denoise": PropertyDefinition(
            type=PropertyType.RANGE,
            default="1.00",
            label="去噪强度",
            min=0.0,
            max=1.0,
            step=0.01,
        ),
        "seed": PropertyDefinition(
            type=PropertyType.INT,
            default=-1,
            label="种子",
        ),
        "preview_step": PropertyDefinition(
            type=PropertyType.INT,
            default=5,
            label="预览频率(步)",
        ),
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

        # 1. 获取输入与参数
        model = inputs.get("model")
        vae = inputs.get("vae")
        positive = inputs.get("positive")
        negative = inputs.get("negative")
        latent = inputs.get("latent")
        steps = int(params.get("steps", 30))
        cfg = float(params.get("cfg", 6.0))
        sampler_name = params.get("sampler_name", "uni_pc")
        scheduler = params.get("scheduler", "simple")
        denoise = float(params.get("denoise", 1.0))
        preview_step = int(params.get("preview_step", 5))
        seed = int(params.get("seed", -1))
        if seed == -1: seed = np.random.randint(2**31)

        with torch.no_grad():
            mm.load_models_gpu([model])
    
            # --- 4. 实时预览与进度回调 ---
            def preview_callback(step, x0, x, total_steps):
                # A. 更新进度条 (每一步都更新)
                current_progress = int((step / total_steps) * 100)
                self.emit_message(
                    method="display_progress",
                    params={
                        "progress": {
                            "data": {
                                "current_value": current_progress,
                                "min": 0,
                                "max": 100
                            }
                        }
                    }
                )

                # B. 发送预览图 (按频率更新)
                if step % preview_step == 0:
                    with torch.no_grad():
                        try:
                            # 仅取第一帧预览
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
                        except Exception as e:
                            pass

            # 5. 调用采样 (Hook 模式)
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
                    positive, negative, latent, denoise
                )
            finally:
                comfy.sample.sample = original_sample
    
            # 6. 最终处理
            final_latent = result[0]
            
            # 7. 采样结束，强制进度到 100%
            self.emit_message(
                method="display_progress",
                params={"progress": {"data": {"current_value": 100, "min": 0, "max": 100}}}
            )

            self.logger.info("执行最终 VAE 解码...")
            first_frame_pixels = vae.decode_tiled(final_latent["samples"][:, :, 0:1, :, :], tile_x=512, tile_y=512)
            final_image = tensor_to_pil(first_frame_pixels)

            # 显存回收
            try:
                mm.unload_all_models()
                mm.soft_empty_cache()
                torch.cuda.empty_cache()
            except:
                pass

        return {
            "latent": final_latent,
            "first_frame_image": final_image
        }
