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


class Component(BaseComponent):
    name = "CLIP单文件加载器"
    category = "生成模型/模型加载"
    description = "直接加载单文件 .safetensors 权重 (支持 CLIP, Qwen-VL, T5 等)"
    requirements = "numpy,transformers,torch,accelerate,safetensors"
    
    inputs = []
    outputs = [
        PortDefinition(name="clip", label="模型束", type=ArgumentType.OBJECT),
    ]
    
    properties = {
        "model_file": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="Safetensors文件路径",
        ),
        "config_repo": PropertyDefinition(
            type=PropertyType.TEXT,
            default="openai/clip-vit-large-patch14",
            label="配置源 (HF Repo ID)",
            description="由于单文件不含配置，需指定该权重对应的模型类型以初始化架构"
        ),
        "device": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="cuda",
            label="加载设备",
            choices=["cuda", "cpu", "auto"]
        ),
        "precision": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="fp16",
            label="加载精度",
            choices=["fp16", "fp32", "bf16"]
        ),
        "trust_remote_code": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="信任远程代码",
        ),
    }

    def run(self, params, inputs=None):
        import torch
        import os
        from safetensors.torch import load_file
        from transformers import AutoConfig, AutoModel, AutoProcessor
        from accelerate import init_empty_weights

        # 内部包装类
        class ClipWrapper:
            def __init__(self, model, processor):
                self.model = model
                self.processor = processor
            def __repr__(self):
                return f"<ClipWrapper model={type(self.model).__name__} device={self.model.device}>"

        # 1. 获取参数
        file_path = params.get("model_file")
        config_id = params.get("config_repo")
        device_mode = params.get("device", "cuda")
        precision = params.get("precision", "fp16")
        trust_code = params.get("trust_remote_code", True)

        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"未找到有效的模型文件: {file_path}")

        dtype = {"fp16": torch.float16, "fp32": torch.float32, "bf16": torch.bfloat16}.get(precision, torch.float16)
        target_device = torch.device("cuda" if (device_mode == "cuda" or (device_mode == "auto" and torch.cuda.is_available())) else "cpu")

        self.logger.info(f"正在准备架构: {config_id}")

        try:
            # 2. 获取配置
            config = AutoConfig.from_pretrained(config_id, trust_remote_code=trust_code)
            
            # 3. 初始化模型（处理 Meta Tensor 报错的关键步骤）
            with init_empty_weights():
                model = AutoModel.from_config(config, trust_remote_code=trust_code)

            # 4. 关键修复：先将 Meta 模型转换为真实内存模型（但不分配权重数据）
            model = model.to_empty(device=target_device)
            
            # 5. 载入单文件权重
            self.logger.info(f"正在载入权重数据: {os.path.basename(file_path)}")
            state_dict = load_file(file_path, device=str(target_device))

            # 6. 处理权重 Key 对齐 (适配 ComfyUI 导出的单文件)
            # 有时单文件权重带有 'model.' 或 'cond_stage_model.' 前缀
            first_key = next(iter(state_dict))
            if not hasattr(model, first_key.split('.')[0]) and '.' in first_key:
                new_state_dict = {}
                prefix = first_key.split('.')[0] + "."
                self.logger.info(f"检测到权重前缀 '{prefix}'，正在尝试自动对齐...")
                for k, v in state_dict.items():
                    new_state_dict[k.replace(prefix, "")] = v
                state_dict = new_state_dict

            # 7. 加载权重到模型
            model.load_state_dict(state_dict, strict=False)
            model.to(dtype)
            
            # 8. 加载处理器
            try:
                processor = AutoProcessor.from_pretrained(config_id, trust_remote_code=trust_code)
            except:
                processor = None

            self.logger.info(f"加载成功！模型已就绪于 {target_device}")
            
            return {"clip": ClipWrapper(model, processor)}

        except Exception as e:
            self.logger.error(f"加载过程中出错: {str(e)}")
            raise e