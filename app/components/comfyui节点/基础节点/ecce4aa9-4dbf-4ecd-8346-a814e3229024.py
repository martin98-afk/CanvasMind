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


class DynamicComponent(BaseComponent):
    name = "VAE编码"
    category = "comfyui节点/基础节点"
    description = "由用户动态生成的组件"
    requirements = ""

    inputs = [
        PortDefinition(name="image", label="image", type=ArgumentType.OBJECT, sub_type="IMAGE", connection=ConnectionType.SINGLE),
        PortDefinition(name="vae", label="vae", type=ArgumentType.OBJECT, sub_type="VAE", connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="latent", label="latent", type=ArgumentType.OBJECT, sub_type="LATENT"),
    ]
    properties = {

    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        vae = inputs.vae
        pixels = inputs.image
        t = vae.encode(pixels)
        return {"latent": {"samples":t}}
