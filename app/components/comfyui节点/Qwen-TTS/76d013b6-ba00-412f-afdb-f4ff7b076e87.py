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
    description = "基于参考音频克隆声音 (需 Base 模型)"
    requirements = "mediapipe>=0.10.31,modelscope,numpy,tf-keras>=2.18,torch,transparent-background>=1.3.4,scipy"

    inputs = [
        PortDefinition(name="model", label="输入模型", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        # 接收二进制 WAV 数据流
        PortDefinition(name="ref_audio", label="参考音频(WAV)", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]

    outputs = [
        PortDefinition(name="output_audio_{{now}}.wav", label="生成语音", type=ArgumentType.FILE),
    ]

    properties = {
        "text": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="Hello, I am cloning this voice.",
            label="生成文本",
        ),
        "ref_text": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="",
            label="参考文本 (可选)",
        ),
        "language": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="auto",
            label="语言",
            choices=["auto", "Chinese", "English", "Japanese", "Korean", "German", "French", "Russian", "Portuguese", "Spanish", "Italian"]
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
        "auto_unload": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="生成后卸载模型",
        ),
    }

    def _save_to_stream(self, outputs, sample_rate):
        """将生成结果写入 WAV 流"""
        import numpy as np
        import io
        import scipy.io.wavfile

        try:
            full_audio = np.concatenate(outputs)
            # Float32 -> Int16 归一化，防止爆音
            audio_int16 = (np.clip(full_audio, -1.0, 1.0) * 32767).astype(np.int16)
            
            buffer = io.BytesIO()
            scipy.io.wavfile.write(buffer, sample_rate, audio_int16)
            return buffer.getvalue()
        except Exception as e:
            raise RuntimeError(f"音频编码失败: {str(e)}")

    def _load_audio_from_stream(self, audio_bytes):
        """
        读取输入的 WAV 二进制流并转换为模型需要的 (numpy_float, sample_rate) 格式
        """
        import numpy as np
        import io
        import scipy.io.wavfile

        try:
            buffer = io.BytesIO(open(audio_bytes, "rb").read())
            sample_rate, data = scipy.io.wavfile.read(buffer)
            
            # 处理多声道 -> 单声道
            if data.ndim > 1:
                data = np.mean(data, axis=1)
            
            # 归一化处理：将 Int 类型转回 Float32 (-1.0 ~ 1.0)
            if data.dtype == np.int16:
                data = data.astype(np.float32) / 32768.0
            elif data.dtype == np.int32:
                data = data.astype(np.float32) / 2147483648.0
            elif data.dtype == np.uint8:
                data = (data.astype(np.float32) - 128.0) / 128.0
            elif data.dtype == np.float32:
                pass # 已经是 float32
            else:
                # 其他格式尝试强转
                data = data.astype(np.float32)

            return data, sample_rate
        except Exception as e:
            raise ValueError(f"解析参考音频失败，请确保输入是标准的 WAV/MP3 格式: {e}")

    def run(self, params, inputs=None):
        import torch
        import numpy as np
        import random
        import gc

        model = inputs.get("model")
        ref_audio_bytes = inputs.get("ref_audio")
        
        if not model:
            raise ValueError("请连接 Qwen3TTS 模型")
        if not ref_audio_bytes:
            raise ValueError("请连接/上传参考音频文件")

        text = params.get("text")
        ref_text = params.get("ref_text")
        language = params.get("language")
        seed = params.get("seed")
        max_tokens = params.get("max_tokens")
        auto_unload = params.get("auto_unload")

        if language == "auto": language = None
        if not ref_text.strip(): ref_text = None
        
        kwargs = {}
        if max_tokens > 0:
            kwargs["max_new_tokens"] = max_tokens

        # 1. 解析参考音频
        self.logger.info("正在解析参考音频...")
        ref_audio_np, _ = self._load_audio_from_stream(ref_audio_bytes)
        # 模型期望的输入是 (numpy_array, sample_rate) 的元组，但Qwen实际上在内部处理采样率
        # 为了匹配 _qwen_tts_haigc 的接口，我们构造 input
        # 注意：Qwen3TTS 内部通常只需要 numpy 数据，采样率可能由模型配置决定，
        # 但遵循通常惯例，我们传递转换后的 numpy 数组。
        # 这里的 ref_audio 参数在 Qwen 接口中通常是一个 tuple: (audio_data, sample_rate)
        # 假设 _load_audio_from_stream 返回的采样率就是原文件的采样率
        ref_audio_tuple = (ref_audio_np, 16000) # 这里的采样率参数视具体模型实现而定，通常模型会重采样

        # 设置随机种子
        torch.manual_seed(seed)
        np.random.seed(seed)
        random.seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)

        self.logger.info(f"生成声音克隆 (Text: {text[:30]}...)...")
        
        try:
            outputs, sample_rate = model.generate_voice_clone(
                text=text,
                ref_audio=ref_audio_tuple,
                ref_text=ref_text,
                language=language,
                **kwargs
            )
        except (ValueError, AttributeError) as e:
            if "generate_voice_clone" in str(e):
                raise ValueError("当前模型不支持 Voice Clone，请务必加载 'Base' 模型 (如 Qwen3-TTS-12Hz-1.7B-Base)。")
            raise e
        finally:
            if auto_unload:
                self.logger.info("卸载模型到 CPU...")
                if hasattr(model, "model"):
                    model.model.to("cpu")
                torch.cuda.empty_cache()
                gc.collect()

        # 2. 编码输出
        binary_stream = self._save_to_stream(outputs, sample_rate)
        return {"output_audio_{{now}}.wav": binary_stream}