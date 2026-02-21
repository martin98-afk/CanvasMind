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


class KSampler(BaseComponent):
    name = "K采样器"
    category = "comfyui节点/基础节点"
    description = "使用指定模型和条件对潜空间进行降噪采样，生成最终图像潜变量"
    requirements = "#comfy,torch,latent_preview"
    inputs = [
        PortDefinition(name="model", label="模型", type=ArgumentType.OBJECT, sub_type="MODEL", connection=ConnectionType.SINGLE),
        PortDefinition(name="positive", label="正向条件", type=ArgumentType.OBJECT, sub_type="Conditioning", connection=ConnectionType.SINGLE),
        PortDefinition(name="negative", label="负向条件", type=ArgumentType.OBJECT, sub_type="Conditioning", connection=ConnectionType.SINGLE),
        PortDefinition(name="latent_image", label="输入潜空间", type=ArgumentType.OBJECT, sub_type="LATENT", connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="latent", label="输出潜空间", type=ArgumentType.OBJECT, sub_type="LATENT"),
    ]
    properties = {
        "seed": PropertyDefinition(
            type=PropertyType.INT,
            default=-1,
            label="随机种子",
            description="指定随机种子，-1时为随机",
        ),
        "steps": PropertyDefinition(
            type=PropertyType.INT,
            default=20,
            label="采样步数",
            description="降噪过程的迭代步数，1-10000",
        ),
        "cfg": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=8.0,
            label="CFG尺度",
            description="分类器无关引导强度，控制与提示词的匹配程度",
        ),
        "sampler_name": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="euler",
            label="采样器",
            description="采样算法，如euler, ddim, dpmpp_2m等",
            choices=["uni_pc", "euler", "euler_ancestral", "dpmpp_2m", "dpmpp_sde", "lms"]
        ),
        "scheduler": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="simple",
            label="调度器",
            description="噪声调度策略，如normal, karras, exponential等",
            choices=["simple", "normal", "exponential", "karras"]
        ),
        "denoise": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=1.0,
            label="降噪强度",
            description="降噪程度，0.0-1.0，值越低保留原图结构越多",
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import torch
        import comfy
        import comfy.sample
        import comfy.utils
        import latent_preview
        
        # 获取输入参数
        model = inputs.model
        positive = inputs.positive
        negative = inputs.negative
        latent = inputs.latent_image
        
        # 获取属性参数
        seed = int(params.seed)
        steps = int(params.steps)
        cfg = float(params.cfg)
        sampler_name = str(params.sampler_name)
        scheduler = str(params.scheduler)
        denoise = float(params.denoise)
        
        # 验证必要输入
        if model is None:
            raise ValueError("模型输入不能为空")
        if latent is None:
            raise ValueError("潜空间输入不能为空")
        
        # 处理潜空间通道
        latent_image = latent["samples"]
        latent_image = comfy.sample.fix_empty_latent_channels(model, latent_image)
        
        # 生成噪声
        if seed == -1:
            # 使用系统随机种子
            generator = torch.Generator(device="cpu")
            seed = generator.seed()
        
        batch_inds = latent.get("batch_index") if isinstance(latent, dict) and "batch_index" in latent else None
        noise = comfy.sample.prepare_noise(latent_image, seed, batch_inds)
        
        # 处理噪声遮罩
        noise_mask = latent.get("noise_mask") if isinstance(latent, dict) and "noise_mask" in latent else None
        
        # 准备进度回调
        callback = latent_preview.prepare_callback(model, steps)
        disable_pbar = not comfy.utils.PROGRESS_BAR_ENABLED
        
        # 执行采样
        samples = comfy.sample.sample(
            model=model,
            noise=noise,
            steps=steps,
            cfg=cfg,
            sampler_name=sampler_name,
            scheduler=scheduler,
            positive=positive,
            negative=negative,
            latent_image=latent_image,
            denoise=denoise,
            disable_noise=False,
            start_step=None,
            last_step=None,
            force_full_denoise=False,
            noise_mask=noise_mask,
            callback=callback,
            disable_pbar=disable_pbar,
            seed=seed
        )
        
        # 构建输出潜空间
        out = latent.copy() if isinstance(latent, dict) else {}
        out["samples"] = samples
        
        return {
            "latent": out
        }