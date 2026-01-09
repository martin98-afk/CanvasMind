# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py"
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
    name = "EdgeTTS文本转语音"
    category = "语音处理"
    description = "使用微软Edge TTS将文本转换为语音，并保存为本地音频文件"
    requirements = "edge_tts,mutagen"
    inputs = [
        PortDefinition(name="text", label="待转换文本", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output_{{now}}.mp3", label="生成的语音文件路径", type=ArgumentType.FILE),
        PortDefinition(name="audio_length", label="音频时长", type=ArgumentType.FLOAT),
    ]

    properties = {
        "voice_name": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="zh-CN-XiaoxiaoNeural",
            label="语音名称",
            choices=["zh-CN-XiaoxiaoNeural", "zh-CN-YunjianNeural", "zh-CN-XiaoyiNeural", "zh-CN-liaoning-XiaobeiNeural", "zh-CN-shaanxi-XiaoniNeural", "en-US-JennyNeural", "en-US-GuyNeural", "ja-JP-NanamiNeural", "ko-KR-SunHiNeural"]
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        self.logger.info(inputs.text)
        import os
        import asyncio
        import edge_tts
        import uuid
        from pathlib import Path
        from mutagen.mp3 import MP3  # 用于计算MP3时长

        text = inputs.text.encode("utf-8").decode("utf-8")
        voice_name = params.voice_name
        unique_id = uuid.uuid4().hex
        output_path = f"temp_tts_{unique_id}.mp3"

        # 确保输出目录存在
        os.makedirs(
            os.path.dirname(output_path)
            if os.path.dirname(output_path) else ".",
            exist_ok=True
        )
        
        def unescape_and_clean(text):
            import re
            import html
            if not text:
                return ""
            # 1. 处理字面意义上的转义字符
            text = text.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r')
            # 2. HTML 实体转码
            text = html.unescape(text)
            # 3. 移除 Markdown 常见的特殊符号
            text = re.sub(r'[\*\#\_\~\>\`]', '', text)
            # 4. 移除 HTML 标签
            text = re.sub(r"<[^>]+>", "", text)
            # 5. 替换连续的换行符为句号（增加停顿感）
            text = re.sub(r'\n+', '。', text) 
            # 6. 过滤非法字符
            text = re.sub(r"[^\u4e00-\u9fff\u0030-\u0039\u0041-\u005a\u0061-\u007a\u3002\uff0c\uff1f\uff01\uff1a\uff1b\u3001\uff08\uff09\u201c\u201d\.\,\!\?\:\;\(\)]", " ", text)
            # 7. 合并多个空格
            text = re.sub(r"\s+", " ", text).strip()
            return text

        async def _tts():
            communicate = edge_tts.Communicate(unescape_and_clean(text), voice_name)
            await communicate.save(output_path)

        try:
            # 执行合成
            asyncio.run(_tts())
            
            # --- 新增：计算音频时长 ---
            audio = MP3(output_path)
            audio_length = float(audio.info.length)
            # -----------------------

            self.logger.info(f"Edge TTS合成成功，时长: {audio_length:.2f}s，文件已保存至: {output_path}")
            
            with open(output_path, "rb") as f:
                return {
                    "output_{{now}}.mp3": f.read(),
                    "audio_length": audio_length  # 返回时长
                }
        except Exception as e:
            self.logger.error(f"Edge TTS合成过程中发生错误: {str(e)}")
            raise
        finally:
            Path(output_path).unlink(missing_ok=True)