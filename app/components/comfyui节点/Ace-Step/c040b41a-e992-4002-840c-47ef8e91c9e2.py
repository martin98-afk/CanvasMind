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
    name = "空音频潜空间"
    category = "comfyui节点/Ace-Step"
    description = ""
    requirements = "#comfy,torch"
    inputs = [
    ]
    outputs = [
        PortDefinition(name="latent", label="潜空间", type=ArgumentType.OBJECT, sub_type="LATENT"),
    ]
    properties = {
        "seconds": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=120.0,
            label="音频秒数",
        ),
        "batch_size": PropertyDefinition(
            type=PropertyType.INT,
            default=1,
            label="批量数",
            description="The number of latent images in the batch.",
        ),
    }
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import comfy
        import torch
        seconds = params.seconds
        batch_size = params.batch_size
        length = int(seconds * 44100 / 512 / 8)
        latent = torch.zeros([batch_size, 8, 16, length], device=comfy.model_management.intermediate_device())
        return {
            "latent": {"samples": latent}
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
