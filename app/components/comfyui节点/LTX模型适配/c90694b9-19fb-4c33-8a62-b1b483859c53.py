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
    requirements = "av,torch,numpy"
    name = "LTX2图像预处理器"
    category = "comfyui节点/LTX模型适配"
    description = "对输入图像进行特定的视频压缩模拟，提高 I2V 生成的一致性。"
    
    inputs = [PortDefinition(name="image", label="IMAGE", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE)]
    outputs = [PortDefinition(name="image", label="预处理IMAGE", type=ArgumentType.IMAGE)]
    properties = {
        "compression": PropertyDefinition(type=PropertyType.INT, default=35, min=0, max=100, label="压缩强度(CRF)"),
    }

    def run(self, params, inputs):
        import av
        from io import BytesIO
        import numpy as np
        import torch
        image = inputs.get("image") # [B, H, W, C]
        crf = int(params.get("compression", 35))
        
        if crf == 0: return {"image": image}

        def process_single(img_tensor):
            # 将 tensor 转为 numpy rgb24
            img_np = (img_tensor.cpu().numpy() * 255).astype(np.uint8)
            h, w = (img_np.shape[0] // 2) * 2, (img_np.shape[1] // 2) * 2
            img_np = img_np[:h, :w]

            # 使用 PyAV 模拟视频压缩
            out_buf = BytesIO()
            container = av.open(out_buf, "w", format="mp4")
            stream = container.add_stream("libx264", rate=1)
            stream.height, stream.width = h, w
            stream.options = {"crf": str(crf), "preset": "veryfast"}
            
            frame = av.VideoFrame.from_ndarray(img_np, format="rgb24")
            for packet in stream.encode(frame): container.mux(packet)
            for packet in stream.encode(): container.mux(packet)
            container.close()

            # 解码回图像
            out_buf.seek(0)
            with av.open(out_buf) as in_cont:
                decoded_frame = next(in_cont.decode(video=0))
                return torch.from_numpy(decoded_frame.to_ndarray(format="rgb24")).float() / 255.0

        output = torch.stack([process_single(image[i]) for i in range(image.shape[0])])
        return {"image": output}