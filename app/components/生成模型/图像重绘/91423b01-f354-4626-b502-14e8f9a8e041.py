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
    name = "QWEN ControlNet重绘"
    category = "生成模型/图像重绘"
    description = ""
    requirements = "numpy,torch"
    inputs = [
        PortDefinition(name="pipeline", label="模型管道", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
        PortDefinition(name="image", label="待重绘图像", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
        PortDefinition(name="mask_image", label="图像遮罩", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
        PortDefinition(name="prompt", label="正向提示词", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="negative_prompt", label="逆向提示词", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output_image", label="输出图像", type=ArgumentType.IMAGE),
    ]
    properties = {
        "controlnet_conditioning_scale": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=1.0,
            label="重绘幅度",
        ),
        "steps": PropertyDefinition(
            type=PropertyType.INT,
            default=30,
            label="迭代步数",
        ),
        "true_cfg_scale": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=4.0,
            label="提示词强度",
        ),
        "seed": PropertyDefinition(
            type=PropertyType.INT,
            default=-1,
            label="随机种子",
        ),
    }
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import numpy as np
        import torch
        seed = params.seed
        if seed == -1:
            seed = np.random.randint(2**16)
        image = inputs.image
        mask_image = inputs.mask_image
        pipe = inputs.pipeline
        image = pipe(
            prompt=inputs.prompt,
            negative_prompt=inputs.negative_prompt,
            control_image=image,
            control_mask=mask_image,
            controlnet_conditioning_scale=params.controlnet_conditioning_scale,
            width=image.size[0],
            height=image.size[1],
            num_inference_steps=params.steps,
            true_cfg_scale=params.true_cfg_scale,
            generator=torch.Generator(device="cuda").manual_seed(seed),
        ).images[0]

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
