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


class Qwen3TTSVoiceDesign(BaseComponent):
    name = "Qwen3 TTS 声音设计"
    category = "comfyui节点/Qwen-TTS"
    description = "基于提示词创建声音，输出为标准音频文件流"
    # 添加 scipy 用于音频流写入
    requirements = "mediapipe>=0.10.31,modelscope,numpy,tf-keras>=2.18,torch,transparent-background>=1.3.4,scipy"
    
    inputs = [
        PortDefinition(name="model", label="输入模型", type=ArgumentType.OBJECT, sub_type="QWEN3_TTS_MODEL", connection=ConnectionType.SINGLE),
    ]

    # 建议将后缀改为 .wav 以保证文件头与内容匹配，兼容性最好
    # 如果系统强制要求 mp3，可以将下方 .wav 改为 .mp3，但内容实际上是 wav 编码
    outputs = [
        PortDefinition(name="output_audio_{{now}}.wav", label="生成语音", type=ArgumentType.FILE),
    ]

    properties = {
        "text": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="Hello, this is a test.",
            label="文本内容",
        ),
        "prompt": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="A young female voice, energetic and bright.",
            label="声音提示词",
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
        """
        将模型生成的 numpy 列表合并并转换为二进制 WAV 文件流
        """
        import numpy as np
        import io
        import scipy.io.wavfile
        try:
            # 1. 合并音频片段
            full_audio = np.concatenate(outputs)
            
            # 2. 归一化与类型转换 (Float32 -> Int16)
            # Qwen 输出通常在 -1.0 到 1.0 之间，转换为 16位整数以符合标准 WAV 格式
            # 这一步非常重要，否则某些播放器无法播放纯 Float 数据
            audio_int16 = (np.clip(full_audio, -1.0, 1.0) * 32767).astype(np.int16)
            
            # 3. 写入内存流
            buffer = io.BytesIO()
            scipy.io.wavfile.write(buffer, sample_rate, audio_int16)
            
            # 4. 获取二进制数据
            binary_data = buffer.getvalue()
            buffer.close()
            
            return binary_data
        except Exception as e:
            raise RuntimeError(f"音频流编码失败: {str(e)}")

    def run(self, params, inputs=None):
        import torch
        import numpy as np
        import random
        import gc
        model = inputs.get("model")
        if not model:
            raise ValueError("请连接 Qwen3TTS 模型 (输入端口 'model' 为空)")

        # 获取参数
        text = params.get("text")
        instruct = params.get("prompt")
        language = params.get("language")
        seed = params.get("seed")
        max_tokens = params.get("max_tokens")
        auto_unload = params.get("auto_unload")

        if language == "auto":
            language = None
        
        kwargs = {}
        if max_tokens > 0:
            kwargs["max_new_tokens"] = max_tokens

        # 设置随机种子 (确保复现性)
        if seed is not None:
            torch.manual_seed(seed)
            np.random.seed(seed)
            random.seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(seed)

        self.logger.info(f"开始生成语音 (Seed: {seed})...")
        
        try:
            # 执行推理
            outputs, sample_rate = model.generate_voice_design(
                text=text,
                instruct=instruct,
                language=language,
                **kwargs
            )
        except (ValueError, AttributeError) as e:
            # 错误提示优化
            err_msg = str(e)
            if "generate_voice_design" in err_msg:
                raise ValueError("模型功能不匹配: 当前加载的模型不支持 '声音设计(Voice Design)'，请检查是否加载了 'Base' 或 'Custom' 模型。")
            raise e
        finally:
            # 显存清理逻辑
            if auto_unload:
                self.logger.info("正在卸载模型以释放显存...")
                if hasattr(model, "model"):
                    model.model.to("cpu")
                if hasattr(model, "device"):
                    model.device = torch.device("cpu")
                torch.cuda.empty_cache()
                gc.collect()

        # 转换为二进制流
        self.logger.info("正在编码音频流...")
        binary_stream = self._save_to_stream(outputs, sample_rate)
        
        # 返回字典，键名需要与 outputs 中的 PortDefinition 名称匹配
        # {now} 占位符在实际运行时通常由系统处理，但在返回数据时我们直接映射到端口定义的模式
        return {
            "output_audio_{{now}}.wav": binary_stream
        }