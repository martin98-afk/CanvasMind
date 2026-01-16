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


class WanModelLoaderComponent(BaseComponent):
    name = "Wan2.1 本地模型加载器"
    category = "生成模型/视频生成"
    description = "加载本地 Wan2.1/2.2 模型的 Transformer、VAE、T5 和 Scheduler"
    requirements = "diffusers,torch,transformers,accelerate,safetensors,sentencepiece"

    inputs = []
    
    outputs = [
        PortDefinition(name="transformer", label="Transformer", type=ArgumentType.OBJECT),
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT),
        PortDefinition(name="text_encoder", label="T5 文本编码器", type=ArgumentType.OBJECT),
        PortDefinition(name="tokenizer", label="分词器", type=ArgumentType.OBJECT),
        PortDefinition(name="scheduler", label="调度器", type=ArgumentType.OBJECT), # 新增输出
    ]

    properties = {
        "model_path": PropertyDefinition(
            type=PropertyType.FILE,
            default="folder",
            label="模型根目录",
        ),
        "precision": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="bfloat16",
            label="精度",
            choices=["bfloat16", "float16", "float32"]
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
        import traceback
        # 增加 FlowMatchEulerDiscreteScheduler
        from diffusers import WanTransformer3DModel, AutoencoderKLWan, FlowMatchEulerDiscreteScheduler
        from transformers import T5EncoderModel, T5Tokenizer

        model_path = os.path.abspath(params.get("model_path"))
        precision = params.get("precision", "bfloat16")
        device = params.get("device", "cuda")
        torch_dtype = torch.bfloat16 if precision == "bfloat16" else torch.float16 if precision == "float16" else torch.float32

        try:
            self.logger.info("正在加载 Wan 所有组件...")
            
            transformer = WanTransformer3DModel.from_pretrained(model_path, subfolder="transformer", torch_dtype=torch_dtype).to(device)
            vae = AutoencoderKLWan.from_pretrained(model_path, subfolder="vae", torch_dtype=torch_dtype).to(device)
            text_encoder = T5EncoderModel.from_pretrained(model_path, subfolder="text_encoder", torch_dtype=torch_dtype).to(device)
            tokenizer = T5Tokenizer.from_pretrained(model_path, subfolder="tokenizer")
            
            # --- 加载调度器 ---
            scheduler_path = os.path.join(model_path, "scheduler")
            if os.path.exists(scheduler_path):
                scheduler = FlowMatchEulerDiscreteScheduler.from_pretrained(model_path, subfolder="scheduler")
            else:
                # 如果文件夹里没提供，创建一个通用的默认值
                scheduler = FlowMatchEulerDiscreteScheduler(
                    num_train_timesteps=1000, 
                    shift=1.0, 
                    use_dynamic_splitting=True
                )
            
            self.logger.info("✅ Wan 组件(含调度器)加载完成")

            return {
                "transformer": transformer,
                "vae": vae,
                "text_encoder": text_encoder,
                "tokenizer": tokenizer,
                "scheduler": scheduler
            }
        except Exception as e:
            self.logger.error(traceback.format_exc())
            raise e