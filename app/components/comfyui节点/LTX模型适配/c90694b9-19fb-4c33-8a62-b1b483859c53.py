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


class LTXVPreprocess(BaseComponent):
    requirements = "av,torch,numpy,Pillow"
    name = "LTX2图像预处理器"
    category = "comfyui节点/LTX模型适配"
    description = "对输入图像进行特定的视频压缩模拟，提高 I2V 生成的一致性。"
    
    inputs = [
        PortDefinition(name="image", label="IMAGE", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="image", label="预处理IMAGE", type=ArgumentType.OBJECT, sub_type="IMAGE"),
    ]
    properties = {
        "compression": PropertyDefinition(
            type=PropertyType.INT,
            default=35,
            label="压缩强度(CRF)",
        ),
    }

    def run(self, params, inputs):
        import torch
        import numpy as np
        import av
        from io import BytesIO
        from PIL import Image
        raw_image = inputs.get("image")
        crf = int(params.get("compression", 35))

        # --- 修复逻辑：自动将 PIL 转换为 Tensor ---
        if isinstance(raw_image, Image.Image):
            # 处理单张 PIL 图像
            img_np = np.array(raw_image.convert("RGB")).astype(np.float32) / 255.0
            image = torch.from_numpy(img_np)[None, ...] # 增加 Batch 维度 -> [1, H, W, C]
        elif isinstance(raw_image, list) and isinstance(raw_image[0], Image.Image):
            # 处理 PIL 图像列表
            img_list = [torch.from_numpy(np.array(i.convert("RGB")).astype(np.float32) / 255.0) for i in raw_image]
            image = torch.stack(img_list) # 合并为 -> [N, H, W, C]
        elif torch.is_tensor(raw_image):
            # 如果已经是 Tensor 则保持不变
            image = raw_image
        else:
            raise ValueError(f"不支持的图像输入类型: {type(raw_image)}")
        # ---------------------------------------

        if crf == 0: 
            return {"image": image}

        def process_single(img_tensor):
            # 确保输入是 [H, W, C]
            img_np = (img_tensor.cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
            
            # 视频编码要求分辨率为偶数
            h, w = (img_np.shape[0] // 2) * 2, (img_np.shape[1] // 2) * 2
            img_np = img_np[:h, :w]

            # 使用 PyAV 模拟视频压缩逻辑 (LTX2 源码核心)
            out_buf = BytesIO()
            container = av.open(out_buf, "w", format="mp4")
            try:
                stream = container.add_stream("libx264", rate=1)
                stream.height, stream.width = h, w
                # 设置 CRF 压缩率
                stream.options = {"crf": str(crf), "preset": "veryfast"}
                
                frame = av.VideoFrame.from_ndarray(img_np, format="rgb24")
                for packet in stream.encode(frame):
                    container.mux(packet)
                for packet in stream.encode():
                    container.mux(packet)
            finally:
                container.close()

            # 解码回图像
            out_buf.seek(0)
            with av.open(out_buf) as in_cont:
                decoded_frame = next(in_cont.decode(video=0))
                res = torch.from_numpy(decoded_frame.to_ndarray(format="rgb24")).float() / 255.0
                return res

        # 遍历 Batch 处理
        self.logger.info(f"正在进行 LTX2 图像预处理 (CRF: {crf})...")
        processed_list = [process_single(image[i]) for i in range(image.shape[0])]
        output = torch.stack(processed_list)
        
        return {"image": output}