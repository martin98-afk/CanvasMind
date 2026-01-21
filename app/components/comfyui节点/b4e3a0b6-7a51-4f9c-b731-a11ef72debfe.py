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


class ComfyUIConfig(BaseComponent):
    requirements = "comfy"
    name = "ComfyUI全局配置"
    category = "comfyui节点"
    description = "设置显存管理策略，建议放在流程起始位置"
    
    properties = {
        "vram_mode": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="normal",
            label="显存策略 (Low=极低显存, Normal=平衡, High=全速)",
            choices=["low", "normal", "high"]
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

    def run(self, params, inputs=None):
        self.ensure_comfy_exist()
        import comfy.model_management as mm
        
        # 1. 触发设备检测 (替代 init_device_info)
        # 调用 get_torch_device 会强制 ComfyUI 去检测当前的 CUDA/显存状态
        device = mm.get_torch_device()
        self.logger.info(f"ComfyUI 当前使用的设备: {device}")

        # 2. 设置显存策略
        mode = params.get("vram_mode", "normal")
        if mode == "low":
            # 极低显存模式 (对应启动参数 --lowvram)
            mm.vram_state = mm.VRAMState.LOW_VRAM
        elif mode == "normal":
            # 标准显存模式
            mm.vram_state = mm.VRAMState.NORMAL_VRAM
        else:
            # 高显存模式 (尽量不卸载模型)
            mm.vram_state = mm.VRAMState.HIGH_VRAM
            
        # 3. 如果你想手动设置显存权重（可选）
        # mm.set_vram_priority_mode(mm.VRAMPriorityMode.LOW_VRAM) # 某些版本可用
        
        return {}