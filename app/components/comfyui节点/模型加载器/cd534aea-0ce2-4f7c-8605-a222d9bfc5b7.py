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


class ComfyVAELoader(BaseComponent):
    inputs = []
    name = "VAE加载器"
    category = "comfyui节点/模型加载器"
    description = "加载 VAE 模型，支持标准 VAE、TAESD (SD1/SDXL/SD3/Flux) 以及 Pixel Space"
    requirements = "torch,#comfyui,#folder_paths,#comfy"

    outputs = [
        PortDefinition(name="vae", label="VAE", type=ArgumentType.OBJECT, sub_type="VAE"),
    ]

    properties = {
        "vae_name": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="VAE文件或TAESD指令",
        ),
    }

    # 定义支持的 TAES 类型列表
    video_taes = ["taehv", "lighttaew2_2", "lighttaew2_1", "lighttaehy1_5"]
    image_taes = ["taesd", "taesdxl", "taesd3", "taef1"]

    def _load_taesd(self, name):
        """
        内部辅助函数：加载 TAESD (Tiny AutoEncoder)
        """
        import torch
        import os
        import folder_paths
        import comfy.utils
        import comfy.sd
        sd = {}
        # 获取 vae_approx 目录下的文件列表
        approx_vaes = folder_paths.get_filename_list("vae_approx")

        # 寻找对应的 encoder 和 decoder 文件
        # 例如 name="taesdxl"，则寻找 taesdxl_encoder.pth 和 taesdxl_decoder.pth
        try:
            encoder = next(filter(lambda a: a.startswith("{}_encoder.".format(name)), approx_vaes))
            decoder = next(filter(lambda a: a.startswith("{}_decoder.".format(name)), approx_vaes))
        except StopIteration:
            raise FileNotFoundError(f"未在 'models/vae_approx' 中找到 {name} 的 encoder 或 decoder 文件。")

        # 加载 Encoder
        enc_path = folder_paths.get_full_path_or_raise("vae_approx", encoder)
        enc = comfy.utils.load_torch_file(enc_path)
        for k in enc:
            sd["taesd_encoder.{}".format(k)] = enc[k]

        # 加载 Decoder
        dec_path = folder_paths.get_full_path_or_raise("vae_approx", decoder)
        dec = comfy.utils.load_torch_file(dec_path)
        for k in dec:
            sd["taesd_decoder.{}".format(k)] = dec[k]

        # 设置缩放参数 (Scale & Shift)
        if name == "taesd":
            sd["vae_scale"] = torch.tensor(0.18215)
            sd["vae_shift"] = torch.tensor(0.0)
        elif name == "taesdxl":
            sd["vae_scale"] = torch.tensor(0.13025)
            sd["vae_shift"] = torch.tensor(0.0)
        elif name == "taesd3": # SD3
            sd["vae_scale"] = torch.tensor(1.5305)
            sd["vae_shift"] = torch.tensor(0.0609)
        elif name == "taef1": # Flux
            sd["vae_scale"] = torch.tensor(0.3611)
            sd["vae_shift"] = torch.tensor(0.1159)
            
        return sd

    def run(self, params, inputs=None):
        import torch
        import os
        import folder_paths
        import comfy.utils
        import comfy.sd
        vae_name = params.get("vae_name", "")
        
        if not vae_name:
            raise ValueError("VAE名称不能为空")

        self.logger.info(f"正在加载 VAE: {vae_name}")

        metadata = None
        sd = {}

        # === 逻辑分支 1: Pixel Space (像素空间，不进行压缩) ===
        if vae_name == "pixel_space":
            sd["pixel_space_vae"] = torch.tensor(1.0)
            
        # === 逻辑分支 2: Image TAES (近似VAE，如 taesdxl) ===
        elif vae_name in self.image_taes:
            sd = self._load_taesd(vae_name)
            
        # === 逻辑分支 3: Video TAES 或 标准 VAE 文件 ===
        else:
            # 检查是否为 Video TAES (去除扩展名后匹配)
            base_name = os.path.splitext(vae_name)[0]
            
            if base_name in self.video_taes:
                # Video TAES 通常在 vae_approx 目录
                vae_name = folder_paths.get_full_path_or_raise("vae_approx", vae_name)
            else:
                # 标准 VAE 通常在 vae 目录
                # get_full_path_or_raise 会自动搜索 models/vae
                folder_paths.add_model_folder_path("vae", os.path.dirname(vae_name))
            
            sd, metadata = comfy.utils.load_torch_file(vae_name, return_metadata=True)

        # 构建 VAE 对象
        vae = comfy.sd.VAE(sd=sd, metadata=metadata)
        
        # 验证有效性 (ComfyUI 原生方法)
        if hasattr(vae, "throw_exception_if_invalid"):
            vae.throw_exception_if_invalid()
            
        return {"vae": vae}
