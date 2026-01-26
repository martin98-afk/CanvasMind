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


class ComfyClipTextEncode(BaseComponent):
    description = ""
    name = "CLIP文本编码器"
    category = "生成模型/ComfyUI"
    
    inputs = [
        PortDefinition(name="clip", label="CLIP", type=ArgumentType.OBJECT),
    ]
    outputs = [
        PortDefinition(name="conditioning", label="条件控制", type=ArgumentType.OBJECT),
    ]
    
    properties = {
        "text": PropertyDefinition(type=PropertyType.TEXT, default="", label="提示词"),
    }

    def run(self, params, inputs):
        clip = inputs.get("clip") # 从上一个组件传来的 Comfy CLIP 对象
        text = params.get("text")
        
        if clip is None:
            raise ValueError("需要连接 CLIP 模型")

        # 调用 CLIP 对象的编码方法
        tokens = clip.tokenize(text)
        cond, pooled = clip.encode_from_tokens(tokens, return_pooled=True)
        
        # 返回 ComfyUI 标准的 conditioning 格式 [[cond, {"pooled_output": pooled}]]
        return {"conditioning": [[cond, {"pooled_output": pooled}]]}


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = ComfyClipTextEncode()
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
