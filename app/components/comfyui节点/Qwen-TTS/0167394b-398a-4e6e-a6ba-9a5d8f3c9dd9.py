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


class Qwen3TTSCustomVoice(BaseComponent):
    name = "Qwen3 TTS 自定义声音"
    category = "comfyui节点/Qwen-TTS"
    description = "使用预设说话人ID生成 (需 CustomVoice 模型)"
    requirements = "mediapipe>=0.10.31,modelscope,numpy,tf-keras>=2.18,torch,transparent-background>=1.3.4,scipy"

    inputs = [
        PortDefinition(name="model", label="输入模型", type=ArgumentType.OBJECT, sub_type="QWEN3_TTS_MODEL", connection=ConnectionType.SINGLE),
    ]

    outputs = [
        PortDefinition(name="output_audio_{{now}}.wav", label="生成语音", type=ArgumentType.FILE),
    ]

    # 预设数据硬编码在组件内
    SPEAKER_PRESETS = {
        "Vivian": "Bright, slightly edgy young female voice.",
        "Serena": "Warm, gentle young female voice.",
        "Uncle_Fu": "Seasoned male voice with a low, mellow timbre.",
        "Dylan": "Youthful Beijing male voice with a clear, natural timbre.",
        "Eric": "Lively Chengdu male voice with a slightly husky brightness.",
        "Ryan": "Dynamic male voice with strong rhythmic drive.",
        "Aiden": "Sunny American male voice with a clear midrange.",
        "Ono_Anna": "Playful Japanese female voice with a light, nimble timbre.",
        "Sohee": "Warm Korean female voice with rich emotion.",
    }

    properties = {
        "text": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="Hello, this is a custom voice test.",
            label="文本内容",
        ),
        "speaker": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="Vivian",
            label="预设说话人",
            choices=["Vivian", "Serena", "Uncle_Fu", "Dylan", "Eric", "Ryan", "Aiden", "Ono_Anna", "Sohee"]
        ),
        "prompt": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="",
            label="补充提示词 (可选)",
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
            # Float32 -> Int16 归一化
            audio_int16 = (np.clip(full_audio, -1.0, 1.0) * 32767).astype(np.int16)
            
            buffer = io.BytesIO()
            scipy.io.wavfile.write(buffer, sample_rate, audio_int16)
            return buffer.getvalue()
        except Exception as e:
            raise RuntimeError(f"音频编码失败: {str(e)}")

    def run(self, params, inputs=None):
        import torch
        import numpy as np
        import random
        import gc

        model = inputs.get("model")
        if not model:
            raise ValueError("请连接 Qwen3TTS 模型")

        text = params.get("text")
        speaker = params.get("speaker")
        user_instruct = params.get("prompt")
        language = params.get("language")
        seed = params.get("seed")
        max_tokens = params.get("max_tokens")
        auto_unload = params.get("auto_unload")

        if language == "auto": language = None
        kwargs = {}
        if max_tokens > 0:
            kwargs["max_new_tokens"] = max_tokens

        # 处理提示词逻辑：优先使用用户输入，否则使用预设字典
        instruct = user_instruct.strip()
        if not instruct and speaker in self.SPEAKER_PRESETS:
            instruct = self.SPEAKER_PRESETS[speaker]
            self.logger.info(f"使用预设提示词: {instruct}")
        
        # 即使为空也传 None，让模型处理
        if not instruct: instruct = None

        # 设置随机种子
        torch.manual_seed(seed)
        np.random.seed(seed)
        random.seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)

        self.logger.info(f"生成自定义声音: {speaker}...")
        
        try:
            outputs, sample_rate = model.generate_custom_voice(
                text=text,
                speaker=speaker,
                instruct=instruct,
                language=language,
                **kwargs
            )
        except (ValueError, AttributeError) as e:
            if "generate_custom_voice" in str(e):
                raise ValueError("当前模型不支持 Custom Voice，请务必加载 'CustomVoice' 模型 (如 Qwen3-TTS-12Hz-1.7B-CustomVoice)。")
            raise e
        finally:
            if auto_unload:
                self.logger.info("卸载模型到 CPU...")
                if hasattr(model, "model"):
                    model.model.to("cpu")
                torch.cuda.empty_cache()
                gc.collect()

        # 编码输出
        binary_stream = self._save_to_stream(outputs, sample_rate)
        return {"output_audio_{{now}}.wav": binary_stream}