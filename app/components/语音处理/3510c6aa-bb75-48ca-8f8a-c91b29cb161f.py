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
    name = "微软TTS文本转语音"
    category = "语音处理"
    description = "使用微软Azure TTS服务将文本转换为语音，并保存为本地音频文件"
    requirements = "azure"
    inputs = [
        PortDefinition(name="text", label="待转换文本", type=ArgumentType.TEXT),
    ]
    outputs = [
        PortDefinition(name="audio_file_path", label="生成的语音文件路径", type=ArgumentType.TEXT),
    ]

    properties = {
        "voice_name": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="zh-CN-XiaoxiaoNeural",
            label="语音名称",
            choices=["zh-CN-XiaoxiaoNeural"]
        ),
        "output_path": PropertyDefinition(
            type=PropertyType.TEXT,
            default="./output_tts.wav",
            label="输出文件路径",
        ),
        "azure_speech_key": PropertyDefinition(
            type=PropertyType.TEXT,
            default="your-subscription-key",
            label="Azure语音服务密钥",
        ),
        "azure_service_region": PropertyDefinition(
            type=PropertyType.TEXT,
            default="eastasia",
            label="Azure服务区域",
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import os
        import azure.cognitiveservices.speech as speechsdk

        # 获取输入和参数
        text = inputs.text
        voice_name = params.voice_name
        output_path = params.output_path
        speech_key = params.azure_speech_key
        service_region = params.azure_service_region

        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

        try:
            # 配置语音服务
            speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
            speech_config.speech_synthesis_voice_name = voice_name

            # 配置音频输出到文件
            audio_config = speechsdk.audio.AudioOutputConfig(filename=output_path)

            # 创建语音合成器
            synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

            # 执行语音合成
            result = synthesizer.speak_text_async(text).get()

            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                self.logger.info(f"语音合成成功，文件已保存至: {output_path}")
                return {"audio_file_path": output_path}
            elif result.reason == speechsdk.ResultReason.Canceled:
                cancellation_details = result.cancellation_details
                error_msg = f"语音合成取消: {cancellation_details.reason}"
                if cancellation_details.reason == speechsdk.CancellationReason.Error:
                    error_msg += f" 错误详情: {cancellation_details.error_details}"
                self.logger.error(error_msg)
                raise RuntimeError(error_msg)
        except Exception as e:
            self.logger.error(f"语音合成过程中发生错误: {str(e)}")
            raise