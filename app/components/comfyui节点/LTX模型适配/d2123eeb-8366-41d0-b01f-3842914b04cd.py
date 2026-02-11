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


class LTXVModelConfigurator(BaseComponent):
    requirements = "# comfy"
    name = "LTX2模型配置器"
    category = "comfyui节点/LTX模型适配"
    description = "为 LTX2 模型应用动态 Shift 修正。这是 LTX2 能够生成高质量视频的关键。"
    
    inputs = [
        PortDefinition(name="model", label="MODEL", type=ArgumentType.OBJECT, sub_type="MODEL", connection=ConnectionType.SINGLE),
        PortDefinition(name="latent", label="参考Latent(用于计算Token数)", type=ArgumentType.OBJECT, sub_type="LATENT", connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="model", label="已修正MODEL", type=ArgumentType.OBJECT, sub_type="MODEL"),
    ]
    properties = {
        "max_shift": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=2.05,
            label="最大偏移",
        ),
        "base_shift": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.95,
            label="基础偏移",
        ),
    }

    def run(self, params, inputs):
        import math
        import comfy.utils
        import comfy.model_sampling
        import comfy.sample
        import comfy.nested_tensor
        model = inputs.get("model").clone()
        latent = inputs.get("latent")
        
        # 计算 Token 数量（分辨率越大，Shift 应越高）
        samples = latent["samples"]
        # LTX2 的 Token 计算基于：帧数 * 高/32 * 宽/32
        tokens = math.prod(samples.shape[2:]) 

        x1, x2 = 1024, 4096
        max_shift = float(params.get("max_shift", 2.05))
        base_shift = float(params.get("base_shift", 0.95))
        mm_val = (max_shift - base_shift) / (x2 - x1)
        b = base_shift - mm_val * x1
        shift = (tokens) * mm_val + b

        sampling_base = comfy.model_sampling.ModelSamplingFlux
        sampling_type = comfy.model_sampling.CONST
        class ModelSamplingAdvanced(sampling_base, sampling_type): pass

        model_sampling = ModelSamplingAdvanced(model.model.model_config)
        model_sampling.set_parameters(shift=shift)
        model.add_object_patch("model_sampling", model_sampling)
        
        self.logger.info(f"LTX2 Shift 已配置: {shift:.4f} (基于 {tokens} tokens)")
        return {"model": model}
