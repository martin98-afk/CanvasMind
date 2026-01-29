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


class ComfyControlNetLoader(BaseComponent):
    requirements = "torch,comfy,nodes"
    name = "ControlNet加载器"
    category = "comfyui节点/模型加载器"
    description = "加载 ControlNet 模型 (如 canny, depth, openpose 等)"

    inputs = []
    outputs = [
        PortDefinition(name="control_net", label="CONTROL_NET", type=ArgumentType.OBJECT),
    ]

    properties = {
        "control_net_name": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="ControlNet模型文件",
        ),
    }

    def ensure_comfy_exist(self):
        import os, sys
        path = self.global_variable.comfy_extension
        if path not in sys.path:
            sys.path.append(path)
        os.chdir(path)

    def run(self, params, inputs):
        self.ensure_comfy_exist()
        import nodes
        
        cnet_name = params.get("control_net_name")
        
        loader = nodes.ControlNetLoader()
        # load_controlnet 返回 (controlnet, )
        control_net = loader.load_controlnet(cnet_name)[0]

        return {
            "control_net": control_net
        }