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
    name = "LTX2空音频潜空间"
    category = "comfyui节点/LTX模型适配"
    description = ""
    requirements = "numpy,comfy,torch"
    inputs = [
        PortDefinition(name="audio_vae", label="音频编码器", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="audio_latent", label="音频潜空间", type=ArgumentType.OBJECT),
    ]
    properties = {
        "frames_number": PropertyDefinition(
            type=PropertyType.INT,
            default=91,
            label="帧数",
        ),
        "frame_rate": PropertyDefinition(
            type=PropertyType.INT,
            default=25,
            label="帧率",
        ),
        "batch_size": PropertyDefinition(
            type=PropertyType.INT,
            default=1,
            label="批次量",
        ),
    }
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import torch
        import comfy.model_management
        audio_vae = inputs.audio_vae
        frames_number = params.frames_number
        frame_rate = params.frame_rate
        batch_size = params.batch_size
        
        z_channels = audio_vae.latent_channels
        audio_freq = audio_vae.latent_frequency_bins
        sampling_rate = int(audio_vae.sample_rate)

        num_audio_latents = audio_vae.num_of_latents_from_frames(frames_number, frame_rate)

        audio_latents = torch.zeros(
            (batch_size, z_channels, num_audio_latents, audio_freq),
            device=comfy.model_management.intermediate_device(),
        )
        return {
            "audio_latent": {
                "samples": audio_latents,
                "sample_rate": sampling_rate,
                "type": "audio",
            }
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
