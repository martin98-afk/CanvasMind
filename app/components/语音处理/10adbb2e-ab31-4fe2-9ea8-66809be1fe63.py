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
    requirements = "edge_tts"
    inputs = [
        PortDefinition(name="text", label="待转换文本", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output_{{now}}.mp3", label="生成的语音文件路径", type=ArgumentType.FILE),
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
        import os
        import asyncio
        import edge_tts

        text = inputs.text
        voice_name = params.voice_name
        output_path = "output.mp3"

        # 确保输出目录存在
        os.makedirs(
            os.path.dirname(output_path)
            if os.path.dirname(output_path) else ".",
            exist_ok=True
        )
        
        def unescape_and_clean(text):
            import re
            import html
            import codecs
            # 1. 将字符串中的 "\\n", "\\t" 等转义序列为真实字符
            text = html.unescape(text)
            # 2. 移除 HTML/XML 标签
            text = re.sub(r"<[^>]+>", "", text)
            # 3. 移除非打印字符（保留基本可读字符）
            text = re.sub(r"[^\x20-\x7E\u4e00-\u9fff\.\,\!\?\:\;\n]", " ", text)
            # 4. 合并多个空白为单个空格
            text = re.sub(r"\s+", " ", text).strip()
            
            text = codecs.decode(text, 'unicode_escape')
            # 2. 将多个换行/空格压缩为合理停顿（可选）
            import re
            text = re.sub(r'\s+', ' ', text).strip()
            return text

        async def _tts():
            communicate = edge_tts.Communicate(unescape_and_clean(text), voice_name)
            await communicate.save(output_path)

        try:
            asyncio.run(_tts())
            self.logger.info(f"Edge TTS合成成功，文件已保存至: {output_path}")
            with open(output_path, "rb") as f:
                return {"output_{{now}}.mp3": f.read()}
        except Exception as e:
            self.logger.error(f"Edge TTS合成过程中发生错误: {str(e)}")
            raise