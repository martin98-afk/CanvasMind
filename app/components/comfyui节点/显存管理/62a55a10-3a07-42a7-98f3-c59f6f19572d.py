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
    name = "显存管理"
    category = "comfyui节点/显存管理"
    description = "强制设置 ComfyUI 预留的显存空间(GB)，防止显存完全溢出"
    requirements = "pynvml,torch,#comfy"

    inputs = [
        PortDefinition(name="anything", label="输入(透传)", type=ArgumentType.OBJECT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output", label="输出(透传)", type=ArgumentType.OBJECT),
        PortDefinition(name="seed", label="SEED", type=ArgumentType.INT),
        PortDefinition(name="reserved_gb", label="实际预留(GB)", type=ArgumentType.FLOAT),
    ]

    properties = {
        "reserved": PropertyDefinition(
            type=PropertyType.RANGE,
            default="0.6",
            label="预留值 (GB)",
            min=-2.0,
            max=32.0,
            step=0.1,
        ),
        "mode": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="auto",
            label="计算模式 (Auto=当前已用+预留)",
            choices=["auto", "manual"]
        ),
        "auto_max_reserved": PropertyDefinition(
            type=PropertyType.RANGE,
            default="0.0",
            label="自动模式上限 (GB, 0=无限制)",
            min=0.0,
            max=24.0,
            step=0.1,
        ),
        "clean_gpu_before": PropertyDefinition(
            type=PropertyType.BOOL,
            default=True,
            label="执行前强制清理显存",
        ),
        "seed": PropertyDefinition(
            type=PropertyType.INT,
            default=0,
            label="随机种子",
        ),
    }

    def ensure_comfy_exist(self):
        import os, sys
        path = self.global_variable.comfy_extension
        if path not in sys.path:
            sys.path.append(path)
        os.chdir(path)

    def get_gpu_info(self):
        """内部工具：获取GPU信息"""
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            total = memory_info.total / (1024**3)
            used = memory_info.used / (1024**3)
            return total, used
        except Exception as e:
            self.logger.warning(f"NVML 获取显存失败: {e}")
            return None, None

    def run(self, params, inputs):
        self.ensure_comfy_exist()
        import gc
        import torch
        import comfy.model_management as mm

        # 1. 解析参数
        reserved = float(params.get("reserved", 0.6))
        mode = params.get("mode", "auto")
        auto_max_reserved = float(params.get("auto_max_reserved", 0.0))
        clean_gpu_before = params.get("clean_gpu_before", True)
        seed = int(params.get("seed", 0))
        passthrough = inputs.get("anything")

        # 2. 强制清理 (如果勾选)
        if clean_gpu_before:
            self.logger.info("正在执行前置显存强制清理...")
            gc.collect()
            mm.unload_all_models()
            mm.soft_empty_cache()
            torch.cuda.empty_cache()

        # 3. 计算预留值
        final_gb = 0.0
        
        if mode == "auto":
            total, used = self.get_gpu_info()
            if total is not None and used is not None:
                # 自动逻辑：预留 = 当前已用 + 预设偏移
                auto_val = used + reserved
                auto_val = max(0, auto_val)
                # 应用上限限制
                if auto_max_reserved > 0:
                    auto_val = min(auto_val, auto_max_reserved)
                final_gb = auto_val
                self.logger.info(f"自动计算显存预留: {final_gb:.2f}GB (已用:{used:.2f}GB)")
            else:
                final_gb = max(0, reserved)
                self.logger.warning("NVML不可用，回退至手动预留值")
        else:
            final_gb = max(0, reserved)

        # 4. 【核心设置】修改 ComfyUI 后端全局变量
        # EXTRA_RESERVED_VRAM 会告诉 ComfyUI 在做显存预算时减去这部分
        mm.EXTRA_RESERVED_VRAM = int(final_gb * 1024 * 1024 * 1024)
        
        self.logger.info(f"ComfyUI EXTRA_RESERVED_VRAM 已设为: {final_gb:.2f} GB")

        # 处理种子 (如果是 -1 则随机一个)
        if seed == -1:
            import random
            seed = random.randint(1, 1125899906842624)

        return {
            "output": passthrough,
            "seed": seed,
            "reserved_gb": round(final_gb, 2)
        }