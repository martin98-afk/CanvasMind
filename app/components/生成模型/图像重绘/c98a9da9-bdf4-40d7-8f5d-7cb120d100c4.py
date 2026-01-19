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


class ApplyControlNet(BaseComponent):
    requirements = "torch,numpy,Pillow"
    name = "应用ControlNet"
    category = "生成模型/图像重绘"
    description = "将ControlNet注入到Conditioning中（支持正/负向提示词注入）"
    
    inputs = [
        PortDefinition(name="conditioning", label="条件(正/负向)", type=ArgumentType.OBJECT),
        PortDefinition(name="controlnet", label="ControlNet模型", type=ArgumentType.OBJECT),
        PortDefinition(name="image", label="控制图像", type=ArgumentType.IMAGE),
        PortDefinition(name="vae", label="VAE(用于Latent控制,可选)", type=ArgumentType.OBJECT),
         PortDefinition(name="mask", label="遮罩(可选)", type=ArgumentType.IMAGE),
    ]
    properties = {
        "strength": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=1.0,
            label="控制强度",
        ),
        "start_percent": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.0,
            label="开始百分比",
        ),
        "end_percent": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=1.0,
            label="结束百分比",
        ),
    }
    outputs = [
        PortDefinition(name="conditioning", label="已加强条件数据", type=ArgumentType.OBJECT),
    ]

    def run(self, params, inputs=None):
        import torch
        import numpy as np
        from PIL import Image

        # 1. 获取输入
        cond_input = inputs.get("conditioning")
        cnet_model = inputs.get("controlnet")
        pil_img = inputs.get("image")
        vae = inputs.get("vae")
        pil_mask = inputs.get("mask")

        if cond_input is None or cnet_model is None or pil_img is None:
            return {"conditioning": cond_input}

        # --- 关键修复：标准化数据结构 ---
        # 如果上游 CLIP 直接传的是 Tensor，将其包装成 ComfyUI 风格的 [[tensor, {}]]
        if isinstance(cond_input, torch.Tensor):
            cond_prepared = [[cond_input, {}]]
        elif isinstance(cond_input, list):
            cond_prepared = cond_input
        else:
            self.logger.error(f"不支持的 Conditioning 类型: {type(cond_input)}")
            return {"conditioning": cond_input}

        # 2. 图像预处理
        # 确保图像为 RGB
        pil_img = pil_img.convert("RGB")
        width, height = pil_img.size
        # 缩放到 8 的倍数以适配 VAE/ControlNet
        width, height = (width // 8) * 8, (height // 8) * 8
        pil_img = pil_img.resize((width, height), Image.LANCZOS)
        
        img_np = np.array(pil_img).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).permute(2, 0, 1).unsqueeze(0)
        
        # 3. 处理 Mask (如果存在)
        if pil_mask:
            mask_img = pil_mask.convert("L").resize((width, height), Image.LANCZOS)
            mask_np = np.array(mask_img).astype(np.float32) / 255.0
            mask_tensor = torch.from_numpy(mask_np).unsqueeze(0).unsqueeze(0) # [1, 1, H, W]
            img_tensor = img_tensor * mask_tensor

        # 4. 注入 ControlNet 逻辑
        output_cond = []
        try:
            for item in cond_prepared:
                # 再次安全检查解包
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    t, extra = item, {}
                else:
                    t, extra = item[0], item[1]
                
                new_extra = extra.copy() if extra is not None else {}
                
                # 创建 ControlNet 参数包
                control_instance = {
                    "model": cnet_model,
                    "hint": img_tensor.to(cnet_model.device, dtype=cnet_model.dtype),
                    "strength": params.get("strength", 1.0),
                    "start_percent": params.get("start_percent", 0.0),
                    "end_percent": params.get("end_percent", 1.0),
                    "vae": vae
                }
                
                # 支持多个 ControlNet 叠加
                if "control" not in new_extra:
                    new_extra["control"] = []
                new_extra["control"].append(control_instance)
                
                output_cond.append([t, new_extra])

            self.logger.info(f"成功将 ControlNet 注入到 {len(output_cond)} 个条件槽中")
            return {"conditioning": output_cond}

        except Exception as e:
            self.logger.error(f"注入 ControlNet 时解包失败: {e}")
            raise e