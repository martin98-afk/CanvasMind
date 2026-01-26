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


class LTXVSampler(BaseComponent):
    requirements = "Pillow,torch,numpy,# comfy,# nodes"
    name = "LTX2核心采样器"
    category = "comfyui节点/LTX模型适配"
    description = "LTX2 专用采样器，支持进度回调、首帧预览以及 AV 潜空间处理。"
    
    inputs = [
        PortDefinition(name="model", label="MODEL", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="positive", label="正向条件", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="negative", label="负向条件", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="latent", label="LATENT", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="latent", label="结果LATENT", type=ArgumentType.OBJECT),
        PortDefinition(name="preview", label="首帧预览", type=ArgumentType.IMAGE),
    ]
    properties = {
        "steps": PropertyDefinition(
            type=PropertyType.INT,
            default=30,
            label="步数",
        ),
        "cfg": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=1.0,
            label="CFG",
        ),
        "sampler": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="euler",
            label="采样器",
            choices=["euler", "heun", "dpmpp_2m"]
        ),
        "scheduler": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="normal",
            label="调度器",
            choices=["normal", "simple", "sgm_uniform"]
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
    }

    def run(self, params, inputs):
        import numpy as np
        import comfy.model_management as mm
        import comfy.utils
        import comfy.model_sampling
        import comfy.sample
        import comfy.nested_tensor
        import nodes
        model = inputs.get("model")
        vae = inputs.get("vae")
        pos = inputs.get("positive")
        neg = inputs.get("negative")
        latent = inputs.get("latent")
        
        seed = int(params.get("seed"))
        if seed == -1: seed = np.random.randint(0, 0xffffffffffffffff)

        # 进度回调
        def cb(step, x0, x, total):
            progress = int((step/total)*100)
            self.emit_message(method="display_progress", params={"progress": {"data": {"current_value": progress, "min": 0, "max": 100}}})
            if step % 5 == 0:
                # 实时解码第一帧预览
                self._send_preview(vae, x0)

        mm.load_models_gpu([model])
        
        # 采样 Hook
        orig_sample = comfy.sample.sample
        def hooked_sample(*args, **kwargs):
            kwargs['callback'] = cb
            return orig_sample(*args, **kwargs)
        
        comfy.sample.sample = hooked_sample
        try:
            ks = nodes.KSampler()
            result = ks.sample(model, seed, params.get("steps"), params.get("cfg"), 
                               params.get("sampler"), params.get("scheduler"), 
                               pos, neg, latent, denoise=params.get("denoise"))
        finally:
            comfy.sample.sample = orig_sample

        final_latent = result[0]
        
        # 如果是 AV 合并的 Latent，需要拆分回视频 Latent 返回
        samples_data = final_latent["samples"]
        if isinstance(samples_data, comfy.nested_tensor.NestedTensor):
            v_lat = samples_data.unbind()[0]
            final_latent = {"samples": v_lat}

        # 最终解码预览图
        final_img = self._decode_frame(vae, final_latent["samples"][:, :, 0:1, :, :])
        return {"latent": final_latent, "preview": final_img}

    def _decode_frame(self, vae, latent_pixel):
        import torch
        import numpy as np
        from PIL import Image
        with torch.no_grad():
            pixels = vae.decode_tiled(latent_pixel, tile_x=512, tile_y=512)
            arr = (pixels.cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
            return Image.fromarray(arr[0])

    def _send_preview(self, vae, x0):
        import base64
        from io import BytesIO
        try:
            # 如果是嵌套张量，取视频部分
            s = x0.unbind()[0] if hasattr(x0, "unbind") else x0
            pil_img = self._decode_frame(vae, s[:, :, 0:1, :, :]).resize((512, 512))
            buf = BytesIO()
            pil_img.save(buf, format="JPEG", quality=70)
            base64_str = base64.b64encode(buf.getvalue()).decode()
            self.emit_message(method="display_image", params={"output": {"data": f"data:image/jpeg;base64,{base64_str}"}})
        except: pass