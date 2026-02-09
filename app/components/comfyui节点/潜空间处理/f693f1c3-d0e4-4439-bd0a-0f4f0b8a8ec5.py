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
    name = "潜空间色调映射Reinhard"
    category = "comfyui节点/潜空间处理"
    description = "应用Reinhard色调映射压缩潜空间动态范围，防止过曝"
    requirements = "torch"
    inputs = [
    ]
    outputs = [
        PortDefinition(name="latent_operation", label="潜空间操作", type=ArgumentType.OBJECT),
    ]
    properties = {
        "multiplier": PropertyDefinition(
            type=PropertyType.RANGE,
            default="1.00",
            label="乘数",
            min=0.0,
            max=100.0,
            step=0.01,
        ),
    }
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import torch
        multiplier = params.multiplier
        def tonemap_reinhard(latent, **kwargs):
            latent_vector_magnitude = (torch.linalg.vector_norm(latent, dim=(1)) + 0.0000000001)[:,None]
            normalized_latent = latent / latent_vector_magnitude
        
            mean = torch.mean(latent_vector_magnitude, dim=(1,2,3), keepdim=True)
            std = torch.std(latent_vector_magnitude, dim=(1,2,3), keepdim=True)
        
            top = (std * 5 + mean) * multiplier
        
            #reinhard
            latent_vector_magnitude *= (1.0 / top)
            new_magnitude = latent_vector_magnitude / (latent_vector_magnitude + 1.0)
            new_magnitude *= top
        
            return normalized_latent * new_magnitude
        return {
            "latent_operation": tonemap_reinhard
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
