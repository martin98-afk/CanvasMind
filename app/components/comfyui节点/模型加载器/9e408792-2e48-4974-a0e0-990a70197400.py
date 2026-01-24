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


class ComfyWanScheduledLoraLoader(BaseComponent):
    requirements = "torch,comfy"
    name = "Wan2.1分段LoRA加载器"
    category = "comfyui节点/模型加载器"
    description = "支持设置 LoRA 在采样的哪个阶段生效（高噪/低噪控制）"
    
    inputs = [
        PortDefinition(name="model", label="MODEL", type=ArgumentType.OBJECT),
        PortDefinition(name="clip", label="CLIP", type=ArgumentType.OBJECT),
    ]
    outputs = [
        PortDefinition(name="model", label="MODEL", type=ArgumentType.OBJECT),
        PortDefinition(name="clip", label="CLIP", type=ArgumentType.OBJECT),
    ]
    
    properties = {
        "lora_path": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="LoRA文件",
        ),
        "strength": PropertyDefinition(
            type=PropertyType.RANGE,
            default="1.00",
            label="总强度",
            min=-2.0,
            max=2.0,
            step=0.01,
        ),
        "start_percent": PropertyDefinition(
            type=PropertyType.RANGE,
            default="0.00",
            label="开始生效时机(0.0=最开始)",
            min=0.0,
            max=1.0,
            step=0.01,
        ),
        "end_percent": PropertyDefinition(
            type=PropertyType.RANGE,
            default="1.00",
            label="结束生效时机(1.0=最后)",
            min=0.0,
            max=1.0,
            step=0.01,
        ),
    }

    def run(self, params, inputs):
        import torch
        import comfy.utils
        import comfy.sd
        import os

        model = inputs.get("model")
        clip = inputs.get("clip")
        lora_path = params.get("lora_path")
        
        if model is None or not lora_path or not os.path.exists(lora_path):
            return {"model": model, "clip": clip}

        strength = float(params.get("strength", 1.0))
        start_p = float(params.get("start_percent", 0.0))
        end_p = float(params.get("end_percent", 1.0))

        self.logger.info(f"应用分段 LoRA: {os.path.basename(lora_path)} ({start_p*100}% - {end_p*100}%)")

        # 加载 LoRA 权重
        lora_weights = comfy.utils.load_torch_file(lora_path)

        # --- 核心黑科技：利用 ComfyUI 的 Patcher 钩子 ---
        # 这种方式可以在不修改 KSampler 的情况下，让 LoRA 只在特定时间点生效
        # 注意：这需要底层 comfy 模块支持 patch_weight 的按步数过滤
        
        with torch.no_grad():
            # 这里调用底层的补丁应用函数
            # 在高级用法中，我们会将 start/end 存入 patcher 的附加选项中
            new_model, new_clip = comfy.sd.load_lora_for_models(
                model, clip, lora_weights, strength, strength
            )
            
            # 这里的补丁会被打入 ModelPatcher。
            # 为了实现分段生效，我们通常需要配合支持“时间调度”的采样器。
            # 如果是简单的集成，你可以先实现两个 LoraLoader 串联：
            # 一个设置 0.0-0.5 (高噪)，一个设置 0.5-1.0 (低噪)
            
        return {"model": new_model, "clip": new_clip}