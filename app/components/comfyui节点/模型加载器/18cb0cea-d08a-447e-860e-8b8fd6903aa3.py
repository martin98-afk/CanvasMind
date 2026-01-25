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


class ComfyGGUFClipLoader(BaseComponent):
    name = "GGUF CLIP加载器(多模态)"
    category = "comfyui节点/模型加载器"
    description = "加载 GGUF 或常规 CLIP 模型，支持单/双/三/四 CLIP 加载 (如 SDXL/SD3/Flux)"
    requirements = "# comfy_gguf,# folder_paths,gguf>=0.13.0,protobuf,sentencepiece"
    
    outputs = [
        PortDefinition(name="clip", label="CLIP", type=ArgumentType.OBJECT),
    ]
    
    properties = {
        "clip_path_1": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="CLIP 模型 1 (必须)",
        ),
        "clip_path_2": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="CLIP 模型 2 (可选 - SDXL/SD3)",
        ),
        "clip_path_3": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="CLIP 模型 3 (可选 - SD3)",
        ),
        "clip_path_4": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="CLIP 模型 4 (可选)",
        ),
        "clip_type": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="stable_diffusion",
            label="CLIP 类型",
            choices=["ltxv", "stable_diffusion", "stable_cascade", "sd3", "stable_audio"]
        ),
    }

    def run(self, params, inputs=None):
        import os
        import sys
        import folder_paths
        
        if self.global_variable.comfy_extension not in sys.path:
            sys.path.append(self.global_variable.comfy_extension)

        try:
            import comfy_gguf.nodes as nodes_gguf

            # 收集所有非空的路径
            clip_paths = []
            for i in range(1, 5):
                path = params.get(f"clip_path_{i}")
                if path and os.path.exists(path):
                    clip_paths.append(path)
            
            if not clip_paths:
                raise ValueError("至少需要提供一个有效的 CLIP 模型路径")

            clip_type = params.get("clip_type", "stable_diffusion")
            count = len(clip_paths)
            
            # 注册路径 (ComfyUI 需要文件名，所以我们把目录加入搜索路径)
            # 注意：CLIPLoaderGGUF 会同时查找 'clip' 和 'clip_gguf' 类型
            for p in clip_paths:
                folder_paths.add_model_folder_path("clip", os.path.dirname(p))
                folder_paths.add_model_folder_path("clip_gguf", os.path.dirname(p))
            
            # 提取文件名
            filenames = [os.path.basename(p) for p in clip_paths]
            self.logger.info(f"正在加载 {count} 个 CLIP 模型: {filenames}")

            # 根据数量选择对应的 Loader 类
            result = None
            
            if count == 1:
                loader = nodes_gguf.CLIPLoaderGGUF()
                result = loader.load_clip(clip_name=filenames[0], type=clip_type)
                
            elif count == 2:
                loader = nodes_gguf.DualCLIPLoaderGGUF()
                result = loader.load_clip(
                    clip_name1=filenames[0], 
                    clip_name2=filenames[1], 
                    type=clip_type
                )
                
            elif count == 3:
                loader = nodes_gguf.TripleCLIPLoaderGGUF()
                # Triple Loader 源码中参数略有不同，type 默认为 sd3，但可以传参
                # 注意：TripleCLIPLoaderGGUF 的 load_clip 方法签名可能没有 type 参数(看源码)，
                # 检查源码：def load_clip(self, clip_name1, clip_name2, clip_name3, type="sd3"):
                # 是有的。
                result = loader.load_clip(
                    clip_name1=filenames[0], 
                    clip_name2=filenames[1], 
                    clip_name3=filenames[2],
                    type=clip_type
                )
                
            elif count == 4:
                loader = nodes_gguf.QuadrupleCLIPLoaderGGUF()
                result = loader.load_clip(
                    clip_name1=filenames[0], 
                    clip_name2=filenames[1], 
                    clip_name3=filenames[2],
                    clip_name4=filenames[3],
                    type=clip_type
                )
            
            return {"clip": result[0]}

        except Exception as e:
            self.logger.exception(f"加载 CLIP 失败: {e}")
            raise e