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


class Qwen3TTSVoiceFeatureExtractor(BaseComponent):
    requirements = "librosa,numpy"
    name = "Qwen3 TTS 声音特征提取"
    category = "comfyui节点/Qwen-TTS"
    description = "从参考音频中提取声音特征，供克隆或对话节点使用 (需使用 Base 模型)"
    
    inputs = [
        PortDefinition(name="model", label="输入模型", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="ref_audio", label="参考音频文件", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]

    outputs = [
        PortDefinition(name="voice_feature", label="声音特征", type=ArgumentType.OBJECT),
    ]

    properties = {
        "ref_text": PropertyDefinition(
            type=PropertyType.MULTILINE, 
            default="", 
            label="参考音频文本(填写可大幅提升相似度)"
        ),
        "x_vector_only": PropertyDefinition(
            type=PropertyType.BOOL, 
            default=False, 
            label="仅提取声学向量(不需要参考文本)"
        ),
    }

    def _load_audio_safe(self, audio_input):
        import numpy as np
        import librosa
        import io
        try:
            if isinstance(audio_input, str):
                wav, sr = librosa.load(audio_input, sr=None, mono=True)
            else:
                wav, sr = librosa.load(io.BytesIO(audio_input), sr=None, mono=True)
            return wav.astype(np.float32), sr
        except Exception as e:
            raise ValueError(f"音频解析失败: {e}")

    def run(self, params, inputs=None):
        model = inputs.get("model")
        ref_audio_input = inputs.get("ref_audio")
        
        if not model: raise ValueError("请连接 Qwen3TTS 模型")
        if not ref_audio_input: raise ValueError("请上传参考音频")

        # 1. 载入音频
        ref_wav, real_sr = self._load_audio_safe(ref_audio_input)
        
        # 2. 提取特征
        # 调用源码中的 create_voice_clone_prompt 方法
        self.logger.info("正在提取声音特征...")
        try:
            prompt_items = model.create_voice_clone_prompt(
                ref_audio=(ref_wav, real_sr),
                ref_text=params.get("ref_text").strip() or None,
                x_vector_only_mode=params.get("x_vector_only")
            )
            return {"voice_feature": prompt_items}
        except Exception as e:
            raise RuntimeError(f"特征提取失败: {e}")