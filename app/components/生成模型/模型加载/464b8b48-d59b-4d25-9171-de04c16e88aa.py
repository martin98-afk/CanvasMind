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
    name = "CLIP单文件加载器 (终极版)"
    category = "生成模型/模型加载"
    description = "智能加载CLIP/T5权重，支持ComfyUI格式/SD内嵌权重，带自动健康检查"
    requirements = "numpy,transformers,torch,accelerate,safetensors"
    
    inputs = []
    outputs = [
        PortDefinition(name="clip", label="CLIP模型束", type=ArgumentType.OBJECT),
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
            description="SD1.5用 openai/clip-vit-large-patch14; SDXL Clip-G用 laion/CLIP-ViT-bigG-14-laion2B-39B-b160k",
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
        "local_tokenizer": PropertyDefinition(
            type=PropertyType.FILE,
            default="folder",
            label="本地Tokenizer路径(可选)",
        ),
    }

    def run(self, params, inputs=None):
        # ================== 1. 严格的函数内导入 ==================
        import torch
        import os
        import numpy as np
        from safetensors.torch import load_file
        from transformers import AutoConfig, AutoModel, AutoTokenizer, AutoProcessor
        from accelerate import init_empty_weights

        # ================== 2. 内部包装类 ==================
        class ClipWrapper:
            def __init__(self, model, tokenizer, processor=None):
                self.model = model
                self.tokenizer = tokenizer
                self.processor = processor
                self.device = model.device
            
            def tokenize(self, texts):
                if not self.tokenizer:
                    raise ValueError("Tokenizer未加载，无法处理文本")
                return self.tokenizer(texts, padding="max_length", max_length=77, truncation=True, return_tensors="pt").to(self.device)

            def __repr__(self):
                return f"<ClipWrapper model={type(self.model).__name__} device={self.device}>"

        # ================== 3. 参数与环境准备 ==================
        file_path = params.get("model_file")
        config_id = params.get("config_repo")
        device_mode = params.get("device", "cuda")
        precision = params.get("precision", "fp16")
        local_tokenizer_path = params.get("local_tokenizer")

        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        dtype_map = {"fp16": torch.float16, "fp32": torch.float32, "bf16": torch.bfloat16}
        target_dtype = dtype_map.get(precision, torch.float16)
        
        if device_mode == "auto":
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            device = torch.device(device_mode)

        self.logger.info(f"正在初始化架构: {config_id} (Target: {device})")

        try:
            # ================== 4. 初始化空模型 (显存优化) ==================
            config = AutoConfig.from_pretrained(config_id, trust_remote_code=True)
            with init_empty_weights():
                model = AutoModel.from_config(config, trust_remote_code=True)

            # ================== 5. 读取与权重提取 (双重策略) ==================
            self.logger.info(f"读取文件: {os.path.basename(file_path)}")
            raw_state_dict = load_file(file_path, device="cpu") # 先读到内存，方便处理字典
            final_state_dict = {}

            # --- 策略A: 智能前缀匹配与Key转换 (应对OpenCLIP/ComfyUI提取出的复杂权重) ---
            anchor_keys = [
                "text_model.embeddings.position_embedding.weight", 
                "embeddings.position_embedding.weight",
                "encoder.block.0.layer.0.SelfAttention.q.weight" # T5
            ]
            detected_prefix = ""
            for key in raw_state_dict.keys():
                for anchor in anchor_keys:
                    if key.endswith(anchor):
                        detected_prefix = key[:len(key)-len(anchor)]
                        break
                if detected_prefix: break
            
            # 常见替换表
            replacements = [("resblocks.", "layers."), (".ln_1.", ".layer_norm1."), (".ln_2.", ".layer_norm2."), ("transformer.", "text_model.")]
            model_keys = set(model.state_dict().keys())

            if detected_prefix:
                self.logger.info(f"[策略A] 检测到智能前缀: '{detected_prefix}'")
                for k, v in raw_state_dict.items():
                    if not k.startswith(detected_prefix): continue
                    
                    clean_key = k[len(detected_prefix):]
                    
                    # 尝试转换
                    replaced_key = clean_key
                    for old, new in replacements:
                        replaced_key = replaced_key.replace(old, new)
                    
                    if replaced_key in model_keys:
                        final_state_dict[replaced_key] = v
                    elif clean_key in model_keys:
                        final_state_dict[clean_key] = v
            
            # --- 策略B: 暴力回退 (模拟旧代码逻辑) ---
            if len(final_state_dict) == 0:
                self.logger.warning("[策略A] 未匹配到权重，切换回 [策略B] (暴力前缀去除)...")
                
                # 寻找第一个可能的 "Key." 前缀
                first_key = next(iter(raw_state_dict))
                prefix = ""
                if '.' in first_key:
                    candidate = first_key.split('.')[0]
                    # 如果模型里本身没有这个属性，那它大概率是前缀 (如 'cond_stage_model')
                    if not hasattr(model, candidate):
                        prefix = candidate + "."
                
                self.logger.info(f"[策略B] 使用前缀: '{prefix}'")
                for k, v in raw_state_dict.items():
                    if prefix and k.startswith(prefix):
                        final_state_dict[k.replace(prefix, "")] = v
                    else:
                        final_state_dict[k] = v

            if len(final_state_dict) == 0:
                raise ValueError("权重提取失败：两种策略均未找到有效权重。")

            # ================== 6. 载入权重到设备 ==================
            self.logger.info(f"正在加载 {len(final_state_dict)} 个张量到显存...")
            model.to_empty(device=device) # 将 Meta Tensor 转为真实 Tensor
            
            # strict=False 允许缺失非必要权重 (如 vision model 部分)
            missing, unexpected = model.load_state_dict(final_state_dict, strict=False)
            
            model.to(target_dtype)
            model.eval()

            # ================== 7. 加载 Tokenizer ==================
            tokenizer_path = local_tokenizer_path if local_tokenizer_path else config_id
            try:
                tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, trust_remote_code=True)
            except Exception as e:
                self.logger.warning(f"Tokenizer加载失败: {e}")
                tokenizer = None

            # ================== 8. 模型健康自检 (Validation) ==================
            self.logger.info(">>> 开始模型健康检查...")
            is_healthy = False
            
            if tokenizer:
                try:
                    # 构造测试输入
                    test_text = ["test check"]
                    inputs = tokenizer(test_text, padding=True, return_tensors="pt").to(device)
                    
                    with torch.no_grad():
                        outputs = model(**inputs)
                    
                    # 尝试获取输出 Embedding
                    check_tensor = None
                    if hasattr(outputs, "pooler_output") and outputs.pooler_output is not None:
                        check_tensor = outputs.pooler_output
                    elif hasattr(outputs, "last_hidden_state"):
                        check_tensor = outputs.last_hidden_state
                    elif hasattr(outputs, "text_embeds"):
                        check_tensor = outputs.text_embeds
                    elif isinstance(outputs, tuple):
                        check_tensor = outputs[0]
                    
                    if check_tensor is not None:
                        # 检查 NaN
                        if torch.isnan(check_tensor).any():
                            self.logger.error("❌ 严重错误：模型输出包含 NaN (数值溢出)！建议尝试 fp32 或 bf16。")
                        # 检查 全0
                        elif torch.all(check_tensor == 0):
                            self.logger.error("❌ 严重错误：模型输出全为 0！权重可能未正确加载。")
                        else:
                            mean_val = check_tensor.abs().mean().item()
                            self.logger.info(f"✅ 自检通过！输出均值: {mean_val:.4f} (非零且非NaN)")
                            is_healthy = True
                    else:
                        self.logger.warning("⚠️ 自检无法获取输出张量，跳过数值检查。")
                except Exception as check_e:
                    self.logger.warning(f"⚠️ 自检过程中发生错误 (可能是架构不兼容): {check_e}")
            else:
                self.logger.warning("⚠️ 跳过自检：无 Tokenizer")

            if not is_healthy and len(final_state_dict) > 0:
                self.logger.warning("模型已加载但未通过自检，请谨慎使用。")

            # ================== 9. 返回 ==================
            return {"clip": ClipWrapper(model, tokenizer, None)}

        except Exception as e:
            self.logger.error(f"加载崩溃: {str(e)}")
            raise e