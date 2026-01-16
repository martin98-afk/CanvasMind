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


class UniversalTextEncoderComponent(BaseComponent):
    name = "CLIP文本编码器"
    category = "生成模型"
    description = "将提示词转换为特征向量 (支持 T5/CLIP)"
    requirements = "torch,transformers"

    inputs = [
        PortDefinition(name="text_encoder", label="编码器模型", type=ArgumentType.OBJECT),
        PortDefinition(name="tokenizer", label="分词器", type=ArgumentType.OBJECT),
    ]
    
    outputs = [
        PortDefinition(name="conditioning", label="特征向量 (Embeds)", type=ArgumentType.OBJECT),
    ]

    properties = {
        "prompt": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="",
            label="提示词",
        ),
        "max_length": PropertyDefinition(
            type=PropertyType.INT,
            default=512,
            label="最大长度",
        ),
    }

    def run(self, params, inputs=None):
        import torch

        # 1. 检查输入
        text_encoder = inputs.get("text_encoder")
        tokenizer = inputs.get("tokenizer")
        prompt = params.get("prompt", "")

        if not text_encoder or not tokenizer:
            raise ValueError("缺少 text_encoder 或 tokenizer 输入")

        self.logger.info(f"正在编码提示词: {prompt[:50]}...")

        # 2. 编码逻辑
        try:
            with torch.no_grad():
                # 分词
                text_inputs = tokenizer(
                    prompt,
                    padding="max_length",
                    max_length=params.get("max_length", 512),
                    truncation=True,
                    return_tensors="pt",
                )
                text_input_ids = text_inputs.input_ids.to(text_encoder.device)
                
                # 编码
                # 对于 Wan (T5) 来说，通常取 last_hidden_state
                prompt_embeds = text_encoder(text_input_ids)
                prompt_embeds = prompt_embeds[0] # 获取 hidden_states

            return {"conditioning": prompt_embeds}

        except Exception as e:
            self.logger.error(f"编码失败: {str(e)}")
            raise e


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = UniversalTextEncoderComponent()
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
