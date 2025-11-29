import hashlib
import importlib.util
import inspect
import os
import sys

from pathlib import Path
from typing import Tuple, Dict, Type, Optional

from loguru import logger

from app.interfaces.component_developer.component_history_manager import ComponentHistoryManager

HISTORY_DIR = Path("canvas_files/node_histories")
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def get_file_hash(file_path: Path) -> str:
    """计算文件的 SHA256 哈希（用于生成稳定 ID）"""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def resource_path(relative_path):
    """获取打包后资源文件的绝对路径"""
    if hasattr(sys, '_MEIPASS'):
        # 如果是打包后的环境
        base_path = sys._MEIPASS
    else:
        # 开发环境，直接使用当前路径
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


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

    def _clear_dynamic_modules(self):
        """清理旧的动态组件模块，避免 exec 污染"""
        to_remove = [name for name in sys.modules if name.startswith("dynamic_component_")]
        for name in to_remove:
            del sys.modules[name]

    def _scan_impl(self) -> Tuple[Dict[str, Type], Dict[str, Path]]:
        """实际扫描逻辑"""
        comp_path = self._components_dir.resolve()
        if not comp_path.exists():
            raise ValueError(f"components_dir does not exist: {comp_path}")

        comp_map = {}
        file_map = {}

        for py_file in comp_path.rglob("*.py"):
            if py_file.name in ("__init__.py", "base.py"):
                continue

            try:
                # === 自动初始化历史记录（若不存在）===
                histories = ComponentHistoryManager.load_histories(py_file)
                if not histories:
                    # 首次扫描，尝试创建 V1
                    try:
                        code = py_file.read_text(encoding="utf-8")
                        code = "\n".join(code.split("\n")[17:])
                        # 临时加载模块以获取组件名
                        tmp_module_name = f"tmp_init_{py_file.stem}_{hash(py_file)}"
                        spec = importlib.util.spec_from_file_location(tmp_module_name, py_file)
                        tmp_module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(tmp_module)

                        comp_cls = None
                        for name, obj in inspect.getmembers(tmp_module, inspect.isclass):
                            if getattr(obj, 'category', ""):
                                comp_cls = obj
                                break

                        if comp_cls is not None:
                            component_name = getattr(comp_cls, 'name', obj.__name__)
                            ComponentHistoryManager.save_history(py_file, component_name, code)
                            logger.info(f"✅ 自动创建 V1 历史: {py_file.name}")
                        else:
                            logger.warning(f"跳过无有效组件类的文件: {py_file}")

                    except Exception as e:
                        logger.error(f"自动创建 V1 失败 {py_file}: {e}")

                # 重新加载最新历史（可能刚创建）
                histories = ComponentHistoryManager.load_histories(py_file)
                latest_version = histories[-1]["version"] if histories else "V1"

                # === 正常加载组件类 ===
                mtime = py_file.stat().st_mtime_ns
                module_name = f"dynamic_component_{py_file.stem}_{mtime:x}"
                if module_name in sys.modules:
                    del sys.modules[module_name]

                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec is None or spec.loader is None:
                    logger.warning(f"⚠️ Cannot load spec for {py_file}")
                    continue

                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if getattr(obj, 'category', None) is not None:
                        component_name = getattr(obj, 'name', obj.__name__)
                        if not component_name:
                            continue

                        # === 注入元数据 ===
                        obj._version = latest_version
                        obj._source_file = py_file
                        obj._history_file = ComponentHistoryManager.get_history_file_path(py_file)

                        full_path = f"{obj.category}/{component_name}"
                        comp_map[full_path] = obj
                        file_map[full_path] = py_file

            except Exception as e:
                import traceback
                logger.error(f"⚠️ Failed to load {py_file}: {e}\n{traceback.format_exc()}")

        return comp_map, file_map

    def get_components(self, force_reload: bool = False) -> Tuple[Dict[str, Type], Dict[str, Path]]:
        """获取组件（带缓存）"""
        if self._cache is None or force_reload:
            self._clear_dynamic_modules()
            self._cache = self._scan_impl()
        return self._cache

    def refresh(self) -> Tuple[Dict[str, Type], Dict[str, Path]]:
        """刷新组件并返回新结果"""
        return self.get_components(force_reload=True)


if __name__ == "__main__":
    pass