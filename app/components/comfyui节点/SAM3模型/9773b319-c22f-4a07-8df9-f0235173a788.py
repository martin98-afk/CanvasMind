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


class ComfySAM3Segmenter(BaseComponent):
    inputs = [
        PortDefinition(name="image", label="输入图片", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
        PortDefinition(name="sam3_model", label="sam3模型", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
    ]
    name = "SAM3统一分割器"
    category = "comfyui节点/SAM3模型"
    description = "集成了SAM3的文本描述分割(Grounding)和点击互动分割(Segmentation)功能"
    requirements = "Pillow,comfy-env>0.0.1,comfy-test>0.0.1,comfyui-sam3,einops>=0.6.0,ftfy==6.1.1,huggingface_hub,iopath>=0.1.10,nodes,numpy>=1.26,opencv-python>=4.8.0,psutil>=5.9.0,pycocotools>=2.0.6,regex,safetensors>=0.4.0,scikit-image>=0.19.0,timm>=1.0.17,tqdm,typing_extensions"
    
    outputs = [
        PortDefinition(name="mask", label="MASK", type=ArgumentType.OBJECT),
        PortDefinition(name="image", label="IMAGE", type=ArgumentType.OBJECT),
        PortDefinition(name="json_boxes", label="BOXES (JSON)", type=ArgumentType.TEXT),
    ]
    
    properties = {
        "mode": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="Text Grounding",
            label="工作模式",
            choices=["Text Grounding", "Interactive (Points/Box)"]
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
        "box_input": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="边界框 (x,y,w,h)",
        ),
        "point_input": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="点击点 (x,y)",
        ),
        "multimask": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="多重掩码 (Multimask)",
        ),
    }

    def run(self, params, inputs=None):
        from nodes.segmentation import SAM3Grounding, SAM3Segmentation

        # 获取输入
        sam3_model = inputs.get("sam3_model")
        image = inputs.get("image")
        
        if not sam3_model or image is None:
            raise ValueError("必须连接 'sam3_model' 和 'image' 输入")

        mode = params.get("mode")
        
        # === 分支 1: 文本分割 (Grounding) ===
        if mode == "Text Grounding":
            text_prompt = params.get("text_prompt", "")
            confidence = params.get("confidence", 0.2)
            
            if not text_prompt:
                self.logger.warning("文本模式下未提供提示词，结果可能为空。")

            self.logger.info(f"正在执行 SAM3 文本分割: '{text_prompt}' (阈值: {confidence})")
            
            # 实例化 Grounding 节点
            grounding_node = SAM3Grounding()
            
            # 调用 segment 方法
            # 注意：这里我们只用到了基础参数，positive/negative boxes 留空
            result = grounding_node.segment(
                sam3_model=sam3_model,
                image=image,
                confidence_threshold=confidence,
                text_prompt=text_prompt,
                positive_boxes=None, 
                negative_boxes=None,
                max_detections=-1,
                offload_model=False
            )
            
            # Grounding 返回: (masks, visualization, boxes, scores)
            return {
                "mask": result[0],
                "image": result[1],
                "json_boxes": result[2]
            }

        # === 分支 2: 交互式分割 (Segmentation) ===
        else:
            self.logger.info("正在执行 SAM3 交互式分割...")
            
            # 1. 构造 Box 数据 (替代 SAM3CreateBox 节点)
            box_data = None
            box_str = params.get("box_input", "").strip()
            if box_str:
                try:
                    vals = [float(x.strip()) for x in box_str.split(',')]
                    if len(vals) == 4:
                        # 构造符合 SAM3_BOXES_PROMPT 格式的字典
                        box_data = {
                            "boxes": [vals],      # [center_x, center_y, w, h]
                            "labels": [True]      # 默认为正向框
                        }
                    else:
                        self.logger.warning(f"框坐标格式错误，应为4个数字，实际: {box_str}")
                except Exception as e:
                    self.logger.warning(f"解析框坐标失败: {e}")

            # 2. 构造 Point 数据 (替代 SAM3CreatePoint 节点)
            pos_points_data = None
            point_str = params.get("point_input", "").strip()
            if point_str:
                try:
                    vals = [float(x.strip()) for x in point_str.split(',')]
                    if len(vals) == 2:
                        # 构造符合 SAM3_POINTS_PROMPT 格式的字典
                        pos_points_data = {
                            "points": [vals],     # [x, y]
                            "labels": [1]         # 1 = 前景/正向点
                        }
                    else:
                        self.logger.warning(f"点坐标格式错误，应为2个数字，实际: {point_str}")
                except Exception as e:
                    self.logger.warning(f"解析点坐标失败: {e}")

            # 实例化 Segmentation 节点
            seg_node = SAM3Segmentation()
            
            # 调用 segment 方法
            result = seg_node.segment(
                sam3_model=sam3_model,
                image=image,
                positive_points=pos_points_data, # 连接我们手动构造的数据
                negative_points=None,
                box=box_data,                    # 连接我们手动构造的数据
                refinement_iterations=0,
                use_multimask=params.get("multimask", True),
                output_best_mask=True,
                offload_model=False
            )
            
            # Segmentation 返回: (mask, mask_logits, visualization, boxes, scores)
            # 我们只需要 mask, image(visualization), boxes
            return {
                "mask": result[0],
                "image": result[2], # 注意索引：2是visualization
                "json_boxes": result[3]
            }