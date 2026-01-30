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


class ComfyWanVideoSamplerAdvanced(BaseComponent):
    requirements = "torch,Pillow,numpy,opencv-python,nodes,comfy"
    name = "K采样器(高级)"
    category = "comfyui节点/基础节点"
    description = "高级K采样器，支持精确步数控制(Start/End Step)和噪声注入控制，适用于图生视频或多重采样工作流。"
    
    inputs = [
        PortDefinition(name="model", label="MODEL", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="positive", label="正向提示词", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="negative", label="负向提示词", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="latent", label="视频画布(Latent)", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="latent", label="视频LATENT", type=ArgumentType.OBJECT),
        PortDefinition(name="first_frame_image", label="首帧预览图", type=ArgumentType.IMAGE),
    ]
    
    properties = {
        "add_noise": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="enable",
            label="注入噪声",
            choices=["enable", "disable"],
            description="disable用于重绘或二次采样时不破坏原有画面结构"
        ),
        "seed": PropertyDefinition(
            type=PropertyType.INT,
            default=-1,
            label="噪声种子",
            description="-1 为随机种子"
        ),
        "steps": PropertyDefinition(
            type=PropertyType.INT,
            default=30,
            label="总步数",
            min=1,
            max=10000
        ),
        "cfg": PropertyDefinition(
            type=PropertyType.RANGE,
            default="6.0",
            label="CFG",
            min=0.0,
            max=100.0,
            step=0.1,
        ),
        "sampler_name": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="uni_pc",
            label="采样器",
            choices=["uni_pc", "euler", "euler_ancestral", "dpmpp_2m", "dpmpp_sde", "lms"]
        ),
        "scheduler": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="simple",
            label="调度器",
            choices=["simple", "normal", "karras", "sgm_uniform", "ddim_uniform"]
        ),
        "start_at_step": PropertyDefinition(
            type=PropertyType.INT,
            default=0,
            label="开始步数",
            min=0,
            max=10000,
            description="从第几步开始采样（用于跳过初始加噪阶段）"
        ),
        "end_at_step": PropertyDefinition(
            type=PropertyType.INT,
            default=10000,
            label="结束步数",
            min=0,
            max=10000,
            description="在第几步停止（通常大于等于总步数表示跑完）"
        ),
        "return_with_leftover_noise": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="disable",
            label="保留剩余噪声",
            choices=["disable", "enable"],
            description="enable表示不进行最后一步去噪，用于将输出传递给下一个采样器"
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

        # --- 暴力降维工具函数 (保持原有逻辑) ---
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
        
        # 高级采样参数
        add_noise = params.get("add_noise", "enable")
        seed = int(params.get("seed", -1))
        steps = int(params.get("steps", 30))
        cfg = float(params.get("cfg", 8.0))
        sampler_name = params.get("sampler_name", "uni_pc")
        scheduler = params.get("scheduler", "simple")
        start_at_step = int(params.get("start_at_step", 0))
        end_at_step = int(params.get("end_at_step", 10000))
        return_with_leftover_noise = params.get("return_with_leftover_noise", "disable")
        preview_step = int(params.get("preview_step", 5))

        if seed == -1: seed = np.random.randint(2**16)

        with torch.no_grad():
            mm.load_models_gpu([model])
    
            # --- 4. 实时预览与进度回调 ---
            def preview_callback(step, x0, x, total_steps):
                # Advanced Sampler 的 step 通常是绝对步数，这里做归一化处理以便显示进度
                # total_steps 在这里可能不准，通常用 steps 参数作为分母
                actual_step = step + 1
                current_progress = int((actual_step / steps) * 100)
                if current_progress > 100: current_progress = 100

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
                if actual_step % preview_step == 0:
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

            # 5. 调用 KSamplerAdvanced (Hook 模式)
            import comfy.sample
            # 实例化 Advanced 节点
            sampler_node = nodes.KSamplerAdvanced()
            
            original_sample = comfy.sample.sample
            def hooked_sample(*args, **kwargs):
                kwargs['callback'] = preview_callback
                return original_sample(*args, **kwargs)
    
            comfy.sample.sample = hooked_sample
            try:
                # 注意：KSamplerAdvanced.sample 的参数顺序必须与源码 INPUT_TYPES 对应或使用关键字参数
                # def sample(self, model, add_noise, noise_seed, steps, cfg, sampler_name, scheduler, positive, negative, latent_image, start_at_step, end_at_step, return_with_leftover_noise, denoise=1.0):
                result = sampler_node.sample(
                    model=model,
                    add_noise=add_noise,
                    noise_seed=seed,
                    steps=steps,
                    cfg=cfg,
                    sampler_name=sampler_name,
                    scheduler=scheduler,
                    positive=positive,
                    negative=negative,
                    latent_image=latent,
                    start_at_step=start_at_step,
                    end_at_step=end_at_step,
                    return_with_leftover_noise=return_with_leftover_noise,
                    denoise=1.0 # Advanced Sampler 内部通常忽略此参数或默认为1，由 start/end step 控制
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
            # 解码第一帧作为结果预览
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