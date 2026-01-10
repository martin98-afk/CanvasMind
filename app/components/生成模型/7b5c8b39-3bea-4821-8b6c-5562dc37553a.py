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


class Component(BaseComponent):
    name = "图像转视频生成器"
    category = "生成模型"
    description = "使用 Stable Video Diffusion 将静态图像转换为短视频"
    requirements = "diffusers,torch,transformers"
    inputs = [
        PortDefinition(name="input_image", label="输入图像", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output_video.mp4", label="输出视频", type=ArgumentType.FILE),
    ]
    properties = {
        "motion_bucket_id": PropertyDefinition(
            type=PropertyType.INT,
            default=123,
            label="运动幅度",
        ),
        "noise_aug_strength": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.02,
            label="噪声增强强度，增加细节变化",
        ),
        "fps": PropertyDefinition(
            type=PropertyType.INT,
            default=7,
            label="输出视频的帧率",
        ),
        "seed": PropertyDefinition(
            type=PropertyType.INT,
            default=-1,
            label="随机种子",
        ),
    }
    def run(self, params, inputs=None):
        self.pipe = None
        import os
        import torch
        from diffusers import StableVideoDiffusionPipeline
        from diffusers.utils import export_to_video
        # 1. 获取输入数据
        image = inputs.get("input_image")
        if image is None:
            raise ValueError("需要输入图像")

        # 2. 处理参数
        motion_bucket_id = params.get("motion_bucket_id", 127)
        fps = params.get("fps", 7)
        noise_aug_strength = params.get("noise_aug_strength", 0.02)
        seed = params.get("seed", -1)
        
        if seed == -1:
            generator = torch.manual_seed(torch.randint(0, 1000000, (1,)).item())
        else:
            generator = torch.manual_seed(seed)

        # 3. 加载模型 (单例模式，避免重复加载占用显存)
        if self.pipe is None:
            self.logger.info("正在加载 SVD 模型...")
            self.pipe = StableVideoDiffusionPipeline.from_pretrained(
                "stabilityai/stable-video-diffusion-img2vid-xt", 
                torch_dtype=torch.float16, 
                variant="fp16"
            )
            # self.pipe.enable_model_cpu_offload() # 节省显存
            self.pipe.to("cuda:0") # 如果显存足够（>24GB）可以直接推到 cuda
            self.logger.info("模型加载完成")

        # SVD 模型要求图片尺寸是 64 的倍数，通常建议 1024x576 或 512x288
        image = image.resize((1024, 576))

        # 5. 执行推理
        self.logger.info("开始生成视频帧...")
        frames = self.pipe(
            image, 
            decode_chunk_size=8, 
            generator=generator, 
            motion_bucket_id=motion_bucket_id,
            noise_aug_strength=noise_aug_strength
        ).frames[0]

        # 6. 保存视频文件
        output_path = os.path.join(os.getcwd(), "output_video.mp4")
        export_to_video(frames, output_path, fps=fps)
        
        self.logger.info(f"视频生成成功: {output_path}")
        try:
            return {
                "output_video.mp4": open(output_path, "rb").read()
            }
        finally:
            os.remove(output_path)


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={"prop1": "test"},
        inputs={"input1": "output"},
        node_id="测试模型",
        show_input_types = True,
        show_output_types = True,
        show_execution_time = True,
        global_vars = {}
    )
    print(result)
