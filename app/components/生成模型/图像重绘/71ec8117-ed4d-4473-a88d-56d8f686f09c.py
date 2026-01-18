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
    name = "QWEN ControlNet 加载器"
    category = "生成模型/图像重绘"
    description = ""
    requirements = "numpy,torch,diffusers"
    inputs = [
    ]
    outputs = [
        PortDefinition(name="pipeline", label="重绘管道", type=ArgumentType.OBJECT),
    ]
    properties = {
        "base_model": PropertyDefinition(
            type=PropertyType.FILE,
            default="safetensors",
            label="基础图像模型",
        ),
        "inpaint_model": PropertyDefinition(
            type=PropertyType.FILE,
            default="safetensors",
            label="重绘模型",
        ),
    }
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import torch
        from diffusers import QwenImageControlNetModel, QwenImageControlNetInpaintPipeline

        base_model = params.base_model
        controlnet_model = params.inpaint_model
        
        controlnet = QwenImageControlNetModel.from_pretrained(controlnet_model, torch_dtype=torch.bfloat16)
        
        pipe = QwenImageControlNetInpaintPipeline.from_pretrained(
            base_model, controlnet=controlnet, torch_dtype=torch.bfloat16
        )
        pipe.to("cuda")

        return {
            "pipeline": pipe
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
