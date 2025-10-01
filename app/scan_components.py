# -*- coding: utf-8 -*-
import importlib
import inspect
import os
from pathlib import Path

from loguru import logger

from app.components.base import BaseComponent


def scan_components(components_dir="components"):
    """扫描 components 目录（相对于脚本位置），返回 {full_path: component_class}"""
    script_dir = Path(__file__).parent
    comp_path = script_dir / components_dir

    comp_map = {}
    file_map = {}
    if not comp_path.exists():
        logger.error(f"⚠️ Components directory '{comp_path}' not found. Creating demo components...")
        # _create_demo_components(script_dir, components_dir)
        comp_path = script_dir / components_dir

    for py_file in comp_path.rglob("*.py"):
        if py_file.name in ("__init__.py", "base.py"):
            continue

        try:
            # 计算相对于 script_dir 的路径，用于构建模块名
            rel_path = py_file.relative_to(script_dir)
            module_path = f"app.{str(rel_path).replace(os.sep, '.')[:-3]}"  # 去掉 .py

            module = importlib.import_module(module_path)
            importlib.reload(module)
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if getattr(obj, 'category', None) is not None and obj != BaseComponent:
                    # ✅ 关键修改：使用 getattr 获取 name 属性，提供默认回退
                    category = getattr(obj, 'category', 'General')
                    component_name = getattr(obj, 'name', obj.__name__)
                    full_path = f"{category}/{component_name}"
                    comp_map[full_path] = obj
                    file_map[full_path] = py_file
        except Exception as e:
            import traceback
            logger.error(f"⚠️ Failed to load {py_file}: {traceback.format_exc()}")

    return comp_map, file_map