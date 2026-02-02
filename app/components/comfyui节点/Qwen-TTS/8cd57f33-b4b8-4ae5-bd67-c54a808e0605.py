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


class Qwen3TTSRoleBank(BaseComponent):
    name = "语音角色库配置"
    category = "comfyui节点/Qwen-TTS"
    description = "将多个声音特征打包成角色库，供对话节点使用"

    inputs = [
        PortDefinition(name="voices", label="角色声音", type=ArgumentType.OBJECT, connection=ConnectionType.MULTIPLE),
    ]
    
    outputs = [
        PortDefinition(name="role_bank", label="角色库", type=ArgumentType.OBJECT),
    ]

    properties = {
        "names": PropertyDefinition(
            type=PropertyType.DYNAMICFORM,
            label="角色名称",
            schema={
                "name": PropertyDefinition(
                    type=PropertyType.TEXT,
                    default="",
                    label="角色名",
                ),
                "var": PropertyDefinition(
                    type=PropertyType.VARIABLE,
                    default="节点输入变量",
                    label="连接变量",
                ),
            }
        ),
    }

    def run(self, params, inputs=None):
        bank = {}
        for i in range(1, 4):
            v = inputs.get(f"voice_{i}")
            name = params.get(f"name_{i}")
            if v and name:
                bank[name] = v
        return {"role_bank": bank}