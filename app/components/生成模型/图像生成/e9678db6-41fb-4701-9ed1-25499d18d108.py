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


class VAEDecodeComponent(BaseComponent):
    name = "VAE解码器"
    category = "生成模型/图像生成"
    description = "将潜空间 Latent 数据解码为可视化图像"
    requirements = "diffusers,torch,Pillow,numpy"
    
    inputs = [
        PortDefinition(name="latent", label="潜空间数据", type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="image", label="解码图像", type=ArgumentType.IMAGE),
    ]
    
    properties = {
        "model_id": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="runwayml/stable-diffusion-v1-5",
            label="VAE权重来源",
            choices=["runwayml/stable-diffusion-v1-5", "stabilityai/sd-vae-ft-mse"]
        ),
    }

    def run(self, params, inputs=None):
        import torch
        import numpy as np
        from PIL import Image
        from diffusers import AutoencoderKL

        # 1. 获取输入数据
        latent_ndarray = inputs.get("latent")
        latents = torch.from_numpy(latent_ndarray).to("cuda", dtype=torch.float16)
        
        model_id = params.get("model_id", "runwayml/stable-diffusion-v1-5")

        vae = AutoencoderKL.from_pretrained(
            model_id, 
            subfolder="vae", 
            torch_dtype=torch.float16
        ).to("cuda")
        
        # 4. 执行解码逻辑
        self.logger.info("正在执行 VAE 解码...")
        with torch.no_grad():
            # 关键：Stable Diffusion 的 Latent 需要除以缩放系数 0.18215 才能还原
            latents = 1 / 0.18215 * latents
            
            # 解码
            decoded_output = vae.decode(latents).sample
            
            # 后处理：将张量转换为 [0, 1] 范围的像素值
            image = (decoded_output / 2 + 0.5).clamp(0, 1)
            
            # 转换维度: [Batch, Channel, H, W] -> [H, W, Channel]
            image = image.cpu().permute(0, 2, 3, 1).float().numpy()
            
            # 转换为 uint8 [0, 255]
            image = (image[0] * 255).astype(np.uint8)
            
            # 创建 PIL 对象
            final_image = Image.fromarray(image)

        self.logger.info("VAE 解码完成")

        # 5. 返回结果
        # 主程序会接收到这个 PIL 对象并利用之前优化的 ImageWidget 进行显示
        return {
            "image": final_image
        }

if __name__ == "__main__":
    # 本地调试代码 (需在有 GPU 的环境运行)
    VAEDecodeComponent()