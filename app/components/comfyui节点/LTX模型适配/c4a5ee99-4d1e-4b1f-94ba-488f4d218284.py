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


class LTXVLatentUpsampler(BaseComponent):
    requirements = "torch,comfy"
    name = "LTX2潜空间放大器"
    category = "comfyui节点/LTX模型适配"
    description = "将 LTX2 视频潜空间放大 2 倍。注意：仅适用于 128 通道的 LTX2 专用放大模型。"
    
    inputs = [
        PortDefinition(name="latent", label="LATENT", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="upscale_model", label="放大模型", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="latent", label="放大后LATENT", type=ArgumentType.OBJECT),
    ]

    def run(self, params, inputs):
        import torch
        import math
        import comfy.model_management as mm
        samples = inputs.get("latent")
        upscale_model = inputs.get("upscale_model")
        vae = inputs.get("vae")

        if samples is None or upscale_model is None or vae is None:
            raise ValueError("LTX2 LatentUpsampler 需要连接 Latent、放大模型和 VAE")

        device = mm.get_torch_device()
        offload_device = mm.vae_offload_device()
        
        # 1. 显存管理与准备
        latents = samples["samples"]
        input_dtype = latents.dtype
        # 获取模型权重的数据类型 (通常是 bfloat16 或 float16)
        model_dtype = next(upscale_model.parameters()).dtype

        # 估算所需显存 (LTX2 128通道张量非常大，放大4倍显存压力巨大)
        memory_required = mm.module_size(upscale_model)
        memory_required += math.prod(latents.shape) * 3000.0 
        mm.free_memory(memory_required, device)

        try:
            # 2. 模型搬运至计算设备
            upscale_model.to(device)
            # 转换 Latent 数据类型和设备
            latents = latents.to(dtype=model_dtype, device=device)

            # 3. 【关键逻辑】反归一化
            # LTX2 的潜空间在放大前必须回到原始分布
            self.logger.info("正在执行 LTX2 潜空间反归一化...")
            stats = vae.first_stage_model.per_channel_statistics
            latents = stats.un_normalize(latents)

            # 4. 执行放大推理 (Factor 2)
            self.logger.info("正在执行 Latent 2x 放大推理...")
            with torch.no_grad():
                upsampled_latents = upscale_model(latents)

            # 5. 【关键逻辑】再归一化
            # 放大后的结果需要重新映射回模型可理解的分布
            self.logger.info("正在执行放大后归一化...")
            upsampled_latents = stats.normalize(upsampled_latents)

        finally:
            # 卸载模型释放显存
            upscale_model.to(offload_device)

        # 6. 数据转换回中间设备格式
        upsampled_latents = upsampled_latents.to(dtype=input_dtype, device=mm.intermediate_device())
        
        # 组装返回字典，移除旧的 noise_mask (因为分辨率变了，旧掩码失效)
        return_dict = samples.copy()
        return_dict["samples"] = upsampled_latents
        return_dict.pop("noise_mask", None) 
        
        self.logger.info(f"LTX2 潜空间放大完成: {list(upsampled_latents.shape)}")
        
        return {"latent": return_dict}