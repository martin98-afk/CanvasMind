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


class AudioTrim(BaseComponent):
    name = "音频裁剪"
    category = "comfyui节点/音频基础节点"
    description = "按起始时间和时长裁剪音频片段，支持负数起始时间（从末尾倒数）"
    requirements = "torch"
    inputs = [
        PortDefinition(name="audio", label="音频对象", type=ArgumentType.OBJECT, sub_type="AUDIO", connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="audio", label="裁剪后音频", type=ArgumentType.OBJECT, sub_type="AUDIO"),
    ]
    properties = {
        "start_seconds": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.0,
            label="起始时间(秒)",
            description="负数表示从末尾倒数，如-5.0表示最后5秒",
        ),
        "duration": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=10.0,
            label="持续时间(秒)",
            description="裁剪片段的长度",
        ),
    }

    def run(self, params, inputs=None):
        import torch
        
        audio = inputs.audio
        if audio is None:
            raise ValueError("音频输入不能为空")
        
        waveform = audio.get("waveform")
        sample_rate = audio.get("sample_rate", 44100)
        
        if waveform is None:
            raise ValueError("音频对象缺少waveform字段")
        
        # 转换为 float32
        if waveform.dtype != torch.float32:
            waveform = waveform.float()
        
        # 计算帧索引
        audio_length = waveform.shape[-1]
        start_seconds = float(params.start_seconds)
        duration = float(params.duration)
        
        if start_seconds < 0:
            # 负数：从末尾倒数
            start_frame = audio_length + int(round(start_seconds * sample_rate))
        else:
            start_frame = int(round(start_seconds * sample_rate))
        
        start_frame = max(0, min(start_frame, audio_length - 1))
        end_frame = start_frame + int(round(duration * sample_rate))
        end_frame = max(0, min(end_frame, audio_length))
        
        if start_frame >= end_frame:
            raise ValueError(
                f"裁剪范围无效: 起始帧{start_frame} >= 结束帧{end_frame} "
                f"(总长度{audio_length}帧，采样率{sample_rate}Hz)"
            )
        
        trimmed_waveform = waveform[..., start_frame:end_frame]
        
        self.logger.info(
            f"✓ 音频裁剪成功 | 原始: {audio_length/sample_rate:.2f}s → "
            f"裁剪后: {trimmed_waveform.shape[-1]/sample_rate:.2f}s | "
            f"范围: {start_seconds}s ~ {start_seconds+duration:.2f}s"
        )
        
        return {
            "audio": {
                "waveform": trimmed_waveform,
                "sample_rate": int(sample_rate)
            }
        }

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = AudioTrim()
    try:
        import torch
        mock_audio = {
            "waveform": torch.randn(1, 2, 44100 * 30),  # 30秒立体声
            "sample_rate": 44100
        }
    except:
        mock_audio = None
    
    result = model.debug(
        params={
            "start_seconds": "5.0",
            "duration": "10.0"
        },
        inputs={"audio": mock_audio},
        global_vars={},
        node_id="test_audio_trim",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True
    )
    print("✅ 裁剪成功，新时长:", result["audio"]["waveform"].shape[2] / 44100, "秒")