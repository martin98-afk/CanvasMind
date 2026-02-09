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


class Qwen3TTSVoiceClone(BaseComponent):
    name = "Qwen3 TTS 声音克隆"
    category = "comfyui节点/Qwen-TTS"
    description = "基于参考音频克隆声音 (需使用 Base 模型)"
    requirements = "mediapipe>=0.10.31,modelscope,numpy,tf-keras>=2.18,torch,transparent-background>=1.3.4,scipy,librosa"

    inputs = [
        PortDefinition(name="model", label="输入模型", type=ArgumentType.OBJECT, sub_type="QWEN3_TTS_MODEL", connection=ConnectionType.SINGLE),
        PortDefinition(name="ref_audio", label="参考音频文件", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]

    outputs = [
        PortDefinition(name="output_audio_{{now}}.wav", label="生成语音", type=ArgumentType.FILE),
    ]

    properties = {
        "text": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="你好，我是被克隆出来的声音。",
            label="目标生成文本",
        ),
        "ref_text": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="",
            label="参考音频文本(强烈建议填写)",
        ),
        "language": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="auto",
            label="语言",
            choices=["auto", "Chinese", "English", "Japanese", "Korean", "German", "French", "Russian", "Portuguese", "Spanish", "Italian"]
        ),
        "temperature": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=1.0,
            label="采样温度(0.1-2.0)",
        ),
        "top_p": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.8,
            label="Top P",
        ),
        "seed": PropertyDefinition(
            type=PropertyType.INT,
            default=0,
            label="随机种子",
        ),
        "max_tokens": PropertyDefinition(
            type=PropertyType.INT,
            default=2048,
            label="最大Token数",
        ),
    }

    def _load_audio_safe(self, audio_input):
        """解析音频并返回 (waveform, sr)"""
        import numpy as np
        import librosa
        import io
        
        try:
            # 兼容路径字符串或字节流
            if isinstance(audio_input, str):
                # 使用 librosa 自动处理各种格式并重采样
                wav, sr = librosa.load(audio_input, sr=None, mono=True)
            else:
                # 假设是字节流
                wav, sr = librosa.load(io.BytesIO(audio_input), sr=None, mono=True)
            
            # 转换为 float32 并确保 1D
            wav = wav.astype(np.float32)
            # 最小长度填充 (Qwen3 内部要求)
            if wav.size < 1024:
                wav = np.pad(wav, (0, 1024 - wav.size), mode='constant')
            return wav, sr
        except Exception as e:
            raise ValueError(f"音频解析失败: {e}")

    def run(self, params, inputs=None):
        import torch
        import numpy as np
        import random

        model = inputs.get("model")
        ref_audio_input = inputs.get("ref_audio")
        
        if not model: raise ValueError("请连接 Qwen3TTS 模型")
        if not ref_audio_input: raise ValueError("请提供参考音频")

        # 1. 动态加载音频，获取真实的采样率
        ref_wav, real_sr = self._load_audio_safe(ref_audio_input)
        ref_audio_tuple = (ref_wav, real_sr)

        # 2. 参数处理
        ref_text = params.get("ref_text").strip() or None
        lang = params.get("language")
        if lang == "auto": lang = "auto"
        
        # 3. 设置种子
        seed = params.get("seed")
        torch.manual_seed(seed)
        np.random.seed(seed % (2**32))
        random.seed(seed)

        self.logger.info("开始生成克隆语音...")
        try:
            # 调用底层 generate_voice_clone
            wavs, sr = model.generate_voice_clone(
                text=params.get("text"),
                ref_audio=ref_audio_tuple,
                ref_text=ref_text,
                language=lang.lower() if lang else "auto",
                max_new_tokens=params.get("max_tokens"),
                temperature=params.get("temperature"),
                top_p=params.get("top_p"),
                repetition_penalty=1.05
            )
            
            # 4. 编码输出
            import io, scipy.io.wavfile
            full_audio = np.concatenate(wavs)
            # 归一化并防止爆音
            max_val = np.abs(full_audio).max()
            if max_val > 1.0:
                full_audio = full_audio / max_val
            
            audio_int16 = (full_audio * 32767).astype(np.int16)
            buffer = io.BytesIO()
            scipy.io.wavfile.write(buffer, sr, audio_int16)
            return {"output_audio_{{now}}.wav": buffer.getvalue()}

        except Exception as e:
            raise RuntimeError(f"生成失败: {str(e)}")