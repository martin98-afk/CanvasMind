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


class ComfyWanVideoDecode(BaseComponent):
    name = "Wan视频解码器"
    category = "comfyui节点/视频生成"
    description = "将 Wan 的 5D 潜空间解码并合成为 MP4 视频"
    requirements = "torch,numpy,opencv-python,#comfy"

    inputs = [
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT),
        PortDefinition(name="latent", label="LATENT", type=ArgumentType.OBJECT),
    ]
    outputs = [
        PortDefinition(name="video_path", label="视频文件路径", type=ArgumentType.TEXT),
    ]

    properties = {
        "fps": PropertyDefinition(
            type=PropertyType.INT,
            default=16,
            label="视频帧率 (FPS)",
        ),
        "tile_size": PropertyDefinition(
            type=PropertyType.INT,
            default=512,
            label="Tiled解码尺寸 (减小可省显存)",
        ),
    }

    def ensure_comfy_exist(self):
        import os, sys
        path = self.global_variable.comfy_extension
        if path not in sys.path: sys.path.append(path)
        os.chdir(path)

    def run(self, params, inputs):
        self.ensure_comfy_exist()
        import torch
        import numpy as np
        import cv2
        import os
        import uuid
        import comfy.model_management as mm

        vae = inputs.get("vae")
        latent = inputs.get("latent")
        
        if vae is None or latent is None:
            raise ValueError("缺少 VAE 或 LATENT 输入")

        samples = latent["samples"] # 形状: [B, 16, F_latent, H_latent, W_latent]
        fps = params.get("fps", 16)
        tile_size = params.get("tile_size", 512)

        self.logger.info(f"开始视频解码，潜空间形状: {samples.shape}")

        with torch.no_grad():
            # 1. 显存调度：确保 VAE 在 GPU 上
            # 注意：视频 VAE 非常大，如果显存不足，ComfyUI 会自动处理
            
            # 2. 执行 Tiled 解码 (这是视频生成必须的，否则必崩)
            # Wan 2.1 的 decode_tiled 会输出 [Batch, Frames, Height, Width, Channels]
            # 这里的 overlap 设为 16 或 32 以减少拼缝
            try:
                pixel_tensor = vae.decode_tiled(
                    samples, 
                    tile_x=tile_size, 
                    tile_y=tile_size, 
                    overlap=32
                )
            except Exception as e:
                self.logger.error(f"VAE解码失败: {e}")
                raise e

            # 3. 转换格式：Tensor -> Numpy [F, H, W, C]
            # 取第一个 Batch
            video_np = (pixel_tensor[0].cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
            
            # 释放显存
            del pixel_tensor
            mm.soft_empty_cache()

            # 4. 合成视频
            # 创建临时目录
            output_dir = os.path.join(os.getcwd(), "temp_output")
            os.makedirs(output_dir, exist_ok=True)
            video_filename = f"wan_video_{uuid.uuid4().hex[:8]}.mp4"
            video_path = os.path.join(output_dir, video_filename)

            num_frames, height, width, channels = video_np.shape
            self.logger.info(f"正在合成视频: {width}x{height}, {num_frames}帧")

            # 使用 OpenCV 写入 MP4 (h264 编码)
            # 注意：某些环境可能不支持 'avc1'，可以换成 'mp4v'
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(video_path, fourcc, fps, (width, height))

            for i in range(num_frames):
                frame = video_np[i]
                # RGB 转 BGR (OpenCV 标准)
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                out.write(frame_bgr)
            
            out.release()

            if not os.path.exists(video_path):
                raise RuntimeError("视频合成失败，未生成文件。")

            self.logger.info(f"✅ 视频生成成功: {video_path}")
            
            return {"video_path": video_path}