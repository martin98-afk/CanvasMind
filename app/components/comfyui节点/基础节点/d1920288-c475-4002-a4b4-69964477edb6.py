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


class ComfyVAEEncodeForInpaint(BaseComponent):
    requirements = "torch,#comfy,#nodes"
    name = "局部重绘编码"
    category = "comfyui节点/基础节点"
    description = "用于局部重绘的 VAE 编码，处理 Mask 边缘"

    inputs = [
        PortDefinition(name="pixels", label="图像(IMAGE)", type=ArgumentType.OBJECT, sub_type="IMAGE", connection=ConnectionType.SINGLE),
        PortDefinition(name="mask", label="遮罩(MASK)", type=ArgumentType.OBJECT, sub_type="MASK", connection=ConnectionType.SINGLE),
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT, sub_type="VAE", connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="latent", label="LATENT", type=ArgumentType.OBJECT, sub_type="LATENT"),
    ]

    properties = {
        "grow_mask_by": PropertyDefinition(
            type=PropertyType.INT,
            default=6,
            label="遮罩羽化扩张(像素)",
        ),
    }

    def ensure_comfy_exist(self):
        import os, sys
        path = self.global_variable.comfy_extension
        if path not in sys.path:
            sys.path.append(path)
        os.chdir(path)

    def run(self, params, inputs):
        self.ensure_comfy_exist()
        import nodes
        
        pixels = inputs.get("pixels")
        vae = inputs.get("vae")
        mask = inputs.get("mask")
        grow_by = int(params.get("grow_mask_by", 6))

        encoder = nodes.VAEEncodeForInpaint()
        # encode 返回 (latent_dict, )
        # 注意：这个 latent 内部包含了 noise_mask，传给 KSampler 时会自动识别为 Inpaint 模式
        latent = encoder.encode(vae, pixels, mask, grow_by)[0]

        return {
            "latent": latent
        }