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
    name = "空潜空间生成"
    category = "生成模型"
    description = ""
    requirements = "numpy"
    inputs = [
    ]
    outputs = [
        PortDefinition(name="latent_out", label="潜空间输出", type=ArgumentType.ARRAY),
    ]
    properties = {
        "wid": PropertyDefinition(
            type=PropertyType.INT,
            default=512,
            label="宽",
        ),
        "hei": PropertyDefinition(
            type=PropertyType.INT,
            default=512,
            label="高",
        ),
    }
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import numpy as np
        w, h = params.get("wid"), params.get("hei")
        # Stable Diffusion 的 Latent 通道数固定为 4，尺寸是原图的 1/8
        shape = (1, 4, h // 8, w // 8)
        # 生成随机噪声
        latent_array = np.random.randn(*shape).astype(np.float16)
        return {"latent_out": latent_array}


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
