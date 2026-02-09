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


class TextEncodeAceAudio(BaseComponent):
    name = "AceStep音频文本编码"
    category = "comfyui节点/Ace-Step"
    description = "将文本标签和歌词编码为音频生成条件，支持歌词强度调节"
    requirements = "#comfy,torch,#node_helpers"
    inputs = [
        PortDefinition(name="clip", label="CLIP模型", type=ArgumentType.OBJECT, sub_type="CLIP", connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="conditioning", label="生成条件", type=ArgumentType.OBJECT, sub_type="Conditioning"),
    ]
    properties = {
        "tags": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="",
            label="文本标签",
        ),
        "lyrics": PropertyDefinition(
            type=PropertyType.MULTILINE,
            default="",
            label="歌词内容",
        ),
        "lyrics_strength": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=1.0,
            label="歌词强度",
        ),
    }

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import node_helpers
        
        clip = inputs.clip
        tags = params.tags or ""
        lyrics = params.lyrics or ""
        lyrics_strength = float(params.lyrics_strength) if params.lyrics_strength is not None else 1.0
        
        tokens = clip.tokenize(tags, lyrics=lyrics)
        conditioning = clip.encode_from_tokens_scheduled(tokens)
        conditioning = node_helpers.conditioning_set_values(conditioning, {"lyrics_strength": lyrics_strength})
        
        return {
            "conditioning": conditioning
        }
