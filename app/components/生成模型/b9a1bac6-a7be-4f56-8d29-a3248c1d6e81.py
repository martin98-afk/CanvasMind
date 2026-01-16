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


class SDTextToImageComponent(BaseComponent):
    name = "K采样器"
    category = "生成模型"
    description = "集成式 Stable Diffusion 文本生成图像节点 (MVP)"
    requirements = "diffusers,torch,transformers,accelerate,Pillow"
    
    inputs = [
        PortDefinition(name="prompt", label="正向提示词", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
        PortDefinition(name="negative_prompt", label="负向提示词", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output_image", label="生成的图像", type=ArgumentType.IMAGE),
    ]
    
    properties = {
        "model_id": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="runwayml/stable-diffusion-v1-5",
            label="模型ID或路径",
            choices=["runwayml/stable-diffusion-v1-5"]
        ),
        "wid": PropertyDefinition(
            type=PropertyType.RANGE,
            default="512.0",
            label="宽度",
            min=300.0,
            max=1000.0,
            step=10.0,
        ),
        "heig": PropertyDefinition(
            type=PropertyType.RANGE,
            default="512.0",
            label="高度",
            min=300.0,
            max=1000.0,
            step=10.0,
        ),
        "steps": PropertyDefinition(
            type=PropertyType.RANGE,
            default="20.0",
            label="迭代步数",
            min=0.0,
            max=50.0,
            step=1.0,
        ),
        "cfg": PropertyDefinition(
            type=PropertyType.RANGE,
            default="7.0",
            label="提示词引导系数(CFG)",
            min=0.0,
            max=100.0,
            step=1.0,
        ),
        "seed": PropertyDefinition(
            type=PropertyType.INT,
            default=-1,
            label="随机种子 (-1为随机)",
        ),
    }

    def run(self, params, inputs=None):
        import torch
        from diffusers import StableDiffusionPipeline

        # 1. 参数解析
        model_id = params.model_id
        prompt = inputs.prompt
        n_prompt = inputs.negative_prompt
        width = params.wid
        height = params.heig
        steps = params.steps
        cfg = params.cfg
        seed = params.seed

        # 2. 种子处理
        if seed == -1:
            seed = torch.seed()
        generator = torch.Generator("cuda").manual_seed(seed)

        # 3. 模型加载 (在 Subprocess 模式下，这是最耗时的)
        self.logger.info(f"正在加载模型: {model_id}...")
        try:
            # 使用 float16 节省显存并加速
            pipe = StableDiffusionPipeline.from_pretrained(
                model_id, 
                torch_dtype=torch.float16,
                safety_checker=None # 禁用审核以加快加载和减少显存
            )
            pipe.to("cuda")
            # 开启内存优化
            # pipe.enable_attention_slicing()
        except Exception as e:
            self.logger.error(f"模型加载失败: {str(e)}")
            raise e

        # 4. 执行推理 (采样)
        self.logger.info("开始采样生成...")
        image = pipe(
            prompt=prompt,
            negative_prompt=n_prompt,
            width=int(width // 8 * 8),
            height=int(height // 8 * 8),
            num_inference_steps=int(steps),
            guidance_scale=cfg,
            generator=generator
        ).images[0]

        # 5. 返回结果 (转换为字节流传递给主进程)
        self.logger.info("图像生成完成")


        return {
            "output_image": image
        }

if __name__ == "__main__":
    # 调试代码
    model = SDTextToImageComponent()
    res = model.run(params={
        "model_id": "runwayml/stable-diffusion-v1-5",
        "prompt": "a cute cat",
        "steps": 10
    })
    print("生成成功，数据长度:", len(res["output_image"]))