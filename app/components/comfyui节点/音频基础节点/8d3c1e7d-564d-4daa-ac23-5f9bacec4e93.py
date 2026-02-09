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


class AudioLoad(BaseComponent):
    name = "音频加载"
    category = "comfyui节点/音频基础节点"
    description = "从本地文件加载音频（支持wav/mp3/flac/ogg等格式），自动处理采样率和声道"
    requirements = "torchaudio,soundfile,torch,numpy"
    inputs = [
    ]
    outputs = [
        PortDefinition(name="audio", label="音频对象", type=ArgumentType.OBJECT, sub_type="AUDIO"),
    ]
    properties = {
        "file_path": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="音频文件路径",
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import os
        import torch
        
        file_path = params.file_path.strip()
        if not file_path:
            raise ValueError("音频文件路径不能为空")
        
        # 支持相对路径（相对于当前工作目录）
        if not os.path.isabs(file_path):
            file_path = os.path.join(os.getcwd(), file_path)
        
        if not os.path.exists(file_path):
            # 尝试在标准输入目录查找
            input_dirs = [
                os.path.join(os.getcwd(), "input"),
                os.path.join(os.getcwd(), "input", "audio"),
                os.path.join(os.getcwd(), "output"),  # 有时用户会从输出目录加载
            ]
            for base_dir in input_dirs:
                candidate = os.path.join(base_dir, file_path)
                if os.path.exists(candidate):
                    file_path = candidate
                    break
            else:
                raise FileNotFoundError(f"音频文件不存在: {file_path}")
        
        self.logger.info(f"正在加载音频: {file_path}")
        
        # 优先使用 torchaudio（支持格式多）
        waveform = None
        sample_rate = None
        load_method = "torchaudio"
        
        try:
            import torchaudio
            # torchaudio 2.0+ 需要设置 backend（避免 av 依赖）
            try:
                torchaudio.set_audio_backend("soundfile")  # 优先使用 soundfile backend
            except:
                pass
            
            waveform, sample_rate = torchaudio.load(file_path, normalize=True)
            load_method = "torchaudio"
        except Exception as e1:
            self.logger.warning(f"torchaudio加载失败，尝试soundfile: {e1}")
            try:
                import soundfile as sf
                import numpy as np
                audio_data, sample_rate = sf.read(file_path, dtype='float32')
                # 转换为 torch.Tensor: [T, C] -> [C, T]
                if audio_data.ndim == 1:
                    audio_data = audio_data[:, np.newaxis]  # 单声道转为 [T, 1]
                waveform = torch.from_numpy(audio_data.T)  # 转置为 [C, T]
                load_method = "soundfile"
            except Exception as e2:
                raise RuntimeError(
                    f"音频加载失败（torchaudio: {e1}；soundfile: {e2}）。"
                    f"请确保文件格式有效（支持wav/mp3/flac/ogg）且已安装soundfile。"
                )
        
        # 验证加载结果
        if waveform is None or sample_rate is None:
            raise RuntimeError("音频加载返回空数据")
        
        # 确保 waveform 为 float32
        if waveform.dtype != torch.float32:
            waveform = waveform.float()
        
        # 添加 batch 维度 [C, T] -> [1, C, T]
        if waveform.ndim == 2:
            waveform = waveform.unsqueeze(0)
        elif waveform.ndim != 3:
            raise ValueError(f"不支持的音频维度: {waveform.ndim}")
        
        # 标准化到 [-1, 1] 范围（torchaudio.load(normalize=True) 已处理，此处双重保险）
        max_val = waveform.abs().max()
        if max_val > 1.0:
            waveform = waveform / max_val
        
        self.logger.info(
            f"✓ 音频加载成功 ({load_method}) | "
            f"采样率: {sample_rate}Hz | "
            f"时长: {waveform.shape[2] / sample_rate:.2f}s | "
            f"声道: {waveform.shape[1]} | "
            f"形状: {list(waveform.shape)}"
        )
        
        return {
            "audio": {
                "waveform": waveform,
                "sample_rate": int(sample_rate)
            }
        }