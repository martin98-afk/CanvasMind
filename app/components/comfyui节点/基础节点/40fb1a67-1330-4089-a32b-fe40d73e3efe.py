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


class ConditioningZeroOut(BaseComponent):
    name = "条件零化"
    category = "comfyui节点/基础节点"
    description = "将条件向量的所有值置零，用于生成无条件引导或中和条件影响"
    requirements = "comfy,torch"
    inputs = [
        PortDefinition(name="conditioning", label="条件向量", type=ArgumentType.OBJECT),
    ]
    outputs = [
        PortDefinition(name="conditioning", label="零化条件", type=ArgumentType.OBJECT),
    ]
    properties = {}

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        import torch
        
        conditioning = inputs.conditioning
        if conditioning is None:
            self.logger.warning("输入条件向量为空，返回空列表")
            return {"conditioning": []}
        
        c = []
        for t in conditioning:
            # 复制条件字典并零化关键张量
            d = t[1].copy()
            pooled_output = d.get("pooled_output", None)
            if pooled_output is not None:
                d["pooled_output"] = torch.zeros_like(pooled_output)
            conditioning_lyrics = d.get("conditioning_lyrics", None)
            if conditioning_lyrics is not None:
                d["conditioning_lyrics"] = torch.zeros_like(conditioning_lyrics)
            # 零化条件张量本身
            n = [torch.zeros_like(t[0]), d]
            c.append(n)
        
        return {
            "conditioning": c
        }
