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


class ComfyReservedVRAM(BaseComponent):
    name = "ComfyUI显存预留设置"
    category = "comfyui节点/显存管理"
    description = "设置 ComfyUI 运行时强制预留的显存(GB)，防止显存溢出"
    requirements = "pynvml,comfy,torch"

    inputs = [
        PortDefinition(name="anything", label="输入(透传)", type=ArgumentType.OBJECT),
    ]
    outputs = [
        PortDefinition(name="output", label="输出(透传)", type=ArgumentType.OBJECT),
        PortDefinition(name="seed", label="SEED", type=ArgumentType.INT),
        PortDefinition(name="reserved_gb", label="实际预留(GB)", type=ArgumentType.FLOAT),
    ]

    properties = {
        "reserved": PropertyDefinition(
            type=PropertyType.RANGE, default=0.6, min=-2.0, max=24.0, step=0.1,
            label="预留显存 (GB)"
        ),
        "mode": PropertyDefinition(
            type=PropertyType.CHOICE, default="auto", 
            choices=["auto", "manual"],
            label="模式 (Auto=当前已用+预留)"
        ),
        "auto_max_reserved": PropertyDefinition(
            type=PropertyType.RANGE, default=0.0, min=0.0, max=24.0, step=0.1,
            label="自动模式上限 (GB, 0=无限制)"
        ),
        "clean_gpu_before": PropertyDefinition(
            type=PropertyType.BOOL, default=True,
            label="设置前强制清理显存"
        ),
        "seed": PropertyDefinition(
            type=PropertyType.INT, default=0,
            label="随机种子"
        ),
    }

    def ensure_comfy_exist(self):
        import os, sys
        path = self.global_variable.comfy_extension
        if path not in sys.path:
            sys.path.append(path)
        os.chdir(path)

    def get_gpu_memory_info(self):
        """获取GPU显存信息"""
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            total = memory_info.total / (1024**3)  # GB
            used = memory_info.used / (1024**3)    # GB
            return total, used
        except Exception as e:
            self.logger.warning(f"无法通过 pynvml 获取显存信息: {e}")
            return None, None

    def run(self, params, inputs):
        self.ensure_comfy_exist()
        import gc
        import torch
        import comfy.model_management as mm

        # 1. 获取参数
        reserved = float(params.get("reserved", 0.6))
        mode = params.get("mode", "auto")
        auto_max_reserved = float(params.get("auto_max_reserved", 0.0))
        clean_gpu_before = params.get("clean_gpu_before", True)
        seed = params.get("seed", 0)
        passthrough = inputs.get("anything")

        # 2. 前置清理逻辑
        if clean_gpu_before:
            self.logger.info("正在执行前置显存清理...")
            gc.collect()
            mm.unload_all_models()
            mm.soft_empty_cache()
            torch.cuda.empty_cache()

        # 3. 计算最终预留值
        final_reserved_gb = 0.0
        
        if mode == "auto":
            total, used = self.get_gpu_memory_info()
            if total is not None and used is not None:
                # 自动模式：将当前已用的显存 + 用户填写的偏移量作为预留
                auto_reserved = used + reserved
                auto_reserved = max(0, auto_reserved)
                
                if auto_max_reserved > 0:
                    auto_reserved = min(auto_reserved, auto_max_reserved)
                
                self.logger.info(f"自动计算预留值: {auto_reserved:.2f}GB (当前已用:{used:.2f}GB)")
                final_reserved_gb = auto_reserved
            else:
                self.logger.warning("自动模式失败，回退到手动设置")
                final_reserved_gb = max(0, reserved)
        else:
            # 手动模式
            final_reserved_gb = max(0, reserved)

        # 4. 修改 ComfyUI 后端全局变量 (最核心的一步)
        # ComfyUI 的内存管理器会读取这个值，在分配 VRAM 前先扣除这部分
        mm.EXTRA_RESERVED_VRAM = int(final_reserved_gb * 1024**3)
        
        self.logger.info(f"ComfyUI EXTRA_RESERVED_VRAM 已设置为: {final_reserved_gb:.2f} GB")

        return {
            "output": passthrough,
            "seed": seed,
            "reserved_gb": round(final_reserved_gb, 2)
        }