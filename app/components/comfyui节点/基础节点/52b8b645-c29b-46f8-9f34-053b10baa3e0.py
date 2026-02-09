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


class ComfyModelSamplingSD3(BaseComponent):
    requirements = "#comfy"
    name = "采样算法(SD3)"
    category = "comfyui节点/基础节点"
    description = "基于 DiscreteFlow 针对 SD3/Flux 等模型调整采样 Shift 和 Multiplier 参数。"

    inputs = [
        PortDefinition(name="model", label="模型", type=ArgumentType.OBJECT, sub_type="MODEL", connection=ConnectionType.SINGLE),
    ]

    outputs = [
        PortDefinition(name="model", label="模型", type=ArgumentType.OBJECT, sub_type="MODEL"),
    ]

    properties = {
        "shift": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=5.0,
            label="采样偏移 (Shift)",
        ),
    }

    def ensure_comfy_exist(self):
        import os, sys
        if hasattr(self, "global_variable") and hasattr(self.global_variable, "comfy_extension"):
            path = self.global_variable.comfy_extension
            if path not in sys.path:
                sys.path.append(path)
                os.chdir(path)

    def run(self, params, inputs):
        self.ensure_comfy_exist()
        import comfy.model_sampling
        
        # 1. 获取输入与参数
        model = inputs.get("model")
        shift = float(params.get("shift", 3.0))
        multiplier = float(params.get("multiplier", 1.0))

        if model is None:
            raise ValueError("输入模型不能为空")

        self.logger.info(f"应用 SD3 采样: Shift={shift}, Multiplier={multiplier}")

        try:
            # --- 核心源码逻辑开始 ---
            # 1. 克隆模型
            m = model.clone()

            # 2. 定义采样类型 (SD3 使用 DiscreteFlow + CONST)
            sampling_base = comfy.model_sampling.ModelSamplingDiscreteFlow
            sampling_type = comfy.model_sampling.CONST

            # 3. 动态定义类 (混合两个基类)
            class ModelSamplingAdvanced(sampling_base, sampling_type):
                pass

            # 4. 实例化新的采样对象
            model_sampling = ModelSamplingAdvanced(model.model.model_config)
            
            # 5. 设置参数 (对应你提供的源码: set_parameters(shift=shift, multiplier=multiplier))
            model_sampling.set_parameters(shift=shift, multiplier=1000)
            
            # 6. 将新的采样对象 Patch 到模型中
            m.add_object_patch("model_sampling", model_sampling)
            # --- 核心源码逻辑结束 ---

            return {
                "model": m
            }

        except Exception as e:
            self.logger.error(f"应用 SD3 采样参数失败: {e}")
            raise e