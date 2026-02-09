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


class ComfyUniversalVideoEncode(BaseComponent):
    name = "通用视频图像编码器"
    category = "comfyui节点/基础节点"
    description = "通用编码器：自动适配 Wan(8/16x), LTX(32x), SD(8x) 等所有模型的尺寸和维度"
    requirements = "torch,numpy,Pillow"
    
    inputs = [
        PortDefinition(name="image", label="IMAGE", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT, sub_type="VAE", connection=ConnectionType.SINGLE),
        PortDefinition(name="reference_latent", label="参考画布", type=ArgumentType.OBJECT, sub_type="LATENT", connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="latent", label="LATENT", type=ArgumentType.OBJECT, sub_type="LATENT"),
    ]

    properties = {
        "compression_ratio": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="Auto",
            label="空间压缩倍率 (SD/Wan2.1=8, Wan2.2=16, LTX=32)",
            choices=["Auto", "8", "16", "32"]
        ),
        "keep_proportion": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="保持原图比例(多余部分裁剪)",
        ),
    }

    def run(self, params, inputs):
        import torch
        import torch.nn.functional as F
        import numpy as np
        from PIL import Image, ImageOps
        
        vae = inputs.get("vae")
        pil_img = inputs.get("image")
        ref_latent = inputs.get("reference_latent")
        
        if any(x is None for x in [vae, pil_img, ref_latent]):
            raise ValueError("通用编码器：请确保连接了 VAE、图片和参考画布")

        # 1. 自动探测目标参数
        t_samples = ref_latent["samples"]
        t_batch, t_channels, t_frames, t_h_lat, t_w_lat = t_samples.shape

        # 2. 确定压缩倍率
        ratio_mode = params.get("compression_ratio", "Auto")
        if ratio_mode == "Auto":
            # 根据通道数智能推断 (Wan2.1/SD=8, Wan2.2=16, LTX=32)
            if t_channels == 128: ratio = 32
            elif t_channels == 48: ratio = 16
            else: ratio = 8
        else:
            ratio = int(ratio_mode)

        # 3. 计算目标像素尺寸
        target_w = t_w_lat * ratio
        target_h = t_h_lat * ratio
        self.logger.info(f"通用编码器：检测到倍率 {ratio}x, 目标尺寸 {target_w}x{target_h}, 通道 {t_channels}")

        # 4. 图像预处理 (缩放与裁剪)
        if params.get("keep_proportion"):
            # 自动居中裁剪缩放
            pil_img = ImageOps.fit(pil_img, (target_w, target_h), Image.LANCZOS)
        else:
            # 强制拉伸
            pil_img = pil_img.resize((target_w, target_h), Image.LANCZOS)

        # 5. 转为 Tensor [1, H, W, C]
        img_np = np.array(pil_img).astype(np.float32) / 255.0
        pixel_tensor = torch.from_numpy(img_np).unsqueeze(0)

        # 6. 执行编码
        with torch.no_grad():
            res_latent = vae.encode(pixel_tensor)
            
            # 7. 维度标准化 (强制转为 5D: B, C, F, H, W)
            if res_latent.ndim == 4:
                res_latent = res_latent.unsqueeze(2)
            
            # 8. 通道数对齐 (针对 48通道 I2V 模型)
            curr_c = res_latent.shape[1]
            if curr_c != t_channels:
                self.logger.info(f"通道不一致 (VAE:{curr_c} vs 画布:{t_channels})，正在自动对齐...")
                if curr_c > t_channels:
                    # 截取 (例如从 48 截取 16)
                    res_latent = res_latent[:, :t_channels, :, :, :]
                else:
                    # 补齐 (例如从 16 补齐到 48，填充 0)
                    pad = torch.zeros([t_batch, t_channels - curr_c, 1, t_h_lat, t_w_lat], device=res_latent.device)
                    res_latent = torch.cat([res_latent, pad], dim=1)

            # 9. 空间尺寸二次检查 (防止因奇数像素导致的 1 像素偏差)
            if res_latent.shape[3] != t_h_lat or res_latent.shape[4] != t_w_lat:
                self.logger.warning("潜空间尺寸存在微小偏差，强制插值对齐...")
                b, c, f, h, w = res_latent.shape
                res_latent = res_latent.view(b*f, c, h, w)
                res_latent = F.interpolate(res_latent, size=(t_h_lat, t_w_lat), mode='nearest')
                res_latent = res_latent.view(b, c, f, t_h_lat, t_w_lat)

        return {"latent": {"samples": res_latent}}