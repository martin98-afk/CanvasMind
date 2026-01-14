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


class AIImageUpscalerComponent(BaseComponent):
    name = "AI图像超分"
    category = "生成模型"
    description = "使用 Real-ESRGAN 模型对解码后的图像进行 AI 细节增强"
    requirements = "torch,Pillow,numpy,spandrel"

    _upscaler_cache = {}

    inputs = [
        PortDefinition(name="image_in", label="图像输入", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
        PortDefinition(name="model", label="输入模型", type=ArgumentType.FILE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="image_out", label="超分图像", type=ArgumentType.IMAGE),
    ]

    properties = {
        "tile_size": PropertyDefinition(
            type=PropertyType.INT,
            default=512,
            label="切片大小(防止显存溢出)",
        ),
    }

    def run(self, params, inputs=None):
        self._model_cache = {}
        import torch
        import numpy as np
        from PIL import Image
        from spandrel import ModelLoader
        import os

        img = inputs.get("image_in")
        if img is None: return

        model_path = inputs.get("model")
        tile_size = int(params.get("tile_size", 512))

        # 1. 加载模型 (带缓存)
        if model_path not in self._model_cache:
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"未找到模型文件: {model_path}")
            
            self.logger.info(f"正在加载超分模型: {model_path}")
            # spandrel 会自动识别模型架构（不管是 ESRGAN 还是其他）
            loader = ModelLoader()
            model = loader.load_from_file(model_path)
            model = model.to("cuda").eval()
            self._model_cache[model_path] = model
        else:
            model = self._model_cache[model_path]

        # 2. 图像预处理
        # 将 PIL 转为 Tensor [1, C, H, W]
        img_np = np.array(img.convert("RGB")).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).permute(2, 0, 1).unsqueeze(0).to("cuda")

        # 3. 推理 (带切片逻辑以节省显存)
        with torch.no_grad():
            try:
                # 简单的直接推理
                # 如果图片极大，建议在这里实现简单的 tiling 逻辑
                output_tensor = model(img_tensor)
            except RuntimeError as e:
                if "out of memory" in str(e):
                    self.logger.error("显存溢出，请尝试更小的图片或更高级的切片方案")
                raise e

        # 4. 后处理转回 PIL
        output_np = output_tensor.squeeze(0).permute(1, 2, 0).cpu().clamp(0, 1).numpy()
        output_img = Image.fromarray((output_np * 255).astype(np.uint8))

        return {
            "image_out": output_img
        }