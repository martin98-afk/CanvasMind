# -*- coding: utf-8 -*-
import importlib
import inspect
import os
from pathlib import Path
from typing import Tuple, Dict, Type

from loguru import logger

from app.components.base import BaseComponent


def scan_components(components_dir: str="app/components", logger=logger) -> Tuple[Dict[str, object], Dict[str, Path]]:
    """
    扫描指定目录下的所有组件类（继承自 BaseComponent 且具有有效 category）。

    Args:
        components_dir: 组件目录路径（绝对路径或相对于当前工作目录的相对路径）

    Returns:
        tuple: (comp_map, file_map)
            - comp_map: {"Category/Name": ComponentClass}
            - file_map: {"Category/Name": Path(to/component.py)}
    """
    comp_path = Path(components_dir).resolve()  # 转为绝对路径，避免歧义
    if comp_path.is_absolute() or comp_path.exists():
        # 用户传的是文件系统路径，需推导出对应的包名
        comp_path = comp_path.resolve()

        # 找到 sys.path 中能包含该路径的根
        pkg_root = None
        pkg_parts = None
        for sp in map(Path, importlib.sys.path):
            try:
                pkg_parts = comp_path.relative_to(sp.resolve())
                pkg_root = sp
                break
            except ValueError:
                continue

        if pkg_root is None:
            raise ValueError(
                f"components_dir '{components_dir}' is not under any sys.path entry. "
                f"sys.path = {importlib.sys.path}"
            )

        # 构造包名：如 app.components
        package_dotted = ".".join(pkg_parts.parts)
    else:
        # 用户直接传的是包路径字符串，如 "app.components"
        package_dotted = components_dir
        # 尝试获取其文件路径用于 rglob
        try:
            pkg_module = importlib.import_module(package_dotted)
            comp_path = Path(pkg_module.__file__).parent if pkg_module.__file__ else Path(pkg_module.__path__[0])
        except Exception as e:
            raise ValueError(f"Cannot locate package '{package_dotted}': {e}")

    comp_map = {}
    file_map = {}

    for py_file in comp_path.rglob("*.py"):
        if py_file.name in ("__init__.py", "base.py"):
            continue

        try:
            # 计算该 py_file 对应的模块名（基于 package_dotted）
            rel_to_pkg = py_file.relative_to(comp_path)
            module_suffix = ".".join(rel_to_pkg.with_suffix("").parts)
            full_module_name = f"{package_dotted}.{module_suffix}" if module_suffix else package_dotted

            module = importlib.import_module(full_module_name)
            importlib.reload(module)  # 可选：开发时有用，生产环境可移除

            for name, obj in inspect.getmembers(module, inspect.isclass):
                if getattr(obj, 'category', None) is not None and obj != BaseComponent:
                    category = getattr(obj, 'category', 'General').strip()
                    if not category:
                        continue
                    component_name = getattr(obj, 'name', obj.__name__)
                    full_path = f"{category}/{component_name}"
                    comp_map[full_path] = obj
                    file_map[full_path] = py_file

        except Exception as e:
            import traceback
            from loguru import logger
            logger.error(f"⚠️ Failed to load {py_file}: {e}\n{traceback.format_exc()}")

    return comp_map, file_map