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


class ComfyLoraLoader(BaseComponent):
    requirements = "comfy"
    name = "LoRA加载器"
    category = "comfyui节点"
    description = "为模型和 CLIP 叠加 LoRA 补丁"
    
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
            label="LoRA文件路径",
        ),
        "strength_model": PropertyDefinition(
            type=PropertyType.RANGE,
            default="1.00",
            label="模型权重 (Strength Model)",
            min=-10.0,
            max=10.0,
            step=0.01,
        ),
        "strength_clip": PropertyDefinition(
            type=PropertyType.RANGE,
            default="1.00",
            label="CLIP权重 (Strength CLIP)",
            min=-10.0,
            max=10.0,
            step=0.01,
        ),
    }
    
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
        self.ensure_comfy_exist()
        import comfy.utils
        import comfy.sd
        import os

        # 1. 获取输入模型
        model = inputs.get("model")
        clip = inputs.get("clip")
        lora_path = params.get("lora_path")
        
        if model is None or clip is None:
            raise ValueError("LoRA 加载器需要连接 MODEL 和 CLIP 输入")
        
        if not lora_path or not os.path.exists(lora_path):
            self.logger.warning(f"未选择 LoRA 或文件不存在: {lora_path}，将跳过叠加。")
            return {"model": model, "clip": clip}

        strength_model = float(params.get("strength_model", 1.0))
        strength_clip = float(params.get("strength_clip", 1.0))

        # 2. 加载 LoRA 权重文件
        self.logger.info(f"正在加载 LoRA: {os.path.basename(lora_path)}")
        lora_weights = comfy.utils.load_torch_file(lora_path)

        # 3. 调用 ComfyUI 核心函数进行“打补丁”
        # 该函数会返回两个新的 Patcher 对象，原始模型不会被修改
        # 它内部会自动处理 SD1.5, SDXL, SD3.5 等不同架构的 Key 映射
        new_model, new_clip = comfy.sd.load_lora_for_models(
            model, 
            clip, 
            lora_weights, 
            strength_model, 
            strength_clip
        )

        return {
            "model": new_model,
            "clip": new_clip
        }