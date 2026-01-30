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


class Qwen3TTSModelLoader(BaseComponent):
    name = "Qwen3 TTS 模型加载"
    category = "comfyui节点/Qwen-TTS"
    description = "加载 Qwen3-TTS 模型，支持指定本地路径或使用标准目录下的模型"
    requirements = "# _qwen_tts_haigc,# comfy_qwen_tts,# folder_paths,librosa,mediapipe>=0.10.31,modelscope,onnxruntime,sox,tf-keras>=2.18,torch,torchaudio,transformers,transparent-background>=1.3.4"

    outputs = [
        PortDefinition(name="model", label="MODEL", type=ArgumentType.OBJECT),
    ]

    properties = {
        "local_model": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="本地模型路径",
        ),
        "online_model": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
            label="标准目录模型",
            choices=["Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", "Qwen/Qwen3-TTS-12Hz-1.7B-Base", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"]
        ),
        "device": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="auto",
            label="运行设备",
            choices=["auto", "cuda", "cpu"]
        ),
        "precision": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="fp16",
            label="精度",
            choices=["fp16", "fp32"]
        ),
    }

    def run(self, params, inputs=None):
        import os
        import shutil
        import folder_paths
        import torch
        # 假设环境已包含此模块，或由requirements自动安装
        from _qwen_tts_haigc import Qwen3TTSModel

        # 1. 获取参数
        local_path_input = params.get("local_model", "").strip()
        online_model_name = params.get("online_model", "")
        device_str = params.get("device", "auto")
        precision = params.get("precision", "fp16")

        # 2. 设置设备
        if device_str == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            device = device_str

        model_path = None

        # 3. 路径判定逻辑：优先使用本地路径
        if local_path_input and os.path.exists(local_path_input):
            # transformers 的 from_pretrained 通常加载的是"文件夹"
            # 如果用户选中的是文件（如 .safetensors 或 config.json），则取其父目录
            if os.path.isfile(local_path_input):
                model_path = os.path.dirname(local_path_input)
            else:
                model_path = local_path_input
            
            self.logger.info(f"检测到本地路径设定，将加载: {model_path}")
        
        else:
            # 4. 回退逻辑：使用 ComfyUI 标准目录 (models/qwen-tts)
            qwen_models_dir = os.path.join(folder_paths.models_dir, "qwen-tts")
            
            # 提取文件夹名称 (去除 Qwen/ 前缀)
            model_folder_name = online_model_name.split("/")[-1]
            target_path = os.path.join(qwen_models_dir, model_folder_name)

            # --- 旧版本文件夹名称兼容与修复 ---
            if not os.path.exists(target_path) or not os.path.isdir(target_path):
                messy_names = [
                    model_folder_name.replace(".", "__"),
                    model_folder_name.replace("1.7B", "1__7B"),
                    model_folder_name.replace("0.6B", "0__6B"),
                    model_folder_name.replace("1.7B", "1-7B"),
                    model_folder_name.replace("0.6B", "0-6B"),
                    model_folder_name.replace(".", "-"),
                ]
                for bad_path_name in messy_names:
                    bad_path = os.path.join(qwen_models_dir, bad_path_name)
                    if os.path.exists(bad_path) and os.path.isdir(bad_path):
                        self.logger.info(f"发现旧命名文件夹，正在重命名: {bad_path} -> {target_path}")
                        try:
                            shutil.move(bad_path, target_path)
                            break
                        except Exception as e:
                            self.logger.warning(f"重命名失败: {e}")

            if not os.path.exists(target_path):
                raise FileNotFoundError(
                    f"模型未找到。\n"
                    f"1. 未指定有效的'本地模型'路径。\n"
                    f"2. 标准路径 {target_path} 不存在。\n"
                    f"请下载模型至 ComfyUI/models/qwen-tts 目录。"
                )
            
            model_path = target_path
            self.logger.info(f"使用标准目录加载: {model_path}")

        # 5. 加载模型
        self.logger.info(f"开始加载 Qwen3TTS 模型 (Device: {device}, Precision: {precision})...")
        
        dtype = torch.float16 if precision == "fp16" else torch.float32

        try:
            # 尝试使用完整参数加载（支持 Flash Attention 2）
            model = Qwen3TTSModel.from_pretrained(
                model_path, 
                device_map=device, 
                dtype=dtype,
                local_files_only=True,     # 强制本地，不联网下载
                force_download=False,
                attn_implementation="flash_attention_2"
            )
        except (TypeError, ValueError, ImportError) as e:
            self.logger.warning(f"Flash Attention 加载失败或参数不支持，尝试降级加载: {e}")
            try:
                # 降级尝试：移除 attn_implementation
                model = Qwen3TTSModel.from_pretrained(
                    model_path, 
                    device_map=device, 
                    torch_dtype=dtype,
                    local_files_only=True,
                    force_download=False
                )
            except Exception as final_e:
                # 再次降级：最简加载
                self.logger.warning(f"标准加载失败，尝试最简加载: {final_e}")
                model = Qwen3TTSModel.from_pretrained(
                    model_path, 
                    local_files_only=True,
                    force_download=False
                )
                # 手动移动到设备
                if hasattr(model, "to"):
                    model.to(device)

        return {"model": model}