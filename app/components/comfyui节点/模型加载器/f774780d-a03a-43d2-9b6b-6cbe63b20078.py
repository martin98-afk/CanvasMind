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


class ComfyGGUFLoader(BaseComponent):
    requirements = "folder_paths,gguf,nodes_gguf,torch"
    name = "GGUF模型加载器(带自动安装)"
    category = "comfyui节点/模型加载器"
    description = "自动检查并安装 GGUF 插件，然后加载 GGUF 扩散模型"
    
    outputs = [
        PortDefinition(name="model", label="MODEL", type=ArgumentType.OBJECT),
    ]
    
    properties = {
        "model_path": PropertyDefinition(type=PropertyType.FILE, default="", label="GGUF模型路径"),
        "auto_install": PropertyDefinition(type=PropertyType.BOOL, default=True, label="若缺少插件则自动下载安装"),
    }

    def _auto_install_plugin(self, custom_nodes_path):
        """自动化安装逻辑"""
        import subprocess
        import sys
        import os
        
        plugin_url = "https://github.com/city96/ComfyUI-GGUF"
        plugin_path = os.path.join(custom_nodes_path, "ComfyUI-GGUF")
        
        # 1. 检查并克隆仓库
        if not os.path.exists(plugin_path):
            self.logger.info(f"检测到缺少 GGUF 插件，正在从 GitHub 克隆: {plugin_url}")
            try:
                # 执行 git clone
                subprocess.run(["git", "clone", plugin_url, plugin_path], check=True)
                self.logger.info("插件克隆成功！")
            except Exception as e:
                self.logger.error(f"Git 克隆失败，请检查是否安装了 Git。错误: {e}")
                return False

        # 2. 检查并安装 pip 依赖
        try:
            import gguf
        except ImportError:
            self.logger.info("正在安装必要的依赖库: gguf...")
            try:
                # 执行 pip install
                subprocess.run([sys.executable, "-m", "pip", "install", "gguf"], check=True)
                self.logger.info("依赖库 gguf 安装成功！")
            except Exception as e:
                self.logger.error(f"Pip 安装依赖失败: {e}")
                return False
        
        return True

    def ensure_comfy_exist(self):
        import os, sys
        # 1. 基础路径检查
        comfy_path = self.global_variable.comfy_extension
        if comfy_path not in sys.path:
            sys.path.append(comfy_path)
        os.chdir(comfy_path)

        # 2. 插件路径处理
        custom_nodes_path = os.path.join(comfy_path, "custom_nodes")
        plugin_path = os.path.join(custom_nodes_path, "ComfyUI-GGUF")

        # 3. 自动安装
        if not os.path.exists(plugin_path):
            success = self._auto_install_plugin(custom_nodes_path)
            if not success:
                raise RuntimeError("GGUF 插件安装失败，请手动检查环境。")

        # 4. 将插件加入系统路径
        if plugin_path not in sys.path:
            sys.path.append(plugin_path)

    def run(self, params, inputs=None):
        self.ensure_comfy_exist()
        import os
        import torch
        import folder_paths
        
        model_path = params.get("model_path")
        if not model_path or not os.path.exists(model_path):
            raise FileNotFoundError(f"找不到 GGUF 模型: {model_path}")

        try:
            # 动态导入刚刚下载好的插件模块
            import nodes_gguf 
            
            # 配置 ComfyUI 寻找模型的路径
            folder_paths.add_model_folder_path("diffusion_models", os.path.dirname(model_path))
            
            self.logger.info(f"正在加载 GGUF 权重: {os.path.basename(model_path)}")
            loader = nodes_gguf.UnetLoaderGGUF()
            result = loader.load_unet(os.path.basename(model_path))
            
            return {"model": result[0]}

        except Exception as e:
            self.logger.error(f"加载 GGUF 时发生异常: {e}")
            raise e