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


class LTXVAddGuide(BaseComponent):
    requirements = "# node_helpers,# get_noise_mask,# comfy,torch"
    name = "LTX2多帧引导注入"
    category = "comfyui节点/LTX模型适配"
    description = "在视频的指定位置插入参考帧（Keyframes），支持多图引导。"

    inputs = [
        PortDefinition(name="positive", label="正向条件", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="negative", label="负向条件", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="latent", label="画布LATENT", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="image", label="引导图像/视频", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="positive", label="正向条件", type=ArgumentType.OBJECT),
        PortDefinition(name="negative", label="负向条件", type=ArgumentType.OBJECT),
        PortDefinition(name="latent", label="LATENT", type=ArgumentType.OBJECT),
    ]
    properties = {
        "frame_idx": PropertyDefinition(
            type=PropertyType.INT,
            default=0,
            label="插入起始帧索引",
        ),
        "strength": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=1.0,
            label="引导强度",
        ),
    }

    def run(self, params, inputs):
        import node_helpers
        import comfy.utils
        import torch
        from get_noise_mask import get_noise_mask
        from comfy.ldm.lightricks.symmetric_patchifier import SymmetricPatchifier, latent_to_pixel_coords
        self.PATCHIFIER = SymmetricPatchifier(1, start_end=True)
        pos = inputs.get("positive")
        neg = inputs.get("negative")
        vae = inputs.get("vae")
        latent = inputs.get("latent")
        image = inputs.get("image")
        
        frame_idx = int(params.get("frame_idx", 0))
        strength = float(params.get("strength", 1.0))
        
        scale_factors = vae.downscale_index_formula # (8, 32, 32)
        latent_image = latent["samples"]
        noise_mask = get_noise_mask(latent) # 使用之前定义的工具函数

        # 1. 编码引导图
        _, _, _, latent_height, latent_width = latent_image.shape
        # 缩放图像并编码
        pixels = comfy.utils.common_upscale(image.movedim(-1, 1), latent_width * 32, latent_height * 32, "bilinear", crop="disabled").movedim(1, -1)
        t = vae.encode(pixels[:, :, :, :3])

        # 2. 计算坐标偏移 (LTX2 源码核心逻辑)
        # 这里的 patchify 和 keyframe_idxs 写入是 LTX2 维持精确控制的关键
        _, latent_coords = self.PATCHIFIER.patchify(t)
        pixel_coords = latent_to_pixel_coords(latent_coords, scale_factors, causal_fix=(frame_idx == 0))
        pixel_coords[:, 0] += frame_idx

        # 3. 写入 Conditioning
        def update_cond(cond, coords):
            # 寻找现有的 keyframe_idxs 或初始化
            existing_coords = None
            for item in cond:
                if "keyframe_idxs" in item[1]:
                    existing_coords = item[1]["keyframe_idxs"]
            
            new_coords = coords if existing_coords is None else torch.cat([existing_coords, coords], dim=2)
            return node_helpers.conditioning_set_values(cond, {"keyframe_idxs": new_coords})

        pos = update_cond(pos, pixel_coords)
        neg = update_cond(neg, pixel_coords)

        # 4. 合并 Latent 和 Mask
        mask = torch.full((noise_mask.shape[0], 1, t.shape[2], noise_mask.shape[3], noise_mask.shape[4]),
                         1.0 - strength, dtype=noise_mask.dtype, device=noise_mask.device)
        
        # 将引导帧拼接在 Latent 序列的最后（LTX2 的特殊处理方式，采样器会自动识别 keyframe_idxs 指向这里）
        latent_image = torch.cat([latent_image, t], dim=2)
        noise_mask = torch.cat([noise_mask, mask], dim=2)

        return {"positive": pos, "negative": neg, "latent": {"samples": latent_image, "noise_mask": noise_mask}}