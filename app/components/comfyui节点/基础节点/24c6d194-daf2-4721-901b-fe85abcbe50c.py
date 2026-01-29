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


class ComfyKSamplerWithPreview(BaseComponent):
    requirements = "torch,comfy,nodes,Pillow,numpy"
    name = "K采样器(预览版)"
    category = "comfyui节点/基础节点"
    description = "ComfyUI 采样器封装，支持实时发送 Latent 预览图"
    
    inputs = [
        PortDefinition(name="model", label="MODEL", type=ArgumentType.OBJECT),
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT), # 预览必须用到 VAE
        PortDefinition(name="positive", label="正向提示词", type=ArgumentType.OBJECT),
        PortDefinition(name="negative", label="负向提示词", type=ArgumentType.OBJECT),
        PortDefinition(name="latent", label="LATENT", type=ArgumentType.OBJECT),
    ]
    outputs = [
        PortDefinition(name="latent", label="LATENT", type=ArgumentType.OBJECT),
        PortDefinition(name="image", label="最终图像", type=ArgumentType.IMAGE),
    ]
    
    properties = {
        "steps": PropertyDefinition(
            type=PropertyType.INT,
            default=20,
            label="步数",
        ),
        "cfg": PropertyDefinition(
            type=PropertyType.RANGE,
            default="7.0",
            label="CFG",
            min=0.0,
            max=20.0,
            step=0.5,
        ),
        "sampler_name": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="euler",
            label="采样器",
            choices=["euler", "euler_ancestral", "heun", "dpmpp_2m", "dpmpp_2m_sde", "ddim"]
        ),
        "scheduler": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="normal",
            label="调度器",
            choices=["normal", "karras", "exponential", "simple", "sgm_uniform"]
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
            default=3,
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
            # 1. 转换成 numpy [0-255]
            arr = (tensor.cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
            # 2. 核心：如果维度大于3，不停地取第0个索引，直到只剩3维 (H, W, C)
            while arr.ndim > 3:
                if arr.shape[0] == 0: break # 防止空数组
                arr = arr[0]
            # 3. 如果第一维依然是1 (比如 1, 512, 3)，继续挤压
            if arr.ndim == 3 and arr.shape[0] == 1:
                arr = np.squeeze(arr, axis=0)
            return Image.fromarray(arr)

        # 1. 获取输入
        model = inputs.get("model")
        vae = inputs.get("vae")
        positive = inputs.get("positive")
        negative = inputs.get("negative")
        latent = inputs.get("latent")
        
        # 2. 获取参数
        steps = int(params.get("steps", 20))
        cfg = float(params.get("cfg", 7.0))
        sampler_name = params.get("sampler_name", "euler")
        scheduler = params.get("scheduler", "normal")
        denoise = float(params.get("denoise", 1.0))
        preview_step = int(params.get("preview_step", 3))
        seed = int(params.get("seed", -1))
        if seed == -1: seed = np.random.randint(2**16)
        with torch.no_grad():
            # 3. 显存管理
            mm.load_models_gpu([model])
    
            # 4. 实时预览回调
            def preview_callback(step, x0, x, total_steps):
                if step % preview_step == 0:
                    with torch.no_grad():
                        try:
                            decoded = vae.decode(x0)
                            # 使用暴力降维函数
                            pil_img = tensor_to_pil(decoded).resize((512, 512))
                            
                            buffered = io.BytesIO()
                            pil_img.save(buffered, format="JPEG", quality=60)
                            img_str = base64.b64encode(buffered.getvalue()).decode()
                            self.emit_message(
                                method="display_image",
                                params={"output": {"data": f"data:image/jpeg;base64,{img_str}"}}
                            )
                        except Exception as e:
                            print(f"预览转换失败: {e}")
    
            # 5. 调用采样 (Hook 模式)
            import comfy.sample
            sampler_node = nodes.KSampler()
            original_sample = comfy.sample.sample
            def hooked_sample(*args, **kwargs):
                kwargs['callback'] = preview_callback
                return original_sample(*args, **kwargs)
    
            comfy.sample.sample = hooked_sample
            try:
                # 这里的 latent["samples"] 确保是 (1, 4, 64, 64)
                result = sampler_node.sample(model, seed, steps, cfg, sampler_name, scheduler, positive, negative, latent, denoise)
            finally:
                comfy.sample.sample = original_sample
    
            # 6. 最终解码 (修复 decode_tiled 报错)
            final_latent = result[0]
            self.logger.info("正在执行最终 Tiled 解码...")
            # 移除 tile_terp，只传核心参数
            final_pixels = vae.decode_tiled(
                final_latent["samples"],
                tile_x=512,
                tile_y=512,
                overlap=64
            )
            # 使用同样的暴力降维处理最终图
            final_image = tensor_to_pil(final_pixels)
            try:
                self.logger.info("执行显存回收...")
                # 将所有模型从 GPU 挪到 CPU（内存）
                mm.unload_all_models()
                
                # 软清理缓存（ComfyUI 内部机制）
                mm.soft_empty_cache()
                
                # 强力清理 PyTorch 缓存（真正的显存释放）
                import torch
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect() # 清理进程间通信残留
                
            except Exception as e:
                self.logger.warning(f"显存回收时出现小问题: {e}")
        return {
            "latent": final_latent,
            "image": final_image
        }