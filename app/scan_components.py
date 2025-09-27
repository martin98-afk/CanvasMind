"""
@author: mading
@license: (C) Copyright: LUCULENT Corporation Limited.
@contact: mading@luculent.net
@file: scan_components.py
@time: 2025/9/26 15:05
@desc: 
"""
import os
import importlib
import inspect
from pathlib import Path
from app.components.base import BaseComponent

def scan_components(components_dir="components"):
    """扫描 components 目录（相对于脚本位置），返回 {full_path: component_class}"""
    script_dir = Path(__file__).parent
    comp_path = script_dir / components_dir

    comp_map = {}

    if not comp_path.exists():
        print(f"⚠️ Components directory '{comp_path}' not found. Creating demo components...")
        # _create_demo_components(script_dir, components_dir)
        comp_path = script_dir / components_dir

    for py_file in comp_path.rglob("*.py"):
        if py_file.name in ("__init__.py", "base.py"):
            continue

        try:
            # 计算相对于 script_dir 的路径，用于构建模块名
            rel_path = py_file.relative_to(script_dir)
            module_path = str(rel_path).replace(os.sep, ".")[:-3]  # 去掉 .py

            module = importlib.import_module(module_path)
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseComponent) and obj != BaseComponent:
                    # ✅ 关键修改：使用 getattr 获取 name 属性，提供默认回退
                    category = getattr(obj, 'category', 'General')
                    component_name = getattr(obj, 'name', obj.__name__)
                    full_path = f"{category}/{component_name}"
                    comp_map[full_path] = obj
                    print(f"✅ Loaded component: {full_path}")
        except Exception as e:
            print(f"⚠️ Failed to load {py_file}: {e}")

    return comp_map