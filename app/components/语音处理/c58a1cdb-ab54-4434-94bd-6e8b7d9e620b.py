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


class Component(BaseComponent):
    name = "higgs-audio"
    category = "语音处理"
    description = ""
    requirements = "descript-audio-codec,torch,transformers>=4.45.1,<4.47.0,librosa,dacite,boto3==1.35.36,s3fs,torchvision,torchaudio,json_repair,pandas,pydantic,vector_quantize_pytorch,loguru,pydub,ruff==0.12.2,omegaconf,click,langid,jieba,accelerate>=0.26.0,boson_multimodal"
    inputs = [
        PortDefinition(name="input1", label="输入1", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output_{now}.mp3", label="输出音频", type=ArgumentType.FILE),
    ]
    properties = {
        "prompt": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="Generate audio following instruction.\n\n<|scene_desc_start|>\nAudio is recorded from a quiet room.\n<|scene_desc_end|>",
            label="提示词",
        ),
    }
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        from boson_multimodal.serve.serve_engine import HiggsAudioServeEngine, HiggsAudioResponse
        from boson_multimodal.data_types import ChatMLSample, Message, AudioContent
        
        import torch
        import torchaudio
        import time
        import click
        
        MODEL_PATH = "bosonai/higgs-audio-v2-generation-3B-base"
        AUDIO_TOKENIZER_PATH = "bosonai/higgs-audio-v2-tokenizer"
        
        system_prompt = (
            params.prompt
        )
        
        messages = [
            Message(
                role="system",
                content=system_prompt,
            ),
            Message(
                role="user",
                content=inputs.input1,
            ),
        ]
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        serve_engine = HiggsAudioServeEngine(MODEL_PATH, AUDIO_TOKENIZER_PATH, device=device)
        
        output: HiggsAudioResponse = serve_engine.generate(
            chat_ml_sample=ChatMLSample(messages=messages),
            max_new_tokens=1024,
            temperature=0.3,
            top_p=0.95,
            top_k=50,
            stop_strings=["<|end_of_text|>", "<|eot_id|>"],
        )
        torchaudio.save(f"output.wav", torch.from_numpy(output.audio)[None, :], output.sampling_rate)
        return {
            "output1": result
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={"prop1": "test"},
        inputs={"input1": "output"},
        node_id="测试模型",
        show_input_types = True,
        show_output_types = True,
        show_execution_time = True,
        global_vars = {}
    )
    print(result)
