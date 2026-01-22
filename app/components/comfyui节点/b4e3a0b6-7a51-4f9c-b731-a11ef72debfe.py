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


class ComfyUIConfig(BaseComponent):
    requirements = "comfy"
    name = "ComfyUI全局配置"
    category = "comfyui节点"
    description = "自动初始化ComfyUI环境并设置显存管理策略"
    
    properties = {
        "vram_mode": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="normal",
            label="显存策略",
            choices=["low", "normal", "high"]
        ),
        "use_fp8": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="启用 FP8 精度 (降低显存，微损画质)",
        ),
        "vae_tiling": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="启用 VAE 瓦片解码 (防止大图 OOM)",
        ),
        "preview_method": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="latent2rgb",
            label="预览模式",
            choices=["none", "latent2rgb", "taesd"]
        ),
    }

    def ensure_comfy_exist(self):
        import os
        import sys
        import subprocess
        from pathlib import Path
        # 1. 获取预设路径或默认路径
        # 优先从全局变量获取，如果没有则设定一个默认克隆位置（例如当前目录下的 ComfyUI_Repo）
        if "comfy_extension" not in self.global_variable.custom:
            target_path = None
        else:
            target_path = self.global_variable.comfy_extension
        default_clone_path = os.path.abspath("./ComfyUI_Repo")

        # 2. 判断是否需要克隆
        need_clone = False
        if not target_path:
            self.logger.info("全局变量 'comfy_extension' 未设置，准备检查默认路径...")
            target_path = default_clone_path
            if not os.path.exists(target_path):
                need_clone = True
        elif not os.path.exists(target_path):
            self.logger.warning(f"配置的路径 {target_path} 不存在，将尝试克隆到该位置。")
            need_clone = True

        # 3. 执行克隆逻辑
        if need_clone:
            self.logger.info(f"正在从 GitHub 克隆 ComfyUI 到: {target_path} ...")
            try:
                # 确保父目录存在
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                # 执行 git clone
                subprocess.run(
                    ["git", "clone", "https://github.com/comfyanonymous/ComfyUI.git", target_path],
                    check=True,
                    capture_output=True
                )
                self.logger.info("ComfyUI 克隆成功！")
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.decode() if e.stderr else str(e)
                raise Exception(f"克隆 ComfyUI 失败，请检查网络或是否安装了 Git: {error_msg}")

        # 4. 设置/更新全局变量 (emit_message)
        # 这一步确保后续节点可以直接从 global_variable 获取到正确的路径
        self.emit_message(
            method="add_custom_to_global_variable",
            params={"comfy_extension": target_path}
        )
        
        # 5. 注入系统路径
        if target_path not in sys.path:
            # 插入到第一位，防止与其他同名包冲突
            sys.path.insert(0, target_path)
            
        return target_path

    def run(self, params, inputs=None):
        self.ensure_comfy_exist()
        import comfy.model_management as mm
        import comfy.options
        
        # 1. 基础显存策略
        mode = params.get("vram_mode", "normal")
        if mode == "low":
            mm.vram_state = mm.VRAMState.LOW_VRAM
        elif mode == "high":
            mm.vram_state = mm.VRAMState.HIGH_VRAM
        else:
            mm.vram_state = mm.VRAMState.NORMAL_VRAM

        # 2. VAE 策略
        comfy.options.vae_tiling = params.get("vae_tiling", False)

        # 3. 预览设置 (在某些版本中可能需要修改 comfy.args)
        # 这里展示如何通过 options 修改
        preview = params.get("preview_method", "latent2rgb")
        # 示例逻辑：如果是 Web 应用环境，通常修改 args 
        # sys.argv.append(f"--preview-method={preview}")

        # 4. 显存强制清理 (手动触发一次)
        mm.unload_all_models()
        mm.soft_empty_cache()

        self.logger.info(f"ComfyUI 配置更新完成: {params}")