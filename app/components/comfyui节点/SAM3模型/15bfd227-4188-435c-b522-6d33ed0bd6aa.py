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


class ComfySAM3Loader(BaseComponent):
    requirements = "Pillow,comfy-env>0.0.1,comfy-test>0.0.1,einops>=0.6.0,ftfy==6.1.1,huggingface_hub,iopath>=0.1.10,# nodes,numpy>=1.26,opencv-python>=4.8.0,psutil>=5.9.0,pycocotools>=2.0.6,regex,safetensors>=0.4.0,scikit-image>=0.19.0,timm>=1.0.17,tqdm,typing_extensions"
    name = "SAM3模型加载器"
    category = "comfyui节点/SAM3模型"
    description = "直接从本地 nodes 模块加载 SAM3 模型"
    
    outputs = [
        PortDefinition(name="sam3_model", label="SAM3_MODEL", type=ArgumentType.OBJECT),
    ]

    properties = {
        "model_path": PropertyDefinition(
            type=PropertyType.FILE,
            default="pt",
            label="SAM3模型路径",
        ),
    }

    def run(self, params, inputs=None):
        from nodes.load_model import LoadSAM3Model

        try:
            model_path = params.get("model_path", "models/sam3/sam3.pt")
            
            self.logger.info(f"正在通过本地 nodes 模块加载 SAM3: {model_path}")
            
            # 1. 实例化类
            loader_instance = LoadSAM3Model()
            
            # 2. 调用 load_model 方法
            # 源码返回的是 tuple: (unified_model,)
            result = loader_instance.load_model(model_path)
            
            # 3. 返回结果
            return {"sam3_model": result[0]}

        except Exception as e:
            self.logger.error(f"SAM3 模型加载失败: {e}")
            raise e