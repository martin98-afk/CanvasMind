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


class Component(BaseComponent):
    name = "通用三模型加载器"
    category = "comfyui节点/模型加载器"
    description = "使用 ComfyUI 后端加载 Checkpoint (.safetensors/.ckpt)"
    requirements = "numpy,comfy,folder_paths,nodes"
    inputs = [
    ]
    outputs = [
        PortDefinition(name="model", label="MODEL", type=ArgumentType.OBJECT),
        PortDefinition(name="clip", label="CLIP", type=ArgumentType.OBJECT),
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT),
    ]
    
    properties = {
        "model_type": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="Standard(SD/Flux)",
            label="模型架构",
            choices=["Standard(SD/Flux)", "Wan"]
        ),
        "ckpt_path": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="unet模型绝对路径",
        ),
        "clip_path": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="clip模型绝对路径",
        ),
        "vae_path": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="vae模型绝对路径",
        ),
    }
    def ensure_comfy_exist(self):
        import os 
        # comfyui节点必须从本地comfy包中读取
        if "comfy_extension" not in self.global_variable.custom:
            raise Exception("自定义全局变量未添加 comfy_extension 参数，无法使用comfy节点。")
        elif not os.path.exists(self.global_variable.comfy_extension):
            raise Exception("配置的 comfy_extension 参数，无法找到本地文件。")
        import sys
        sys.path.append(self.global_variable.comfy_extension)

    def run(self, params, inputs=None):
        self.ensure_comfy_exist()
        import os
        
        import comfy.model_management
        import comfy.sd
        import folder_paths
        m_type = params.model_type
        ckpt_path = params.ckpt_path
        clip_path = params.clip_path
        vae_path = params.vae_path
        # 调用 ComfyUI 的核心加载函数
        # 它会自动识别是 SD1.5, SDXL 还是其他，并返回封装好的 Patcher 对象
        embedding_directory=folder_paths.get_folder_paths("embeddings")
        model, clip, vae = None, None, None
        if m_type == "Wan":
            self.logger.info("正在以 Wan2.1 模式加载模型...")
            
            # 1. 加载 DiT 模型 (Wan 2.1 建议使用专用的加载方式)
            # 注意：Wan 2.1 通常不包含在 guess_config 里，建议直接加载
            if ckpt_path and os.path.exists(ckpt_path):
                model = comfy.sd.load_diffusion_model(ckpt_path)

            # 2. 关键修复：加载 T5 CLIP
            # 必须指定 clip_type 为 WAN，否则会报 size mismatch 错误
            if clip_path and os.path.exists(clip_path):
                self.logger.info(f"正在加载 Wan 专用 T5: {clip_path}")
                # 显式指定 WAN 类型，这会初始化 256384 大小的词表
                clip = comfy.sd.load_clip(
                    ckpt_paths=[clip_path], 
                    embedding_directory=embedding_directory,
                    clip_type=comfy.sd.CLIPType.WAN 
                )
            
            # 3. 加载 3D VAE
            if vae_path and os.path.exists(vae_path):
                self.logger.info(f"正在加载 Wan 专用 VAE: {vae_path}")
                vae_sd = comfy.utils.load_torch_file(vae_path)
                # Wan 的 VAE 也是特殊的，ComfyUI 内部会自动处理
                vae = comfy.sd.VAE(sd=vae_sd)

        else:
            # 标准加载逻辑 (SD1.5, SDXL, Flux)
            self.logger.info("正在以标准模式加载模型...")
            if ckpt_path and os.path.exists(ckpt_path):
                out = comfy.sd.load_checkpoint_guess_config(
                    ckpt_path, output_vae=True, output_clip=True, 
                    embedding_directory=folder_paths.get_folder_paths("embeddings")
                )
                model, clip, vae = out[0], out[1], out[2]

            if clip is None and clip_path and os.path.exists(clip_path):
                self.logger.info(f"正在从外部路径加载 CLIP: {clip_path}")
                # 使用 ComfyUI 的 CLIP 加载器
                # type="stable_diffusion" 是通用类型，如果是 SDXL/Flux 需要特定处理
                clip = comfy.sd.load_clip(
                    ckpt_paths=[clip_path], 
                    embedding_directory=folder_paths.get_folder_paths("embeddings")
                )
            if vae_path and os.path.exists(vae_path):
                sd = comfy.utils.load_torch_file(vae_path)
                vae = comfy.sd.VAE(sd=sd)
        return {
            "model": model,
            "clip": clip,
            "vae": vae
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
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
