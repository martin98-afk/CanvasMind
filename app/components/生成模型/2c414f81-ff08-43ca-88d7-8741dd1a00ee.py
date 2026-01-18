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


class ModelLoaderComponent(BaseComponent):
    name = "模型加载器"
    category = "生成模型"
    description = "通过文件选择器加载本地模型（文件夹或单文件）"
    requirements = "diffusers,torch,transformers,accelerate,safetensors,omegaconf,modelscope"

    inputs = [
        
    ]
    
    outputs = [
        PortDefinition(name="model", label="模型对象", type=ArgumentType.OBJECT),
    ]

    properties = {
        "model": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="模型文件选择",
        ),
        "precision": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="float16",
            label="精度",
            choices=["float16", "float32"]
        ),
        "device": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="cuda",
            label="运行设备",
            choices=["cuda", "cpu"]
        ),
    }

    def run(self, params, inputs=None):
        import torch
        import os
        from diffusers import StableDiffusionPipeline
        # 1. 获取路径（优先从输入端口获取，如果没有则可能需要报错）
        model_path = params.model
        
        if not model_path:
            raise ValueError("请连接或选择模型文件路径")
        
        # 统一路径格式，处理不同系统的斜杠
        model_path = os.path.abspath(model_path)
        
        precision = params.get("precision", "float16")
        device = params.get("device", "cuda")
        torch_dtype = torch.float16 if precision == "float16" else torch.float32

        # 2. 缓存检查
        self.logger.info(f"🚀 开始加载模型: {model_path}")

        try:
            # 3. 根据路径类型选择加载方式
            common_args = {
                "torch_dtype": torch_dtype,
                "safety_checker": None,
                "requires_safety_checker": False,
            }

            # 情况 A: 路径是一个文件（通常是 .safetensors 或 .ckpt）
            if os.path.isfile(model_path):
                if model_path.endswith((".safetensors", ".ckpt", ".bin")):
                    self.logger.info("检测到单文件模型，使用 from_single_file 加载...")
                    try:
                        pipe = StableDiffusionPipeline.from_single_file(
                            model_path, 
                            **common_args
                        )
                    except:
                        # qwen系列模型
                        from modelscope import DiffusionPipeline
                        pipe = DiffusionPipeline.from_pretrained(
                            model_path, **common_args
                        )
                else:
                    raise ValueError(f"不支持的文件格式: {model_path}")

            # 情况 B: 路径是一个文件夹（Diffusers 格式）
            elif os.path.isdir(model_path):
                self.logger.info("检测到模型文件夹，使用 from_pretrained 加载...")
                pipe = StableDiffusionPipeline.from_pretrained(
                    model_path,
                    **common_args
                )
            else:
                raise FileNotFoundError(f"路径不存在: {model_path}")

            # 4. 移动到设备并优化
            pipe = pipe.to(device)
            
            if device == "cuda":
                # 显存优化
                pipe.enable_attention_slicing()
                if torch.__version__ >= "2.0":
                    # PyTorch 2.0+ 自动使用高效注意力机制
                    pass
                else:
                    try: pipe.enable_xformers_memory_efficient_attention()
                    except: pass

            return {"model": pipe}

        except Exception as e:
            self.logger.error(f"❌ 模型加载失败: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            raise e