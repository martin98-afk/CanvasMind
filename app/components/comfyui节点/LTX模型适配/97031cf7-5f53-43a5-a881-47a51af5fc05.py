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


class LTXVScheduler(BaseComponent):
    requirements = "torch"
    name = "LTX2专用调度器"
    category = "comfyui节点/LTX模型适配"
    description = "生成 LTX2 优化的时间步序列（Sigmas），支持偏移拉伸。"
    
    inputs = [PortDefinition(name="latent", label="LATENT(可选)", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE, optional=True)]
    outputs = [PortDefinition(name="sigmas", label="SIGMAS", type=ArgumentType.OBJECT)]
    properties = {
        "steps": PropertyDefinition(type=PropertyType.INT, default=20, label="步数"),
        "max_shift": PropertyDefinition(type=PropertyType.FLOAT, default=2.05, label="Max Shift"),
        "base_shift": PropertyDefinition(type=PropertyType.FLOAT, default=0.95, label="Base Shift"),
        "stretch": PropertyDefinition(type=PropertyType.BOOL, default=True, label="拉伸(Stretch)"),
        "terminal": PropertyDefinition(type=PropertyType.FLOAT, default=0.1, label="终端值"),
    }

    def run(self, params, inputs):
        import math
        import torch
        
        steps = int(params.get("steps"))
        latent = inputs.get("latent")
        
        # 计算 shift
        tokens = 4096
        if latent is not None:
            tokens = math.prod(latent["samples"].shape[2:])
        
        x1, x2 = 1024, 4096
        mm_val = (params.get("max_shift") - params.get("base_shift")) / (x2 - x1)
        b = params.get("base_shift") - mm_val * x1
        sigma_shift = (tokens) * mm_val + b

        # 生成基础 sigmas
        sigmas = torch.linspace(1.0, 0.0, steps + 1)
        
        # 应用 Shift 变换
        power = 1
        sigmas = torch.where(
            sigmas != 0,
            math.exp(sigma_shift) / (math.exp(sigma_shift) + (1 / sigmas - 1) ** power),
            torch.zeros_like(sigmas),
        )

        # Sigma 拉伸逻辑
        if params.get("stretch"):
            non_zero_mask = sigmas != 0
            non_zero_sigmas = sigmas[non_zero_mask]
            one_minus_z = 1.0 - non_zero_sigmas
            scale_factor = one_minus_z[-1] / (1.0 - params.get("terminal"))
            stretched = 1.0 - (one_minus_z / scale_factor)
            sigmas[non_zero_mask] = stretched

        return {"sigmas": sigmas}