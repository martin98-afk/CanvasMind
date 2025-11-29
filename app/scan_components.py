import importlib.util
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Tuple, Dict, Type, Optional

from loguru import logger


def resource_path(relative_path):
    """获取打包后资源文件的绝对路径"""
    if hasattr(sys, '_MEIPASS'):
        # 如果是打包后的环境
        base_path = sys._MEIPASS
    else:
        # 开发环境，直接使用当前路径
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def cleanup_dynamic_modules():
    # 删除所有 dynamic_component_* 模块
    to_remove = [name for name in sys.modules if name.startswith("dynamic_component_")]
    for name in to_remove:
        del sys.modules[name]


def scan_components(components_dir: str = resource_path("app/components"), logger=logger) -> Tuple[Dict[str, Type], Dict[str, Path]]:
    """
    扫描指定目录下的所有 .py 文件，动态加载其中满足条件的组件类。

    支持任意文件系统路径（绝对或相对），无需该目录是 Python 包或在 sys.path 中。

    要求：
      - 每个 .py 文件应能独立导入（无未满足的顶层导入错误）
      - 组件类需满足：
          - 是 BaseComponent 的子类（或至少不是 BaseComponent 本身）
          - 具有非 None 的 'category' 属性

    Args:
        components_dir: 文件系统路径（如 './my_components' 或 '/opt/custom/components'）

    Returns:
        (comp_map, file_map)
        - comp_map: { "Category/Name": Class }
        - file_map: { "Category/Name": Path(file) }
    """
    comp_path = Path(components_dir).resolve()
    if not comp_path.exists():
        raise ValueError(f"components_dir does not exist: {comp_path}")

    comp_map = {}
    file_map = {}

    for py_file in comp_path.rglob("*.py"):
        if py_file.name == "__init__.py" or py_file.name == "base.py":
            continue

        try:
            # 动态从文件加载模块
            module_name = f"dynamic_component_{py_file.stem}_{hash(py_file)}"
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                logger.warning(f"⚠️ Cannot load spec for {py_file}")
                continue

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 遍历模块中的所有类
            for name, obj in inspect.getmembers(module, inspect.isclass):
                # 排除 BaseComponent 本身，且要求是其子类（更安全）
                if getattr(obj, 'category', None) is not None:
                    component_name = getattr(obj, 'name', obj.__name__)
                    if len(component_name) == 0:
                        continue
                    obj._source_file = py_file  # 动态加属性
                    full_path = f"{getattr(obj, 'category', None)}/{component_name}"
                    comp_map[full_path] = obj
                    file_map[full_path] = py_file

        except Exception as e:
            import traceback
            logger.error(f"⚠️ Failed to load {py_file}: {e}\n{traceback.format_exc()}")

    return comp_map, file_map


class ComponentScanner:
    _instance = None
    _cache: Optional[Tuple[Dict[str, Type], Dict[str, Path]]] = None
    _components_dir: Path = Path(resource_path("app/components"))

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._clear_dynamic_modules()  # 启动时清理（可选）

    def _clear_dynamic_modules(self):
        """清理旧的动态模块，避免 exec 污染"""
        to_remove = [name for name in sys.modules if name.startswith("dynamic_component_")]
        for name in to_remove:
            del sys.modules[name]

    def _scan_impl(self) -> Tuple[Dict[str, Type], Dict[str, Path]]:
        """实际扫描逻辑（你原来的代码）"""
        comp_path = self._components_dir.resolve()
        if not comp_path.exists():
            raise ValueError(f"components_dir does not exist: {comp_path}")

        comp_map = {}
        file_map = {}

        for py_file in comp_path.rglob("*.py"):
            if py_file.name in ("__init__.py", "base.py"):
                continue

            try:
                # 使用文件修改时间确保模块名唯一（避免 sys.modules 复用）
                mtime = py_file.stat().st_mtime_ns
                module_name = f"dynamic_component_{py_file.stem}_{mtime:x}"

                # 确保旧模块被移除（防御性）
                if module_name in sys.modules:
                    del sys.modules[module_name]

                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec is None or spec.loader is None:
                    logger.warning(f"⚠️ Cannot load spec for {py_file}")
                    continue

                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module  # 显式注册到 sys.modules
                spec.loader.exec_module(module)

                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if getattr(obj, 'category', None) is not None:
                        component_name = getattr(obj, 'name', obj.__name__)
                        if not component_name:
                            continue
                        obj._source_file = py_file
                        full_path = f"{obj.category}/{component_name}"
                        comp_map[full_path] = obj
                        file_map[full_path] = py_file

            except Exception as e:
                import traceback
                logger.error(f"⚠️ Failed to load {py_file}: {e}\n{traceback.format_exc()}")

        return comp_map, file_map

    def get_components(self, force_reload: bool = False) -> Tuple[Dict[str, Type], Dict[str, Path]]:
        """
        获取组件扫描结果。
        - 首次调用：扫描并缓存
        - 后续调用：返回缓存（除非 force_reload=True）
        """
        if self._cache is None or force_reload:
            self._clear_dynamic_modules()  # 刷新前清理
            self._cache = self._scan_impl()
        return self._cache

    def refresh(self) -> Tuple[Dict[str, Type], Dict[str, Path]]:
        """主动刷新组件并返回新结果"""
        return self.get_components(force_reload=True)


if __name__ == "__main__":
    pass