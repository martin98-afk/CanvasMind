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


class ComfyVAEDecode(BaseComponent):
    requirements = "torch,numpy,Pillow,comfy"
    name = "VAE解码器"
    category = "comfyui节点/基础节点"
    description = "将潜空间数据解码为可视化图像"
    
    inputs = [
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT, sub_type="VAE", connection=ConnectionType.SINGLE),
        PortDefinition(name="samples", label="待解码潜空间", type=ArgumentType.OBJECT, sub_type="LATENT", connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="images", label="IMAGE", type=ArgumentType.OBJECT, sub_type=""),
    ]
        
    def run(self, params, inputs):
        samples = inputs.samples
        vae = inputs.vae
        latent = samples["samples"]
        if latent.is_nested:
            latent = latent.unbind()[0]

        images = vae.decode(latent)
        if len(images.shape) == 5: #Combine batches
            images = images.reshape(-1, images.shape[-3], images.shape[-2], images.shape[-1])
        return {"images": images}