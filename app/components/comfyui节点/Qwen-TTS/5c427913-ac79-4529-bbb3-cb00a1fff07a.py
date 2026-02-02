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


class Qwen3TTSDialogueInference(BaseComponent):
    name = "Qwen3 TTS 多角色对话"
    category = "comfyui节点/Qwen-TTS"
    description = "执行多角色脚本，生成带停顿控制的连续对话语音 (需 Base 模型)"
    requirements = "numpy,torch,scipy"

    inputs = [
        PortDefinition(name="model", label="输入模型", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="role_bank", label="角色库(RoleBank)", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
    ]

    outputs = [
        PortDefinition(name="dialogue_output_{{now}}.wav", label="生成对话语音", type=ArgumentType.FILE),
    ]

    properties = {
        "script": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="角色A: 你好，今天天气不错。角色B: 是的，很适合散步。",
            label="对话剧本 (格式: 角色名: 文本)",
        ),
        "pause_linebreak": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.5,
            label="行间停顿(秒)",
        ),
        "period_pause": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.4,
            label="句号停顿(秒)",
        ),
        "comma_pause": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.2,
            label="逗号停顿(秒)",
        ),
        "batch_size": PropertyDefinition(
            type=PropertyType.INT,
            default=4,
            label="并行处理行数(显存大调高)",
        ),
        "language": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="auto",
            label="默认语言",
            choices=["auto", "Chinese", "English", "Japanese", "Korean"]
        ),
        "seed": PropertyDefinition(
            type=PropertyType.INT,
            default=0,
            label="随机种子",
        ),
    }

    def run(self, params, inputs=None):
        import re
        import torch
        import numpy as np
        import io
        import scipy.io.wavfile
        import random

        model = inputs.get("model")
        role_bank = inputs.get("role_bank") # 这是一个字典 { "角色名": prompt_data }
        
        if not model: raise ValueError("请连接 Qwen3TTS 模型")
        if not role_bank: raise ValueError("请连接角色库(Role Bank)")

        script = params.get("script")
        pause_lb = params.get("pause_linebreak")
        p_pause = params.get("period_pause")
        c_pause = params.get("comma_pause")
        batch_size = params.get("batch_size")
        
        # 设置随机种子
        seed = params.get("seed")
        torch.manual_seed(seed)
        np.random.seed(seed % (2**32))

        # 1. 解析剧本
        lines = script.strip().split("\n")
        texts_to_gen = []
        prompts_to_gen = []
        pauses_to_gen = [] # 记录每一段之后的停顿时间

        self.logger.info("正在解析剧本和处理停顿标记...")
        
        for line in lines:
            line = line.strip()
            if not line or (":" not in line and "：" not in line):
                continue

            # 分割角色和内容
            if ":" in line:
                role_name, text = line.split(":", 1)
            else:
                role_name, text = line.split("：", 1)

            role_name = role_name.strip()
            text = text.strip()

            if role_name not in role_bank:
                self.logger.warning(f"跳过未定义角色: {role_name}")
                continue

            # 处理停顿符号（参考源码正则）
            if p_pause > 0:
                text = re.sub(r'\.(?!\d)', f'. [break={p_pause}]', text)
                text = re.sub(r'。', f'。 [break={p_pause}]', text)
            if c_pause > 0:
                text = re.sub(r',(?!\d)', f', [break={c_pause}]', text)
                text = re.sub(r'，', f'， [break={c_pause}]', text)

            # 拆分带有 [break=X] 的文本
            parts = re.split(r'\[break=([\d\.]+)\]', text)
            
            current_prompt = role_bank[role_name]

            for i in range(0, len(parts), 2):
                segment_text = parts[i].strip()
                if not segment_text: continue

                current_seg_pause = 0.0
                if i + 1 < len(parts):
                    try:
                        current_seg_pause = float(parts[i+1])
                    except: pass

                texts_to_gen.append(segment_text)
                prompts_to_gen.append(current_prompt)
                pauses_to_gen.append(current_seg_pause)

            # 行末增加行间停顿
            if pauses_to_gen:
                pauses_to_gen[-1] += pause_lb

        if not texts_to_gen:
            raise ValueError("剧本解析失败，请检查格式是否为 '角色名: 文本'")

        # 2. 分批次进行推理
        self.logger.info(f"开始推理，共 {len(texts_to_gen)} 个文本段...")
        results_audio = []
        sample_rate = 24000 # 默认采样率

        try:
            for i in range(0, len(texts_to_gen), batch_size):
                chunk_texts = texts_to_gen[i : i + batch_size]
                chunk_prompts = prompts_to_gen[i : i + batch_size]
                
                # 调用底层的批量生成接口
                wavs, sr = model.generate_voice_clone(
                    text=chunk_texts,
                    voice_clone_prompt=chunk_prompts,
                    language=params.get("language").lower(),
                    repetition_penalty=1.05,
                    temperature=1.0
                )
                sample_rate = sr

                for j, wav in enumerate(wavs):
                    results_audio.append(wav)
                    # 插入静音段
                    pause_time = pauses_to_gen[i + j]
                    if pause_time > 0:
                        silence_len = int(pause_time * sample_rate)
                        silence = np.zeros(silence_len, dtype=np.float32)
                        results_audio.append(silence)

            # 3. 合并音频并导出
            full_audio = np.concatenate(results_audio)
            
            # 归一化处理
            max_val = np.abs(full_audio).max()
            if max_val > 0:
                full_audio = full_audio / max_val
            
            audio_int16 = (full_audio * 32767).astype(np.int16)
            buffer = io.BytesIO()
            scipy.io.wavfile.write(buffer, sample_rate, audio_int16)
            
            return {"dialogue_output_{{now}}.wav": buffer.getvalue()}

        except Exception as e:
            raise RuntimeError(f"对话合成失败: {e}")