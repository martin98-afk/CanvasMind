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


class ComfyVAEDecode(BaseComponent):
    requirements = "torch,numpy,Pillow,comfy"
    name = "VAE解码器"
    category = "comfyui节点"
    description = "将潜空间数据解码为可视化图像"
    
    inputs = [
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="latent", label="LATENT", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        # 这里的 type 取决于你平台定义的 IMAGE 类型（通常对应 PIL.Image 或文件路径）
        PortDefinition(name="image", label="IMAGE", type=ArgumentType.IMAGE),
    ]
    
    def ensure_comfy_exist(self):
        import os 
        # comfyui节点必须从本地comfy包中读取
        if "comfy_extension" not in self.global_variable.custom:
            raise Exception("自定义全局变量未添加 comfy_extension 参数，无法使用comfy节点。")
        elif not os.path.exists(self.global_variable.comfy_extension):
            raise Exception("配置的 comfy_extension 参数，无法找到本地文件。")
        import sys
        sys.path.append(self.global_variable.comfy_extension)
        
    def run(self, params, inputs):
        import torch
        import numpy as np
        from PIL import Image

        # 1. 获取输入并校验
        import comfy.model_management as mm
        vae = inputs.get("vae")
        
        # 告诉调度器我要用 VAE 了
        mm.load_models_to_gpu([vae])
        latent = inputs.get("latent")
        
        if vae is None or latent is None:
            raise ValueError("VAE解码器缺少必要的输入：vae 或 latent 为空")

        # 2. 从字典中取出 Tensor
        # 标准 ComfyUI latent 是一个字典 {"samples": tensor}
        samples = latent["samples"]

        # 3. 执行解码
        # 为了防止大图 OOM (显存溢出)，建议使用 decode_tiled
        # 如果你追求极致速度且显存充足，可以用 pixels = vae.decode(samples)
        self.logger.info(f"正在解码潜空间，尺寸为: {samples.shape}")
        pixels = vae.decode(samples)

        # 4. 转换 Tensor 到 Numpy [Batch, Height, Width, Channels]
        # .cpu() 移至内存, .numpy() 转换格式
        img_np = (pixels.cpu().detach().numpy() * 255.0).clip(0, 255).astype(np.uint8)
        img_np = np.squeeze(img_np)
        # 5. 【核心修复】处理维度，确保返回的是 PIL 兼容的 3D 数组 (H, W, C)
        if len(img_np.shape) == 4:
            # 如果 batch_size > 1，这里默认取第一张。
            # 如果你的平台支持图像列表，可以循环处理
            img_np = img_np[0] 

        # 6. 安全校验：防止出现 (1, 512, 3) 这种高度异常的情况
        if img_np.shape[0] < 2 or img_np.shape[1] < 2:
             raise ValueError(f"生成的图像尺寸异常: {img_np.shape}，请检查潜空间尺寸")

        # 7. 转换为 PIL Image 并输出
        try:
            out_img = Image.fromarray(img_np, mode='RGB')
            self.logger.info(f"解码成功，图像尺寸: {out_img.width}x{out_img.height}")
            return {"image": out_img}
        except Exception as e:
            self.logger.error(f"PIL转换失败: {str(e)}，数组形状: {img_np.shape}")
            raise e