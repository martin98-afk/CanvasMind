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


class VAEEncodeComponent(BaseComponent):
    name = "VAE编码器"
    category = "生成模型/图像生成"
    description = "将可视化图像压缩为潜空间 Latent 数据 (用于图生图)"
    requirements = "diffusers,torch,Pillow,numpy,torchvision"

    inputs = [
        PortDefinition(name="image", label="输入图像", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        # 输出 NumPy 序列化后的字节流
        PortDefinition(name="latent", label="潜空间数据", type=ArgumentType.ARRAY),
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
        from PIL import Image
        from diffusers import AutoencoderKL
        import torchvision.transforms as T

        # 1. 获取输入图像 (PIL 对象)
        pil_image = inputs.get("image")
        if pil_image is None:
            raise ValueError("未接收到输入图像")
        
        model_id = params.get("model_id", "runwayml/stable-diffusion-v1-5")

        # 2. 图像预处理
        # VAE 要求输入尺寸必须是 8 的倍数，且像素值需归一化到 [-1, 1]
        w, h = pil_image.size
        new_w, new_h = (w // 8) * 8, (h // 8) * 8
        if w != new_w or h != new_h:
            self.logger.warning(f"图像尺寸 {w}x{h} 已调整为 {new_w}x{new_h} 以适配 VAE")
            pil_image = pil_image.resize((new_w, new_h), resample=Image.LANCZOS)

        # 转换为 Tensor: [C, H, W]，并归一化到 [0, 1]
        img_tensor = T.ToTensor()(pil_image).to("cuda", dtype=torch.float16)
        # 进一步归一化到 [-1, 1]
        img_tensor = 2.0 * img_tensor - 1.0
        # 增加 Batch 维度: [1, C, H, W]
        img_tensor = img_tensor.unsqueeze(0)


        self.logger.info(f"正在加载 VAE 模型: {model_id}")
        vae = AutoencoderKL.from_pretrained(
            model_id, 
            subfolder="vae", 
            torch_dtype=torch.float16
        ).to("cuda")
        # 4. 执行编码逻辑
        self.logger.info("正在执行 VAE 编码...")
        with torch.no_grad():
            # 编码得到分布
            posterior = vae.encode(img_tensor).latent_dist
            # 从分布中采样得到 Latent (通常使用 mode 或者是 sample)
            latents = posterior.sample()
            
            # 关键：Stable Diffusion 的标准操作，编码后需乘以缩放系数 0.18215
            latents = latents * 0.18215

        self.logger.info("VAE 编码完成")

        # 5. 将结果转换为 NumPy 数组并序列化
        # 这一步是为了让“没有 Torch 的主程序”能够无障碍地传递数据
        latent_ndarray = latents.cpu().numpy()

        return {
            "latent": latent_ndarray
        }
    

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = VAEEncodeComponent()
    result = model.debug(
        params={"prop1": "test"},
        inputs={"input1": "output"},
        node_id="测试模型",
        show_input_types = True,
        show_output_types = True,
        show_execution_time = True,
        global_vars = {}
    )
    print(result)
