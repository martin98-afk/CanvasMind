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


class ComfyLatentUpscale(BaseComponent):
    requirements = "torch,# comfy,# nodes"
    name = "潜空间缩放"
    category = "comfyui节点/潜空间处理"
    description = "直接缩放 Latent 尺寸 (常用于 Hires Fix)"

    inputs = [
        PortDefinition(name="samples", label="LATENT", type=ArgumentType.OBJECT, sub_type="LATENT", connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="latent", label="LATENT", type=ArgumentType.OBJECT, sub_type="LATENT"),
    ]

    properties = {
        "upscale_method": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="nearest-exact",
            label="缩放算法",
            choices=["nearest-exact", "bilinear", "area", "bicubic", "bislerp"]
        ),
        "widt": PropertyDefinition(
            type=PropertyType.INT,
            default=1024,
            label="目标宽度",
        ),
        "heigh": PropertyDefinition(
            type=PropertyType.INT,
            default=1024,
            label="目标高度",
        ),
        "crop": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="disabled",
            label="裁剪方式",
            choices=["disabled", "center"]
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
        
        samples = inputs.get("samples")
        method = params.get("upscale_method", "nearest-exact")
        width = int(params.get("widt", 1024))
        height = int(params.get("heigh", 1024))
        crop = params.get("crop", "disabled")

        upscaler = nodes.LatentUpscale()
        latent = upscaler.upscale(samples, method, width, height, crop)[0]

        return {
            "latent": latent
        }