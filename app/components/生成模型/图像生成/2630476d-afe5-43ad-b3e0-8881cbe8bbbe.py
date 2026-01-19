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


class CLIPTextEncode(BaseComponent):
    requirements = "torch"
    name = "CLIP文本编码器"
    category = "生成模型/图像生成"
    description = "将文本转换为CLIP嵌入 (Conditioning)"
    
    inputs = [
        PortDefinition(name="clip", label="模型束", type=ArgumentType.OBJECT),
    ]
    outputs = [
        PortDefinition(name="conditioning", label="条件数据", type=ArgumentType.OBJECT),
    ]
    properties = {
        "prompt": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="",
            label="提示词输入",
        ),
    }

    def run(self, params, inputs=None):
        import torch
        clip_bundle = inputs.get("clip") # 之前加载器返回的ClipWrapper
        text = params.get("prompt", "")

        if not clip_bundle:
            raise ValueError("请连接CLIP加载器")

        # 使用封装好的 model 和 tokenizer/processor
        model = clip_bundle.model
        processor = clip_bundle.processor

        # 编码逻辑
        inputs_data = processor(text=text, return_tensors="pt", padding=True, truncation=True)
        inputs_data = {k: v.to(model.device) for k, v in inputs_data.items()}

        with torch.no_grad():
            # 针对不同模型获取 hidden_states
            if hasattr(model, "get_text_features"):
                # 标准 CLIPModel
                outputs = model.text_model(**inputs_data)
                cond = outputs.last_hidden_state
            else:
                # 纯 TextModel (如 SD 里的 CLIPTextModel)
                outputs = model(**inputs_data)
                cond = outputs.last_hidden_state

        return {"conditioning": cond}