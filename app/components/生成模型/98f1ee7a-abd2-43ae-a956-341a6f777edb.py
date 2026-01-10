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
    name = "多模态视频生成引擎 (CogVideoX)"
    category = "生成模型"
    description = "专业级视频生成组件：支持纯文字生成视频（T2V）或文字+图像生成视频（I2V）。"
    requirements = "diffusers>=0.30.0,transformers,accelerate,torch,sentencepiece,Pillow"
    
    inputs = [
        PortDefinition(name="prompt", label="提示词", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="input_image", label="参考图像 (可选)", type=ArgumentType.IMAGE, connection=ConnectionType.SINGLE),
    ]
    
    outputs = [
        PortDefinition(name="output_video.mp4", label="输出视频", type=ArgumentType.FILE),
    ]
    
    properties = {
        "num_frames": PropertyDefinition(
            type=PropertyType.INT,
            default=49,
            label="生成帧数 (49或81)",
        ),
        "steps": PropertyDefinition(
            type=PropertyType.INT,
            default=50,
            label="推理步数",
        ),
        "guidance_scale": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=6.0,
            label="CFG 引导系数",
        ),
        "fps": PropertyDefinition(
            type=PropertyType.INT,
            default=8,
            label="输出帧率",
        ),
        "seed": PropertyDefinition(
            type=PropertyType.INT,
            default=-1,
            label="随机种子",
        ),
    }


    def run(self, params, inputs):
        self.pipe = None
        self.current_mode = None # 记录当前加载的是 T2V 还是 I2V
        import os
        import torch
        import random
        from PIL import Image
        from diffusers import CogVideoXPipeline, CogVideoXImageToVideoPipeline
        from diffusers.utils import export_to_video
        from pathlib import Path

        # 1. 环境准备
        device = "cuda" if torch.cuda.is_available() else "cpu"
        prompt = inputs.get("prompt")
        image = inputs.get("input_image")
        
        if not prompt:
            prompt = "A professional cinematic video, high quality."
            self.logger.warning("未检测到提示词，使用默认描述")

        # 2. 随机种子逻辑（解决“生成都一样”的关键）
        seed = params.get("seed", -1)
        if seed == -1:
            seed = random.randint(0, 1000000)
        
        # 必须使用专用的 Generator 确保随机性被应用到正确设备
        generator = torch.Generator(device=device).manual_seed(seed)
        self.logger.info(f"当前任务种子: {seed}")

        # 3. 动态加载模型
        model_id = params.get("model_variant", "THUDM/CogVideoX-2b")
        is_i2v = image is not None
        
        # 确定需要哪种 Pipeline
        pipe_class = CogVideoXImageToVideoPipeline if is_i2v else CogVideoXPipeline
        
        if self.pipe is None or self.loaded_model_id != model_id:
            self.logger.info(f"正在加载 {model_id} (模式: {'图生视频' if is_i2v else '文生视频'})...")
            
            # 如果是图生视频，需要加载专门的 I2V 模型分支
            load_path = model_id if not is_i2v else f"{model_id}-I2V"
            
            self.pipe = pipe_class.from_pretrained(
                load_path, 
                torch_dtype=torch.float16
            )
            
            # 性能优化
            self.pipe.enable_model_cpu_offload() # 节省显存
            self.pipe.vae.enable_tiling()        # 防止大分辨率下显存炸裂
            self.loaded_model_id = model_id

        # 4. 执行生成
        self.logger.info(f"开始生成视频。Prompt: {prompt}")
        
        try:
            with torch.inference_mode():
                if is_i2v:
                    # 图生视频：提示词和图片共同起作用
                    input_image = image.resize((720, 480)) # 标准分辨率
                    video_frames = self.pipe(
                        prompt=prompt,
                        image=input_image,
                        num_videos_per_prompt=1,
                        num_inference_steps=params.get("steps", 30),
                        num_frames=params.get("num_frames", 49),
                        guidance_scale=params.get("guidance_scale", 6.0),
                        generator=generator,
                    ).frames[0]
                else:
                    # 纯文生视频：完全由提示词控制
                    video_frames = self.pipe(
                        prompt=prompt,
                        num_videos_per_prompt=1,
                        num_inference_steps=params.get("steps", 30),
                        num_frames=params.get("num_frames", 49),
                        guidance_scale=params.get("guidance_scale", 6.0),
                        generator=generator,
                    ).frames[0]
        except Exception as e:
            self.logger.error(f"生成失败: {str(e)}")
            raise e

        # 5. 结果持久化
        output_filename = "result.mp4"
        
        export_to_video(video_frames, output_filename, fps=params.get("fps", 8))
        
        self.logger.success(f"视频生成成功，总计 {len(video_frames)} 帧")

        try:
            with open(output_filename, "rb") as f:
                video_data = f.read()
            return {
                "output_video.mp4": video_data
            }
        finally:
            if os.path.exists(output_filename):
                os.remove(output_filename)

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