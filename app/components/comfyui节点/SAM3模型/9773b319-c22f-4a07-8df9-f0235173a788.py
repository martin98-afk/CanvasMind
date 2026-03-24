# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path

base_path = (
    Path(__file__).parent.parent / "base.py"
    if (Path(__file__).parent.parent / "base.py").exists()
    else Path(__file__).parent.parent.parent / "base.py"
)
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


class ComfySAM3Segmenter(BaseComponent):
    name = "SAM3统一分割器"
    category = "comfyui节点/SAM3模型"
    description = "集成了SAM3的文本描述分割(Grounding)和点击互动分割(Segmentation)功能"
    requirements = "Pillow,comfy-env>0.0.1,comfy-test>0.0.1,# comfyui-sam3,einops>=0.6.0,ftfy==6.1.1,huggingface_hub,iopath>=0.1.10,# nodes,numpy>=1.26,opencv-python>=4.8.0,psutil>=5.9.0,pycocotools>=2.0.6,regex,safetensors>=0.4.0,scikit-image>=0.19.0,timm>=1.0.17,tqdm,typing_extensions,# sam3_nodes,torch"
    inputs = [
        PortDefinition(
            name="image",
            label="输入图片",
            type=ArgumentType.IMAGE,
            connection=ConnectionType.SINGLE,
        ),
        PortDefinition(
            name="sam3_model",
            label="sam3模型",
            type=ArgumentType.OBJECT,
            sub_type="",
            connection=ConnectionType.SINGLE,
        ),
    ]
    outputs = [
        PortDefinition(name="mask", label="MASK", type=ArgumentType.IMAGE),
        PortDefinition(name="image", label="IMAGE", type=ArgumentType.IMAGE),
        PortDefinition(name="json_boxes", label="BOXES (JSON)", type=ArgumentType.JSON),
        PortDefinition(
            name="polygons", label="POLYGONS (JSON)", type=ArgumentType.JSON
        ),
    ]

    properties = {
        "mode": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="Text Grounding",
            label="工作模式",
            choices=["Text Grounding", "Interactive (Points/Box)"],
        ),
        "text_prompt": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="",
            label="文本提示词 (Grounding)",
        ),
        "confidence": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.2,
            label="置信度阈值",
        ),
        "multimask": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="多重掩码 (Multimask)",
        ),
        "mask_display_mode": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="Polygon",
            label="Mask显示模式",
            choices=["Pixel", "Polygon"],
        ),
    }

    def tensor_to_pil(self, tensor, is_mask=False):
        """
        辅助函数：将 ComfyUI 的 Tensor 转换为 PIL Image
        """
        import torch
        import numpy as np
        from PIL import Image

        if tensor is None:
            return None

        # 1. 如果已经是 PIL，直接返回
        if isinstance(tensor, Image.Image):
            return tensor

        # 2. 移动到 CPU 并转为 Numpy
        if isinstance(tensor, torch.Tensor):
            image_np = tensor.cpu().detach().numpy()
        else:
            image_np = np.array(tensor)

        # 3. 处理维度
        # ComfyUI Mask 通常是 [Batch, H, W] -> 需要变为 [H, W]
        # ComfyUI Image 通常是 [Batch, H, W, C] -> 需要变为 [H, W, C]
        if image_np.ndim == 4:  # [B, H, W, C]
            image_np = image_np[0]
        elif image_np.ndim == 3:  # [B, H, W] (Mask) 或 [H, W, C]
            if is_mask:
                # Mask [B, H, W] 取第一个 batch
                image_np = image_np[0]
            # 如果不是 Mask 且是 3维，通常无需处理，除非是 [C, H, W] 但 ComfyUI 默认是 [H,W,C]

        # 4. 转换数值范围并创建 PIL
        if is_mask:
            # Mask 通常是 0.0-1.0 的 float，需要转换为 0-255 的 uint8
            # 模式 'L' (灰度)
            return Image.fromarray((image_np * 255).astype(np.uint8), mode="L")
        else:
            # Image 通常是 0.0-1.0 的 float，需要转换为 0-255 的 uint8
            # 模式 'RGB'
            return Image.fromarray((image_np * 255).astype(np.uint8), mode="RGB")

    def tensor_to_base64(self, tensor, is_mask=False):
        """将 ComfyUI 的 Tensor 转换为 base64 编码的图片"""
        import base64
        from io import BytesIO

        pil_image = self.tensor_to_pil(tensor, is_mask=is_mask)
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{img_str}"

    def mask_to_polygon(self, mask_tensor, epsilon_factor=0.005, min_area=100):
        """将mask tensor转换为多边形坐标"""
        import numpy as np
        import cv2
        import torch

        if mask_tensor is None:
            return []

        if isinstance(mask_tensor, torch.Tensor):
            mask_np = mask_tensor.cpu().detach().numpy()
        else:
            mask_np = np.array(mask_tensor)

        if mask_np.ndim == 3:
            mask_np = mask_np[0]
        if mask_np.ndim == 4:
            mask_np = mask_np[0, 0]

        mask_np = (mask_np * 255).astype(np.uint8)
        h, w = mask_np.shape

        contours, _ = cv2.findContours(
            mask_np, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        polygons = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue

            epsilon = epsilon_factor * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)

            if len(approx) >= 3:
                poly_coords = [[pt[0][0] / w, pt[0][1] / h] for pt in approx]
                polygons.append(poly_coords)

        return polygons

    def run(self, params, inputs=None):
        import json
        from sam3_nodes.segmentation import SAM3Grounding, SAM3Segmentation

        sam3_model = inputs.get("sam3_model")
        image = inputs.get("image")

        if not sam3_model or image is None:
            raise ValueError("必须连接 'sam3_model' 和 'image' 输入")

        mode = params.get("mode")

        raw_mask = None
        raw_visualization = None
        json_boxes = "[]"

        if mode == "Text Grounding":
            text_prompt = params.get("text_prompt", "")
            confidence = params.get("confidence", 0.2)

            if not text_prompt:
                self.logger.warning("文本模式下未提供提示词，结果可能为空。")

            self.logger.info(
                f"正在执行 SAM3 文本分割: '{text_prompt}' (阈值: {confidence})"
            )

            grounding_node = SAM3Grounding()
            result = grounding_node.segment(
                sam3_model=sam3_model,
                image=image,
                confidence_threshold=confidence,
                text_prompt=text_prompt,
                positive_boxes=None,
                negative_boxes=None,
                max_detections=-1,
                offload_model=False,
            )

            raw_mask = result[0]
            raw_visualization = result[1]
            json_boxes = result[2]

        else:
            self.logger.info("正在执行 SAM3 交互式分割...")

            seg_node = SAM3Segmentation()
            accumulated_pos_points = []
            accumulated_neg_points = []
            mask_b64 = None
            last_mask_tensor = None
            last_polygons = []

            for round_idx in range(100):
                self.logger.info(f"交互式分割第 {round_idx + 1} 轮")
                image_b64 = self.tensor_to_base64(image)

                mask_display_mode = params.get("mask_display_mode", "Polygon")
                schema = {
                    "image": image_b64,
                    "positive_points": accumulated_pos_points,
                    "negative_points": accumulated_neg_points,
                }

                if mask_display_mode == "Pixel":
                    schema["mask"] = mask_b64
                else:
                    schema["polygons"] = last_polygons if round_idx > 0 else []

                result = self.emit_message(
                    method="point_click_selector",
                    params={
                        "title": f"SAM3 交互式标注 (第 {round_idx + 1} 轮)",
                        "schema": schema,
                    },
                    interactive=True,
                )

                if not result:
                    self.logger.warning("交互标注未返回有效结果")
                    break

                pos_points = result.get("positive_points", [])
                neg_points = result.get("negative_points", [])

                if round_idx == 0 and len(pos_points) == 0 and len(neg_points) == 0:
                    self.logger.info("用户未标注任何点，退出交互")
                    break

                if len(pos_points) == 0 and len(neg_points) == 0:
                    self.logger.info("用户未添加新点，结束交互")
                    break

                accumulated_pos_points = pos_points
                accumulated_neg_points = neg_points

                self.logger.info(
                    f"第 {round_idx + 1} 轮标注: 正点 {len(pos_points)}, 负点 {len(neg_points)}, 累计: 正{len(accumulated_pos_points)}, 负{len(accumulated_neg_points)}"
                )

                pos_points_data = (
                    {
                        "points": accumulated_pos_points,
                        "labels": [1] * len(accumulated_pos_points),
                    }
                    if accumulated_pos_points
                    else None
                )
                neg_points_data = (
                    {
                        "points": accumulated_neg_points,
                        "labels": [0] * len(accumulated_neg_points),
                    }
                    if accumulated_neg_points
                    else None
                )

                seg_result = seg_node.segment(
                    sam3_model=sam3_model,
                    image=image,
                    positive_points=pos_points_data,
                    negative_points=neg_points_data,
                    box=None,
                    refinement_iterations=0,
                    use_multimask=params.get("multimask", True),
                    output_best_mask=True,
                    offload_model=False,
                )

                last_mask_tensor = seg_result[0]
                raw_visualization = seg_result[2]
                json_boxes = seg_result[3]

                last_polygons = self.mask_to_polygon(last_mask_tensor)
                mask_b64 = self.tensor_to_base64(last_mask_tensor, is_mask=True)

            if last_mask_tensor is not None:
                raw_mask = last_mask_tensor
            else:
                seg_result = seg_node.segment(
                    sam3_model=sam3_model,
                    image=image,
                    positive_points=None,
                    negative_points=None,
                    box=None,
                    refinement_iterations=0,
                    use_multimask=params.get("multimask", True),
                    output_best_mask=True,
                    offload_model=False,
                )
                raw_mask = seg_result[0]
                raw_visualization = seg_result[2]
                json_boxes = seg_result[3]

        self.logger.info("正在转换图像格式...")

        pil_mask = self.tensor_to_pil(raw_mask, is_mask=True)
        pil_image = self.tensor_to_pil(raw_visualization, is_mask=False)
        polygons = self.mask_to_polygon(raw_mask)

        return {
            "mask": pil_mask,
            "image": pil_image,
            "json_boxes": json.loads(json_boxes),
            "polygons": polygons,
        }
