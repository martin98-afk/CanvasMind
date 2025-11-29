# -*- coding: utf-8 -*-
import asyncio
import importlib
import inspect
import json
import os
import sys
import threading
from pathlib import Path
from typing import Tuple, Dict, Type, Optional, List

from loguru import logger

from app.interfaces.component_developer.component_history_manager import ComponentHistoryManager

# --- 新增依赖 ---
try:
    from watchfiles import awatch, Change
    HAS_WATCHFILES = True
except ImportError:
    HAS_WATCHFILES = False
    logger.warning("watchfiles 未安装，组件使用统计将不自动更新")

HISTORY_DIR = Path("canvas_files/node_histories")
CANVAS_DIR = Path("canvas_files/workflows")
HISTORY_DIR.mkdir(parents=True, exist_ok=True)
CANVAS_DIR.mkdir(parents=True, exist_ok=True)


# === 新增：使用记录 ===
class UsageRecord:
    __slots__ = ("canvas_path", "node_name", "version")
    def __init__(self, canvas_path: Path, node_name: str, version: str):
        self.canvas_path = canvas_path
        self.node_name = node_name
        self.version = version


# === 新增：使用情况追踪器 ===
class ComponentUsageTracker:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._index: Dict[str, List[UsageRecord]] = {}
            cls._running = False
            if HAS_WATCHFILES:
                cls._instance._start_watcher()
        return cls._instance

    def _start_watcher(self):
        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._watch_files())
        threading.Thread(target=run, daemon=True).start()

    async def _watch_files(self):
        self._running = True
        await self._rebuild_index()
        logger.info("✅ 组件使用索引已全量重建")

        async for changes in awatch(CANVAS_DIR, recursive=True):
            if not self._running:
                break
            for change_type, file_path in changes:
                path = Path(file_path)
                print(path)
                if path.suffix == ".workflow.json":
                    if change_type in (Change.added, Change.modified):
                        await self._update_index(path)
                    elif change_type == Change.deleted:
                        await self._remove_canvas(path)

    async def _rebuild_index(self):
        self._index.clear()
        for canvas in CANVAS_DIR.rglob("*.workflow.json"):
            await self._update_index(canvas)

    async def _update_index(self, canvas_path: Path):
        try:
            with open(canvas_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            nodes = data.get("graph", {}).get("nodes", {})
            runtime = data.get("runtime", {})
            stable_key_map = runtime.get("node_id2stable_key", {})

            # 清理该画布旧记录
            await self._remove_canvas(canvas_path)

            for node_id, node_data in nodes.items():
                version = node_data.get("custom", {}).get("version", "latest")
                node_name = node_data.get("name", "Unknown")
                stable_key = stable_key_map.get(node_id, "")
                full_path = stable_key.split("||")[0] if "||" in stable_key else ""
                if not full_path:
                    continue

                if full_path not in self._index:
                    self._index[full_path] = []
                self._index[full_path].append(UsageRecord(canvas_path, node_name, version))
        except Exception as e:
            logger.warning(f"解析画布失败 {canvas_path}: {e}")

    async def _remove_canvas(self, canvas_path: Path):
        for records in self._index.values():
            records[:] = [r for r in records if r.canvas_path != canvas_path]

    def get_usage(self, full_path: str) -> List[UsageRecord]:
        return self._index.get(full_path, [])


# === 原 ComponentScanner 保持不变（略作清理）===
def get_file_hash(file_path: Path) -> str:
    import hashlib
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
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
        to_remove = [name for name in sys.modules if name.startswith("dynamic_component_")]
        for name in to_remove:
            del sys.modules[name]

    def _scan_impl(self) -> Tuple[Dict[str, Type], Dict[str, Path]]:
        comp_path = self._components_dir.resolve()
        if not comp_path.exists():
            raise ValueError(f"components_dir does not exist: {comp_path}")

        comp_map = {}
        file_map = {}

        for py_file in comp_path.rglob("*.py"):
            if py_file.name in ("__init__.py", "base.py"):
                continue

            try:
                histories = ComponentHistoryManager.load_histories(py_file)
                if not histories:
                    try:
                        code = py_file.read_text(encoding="utf-8")
                        # 注意：你这里切掉了前17行，确保这是正确的
                        code = "\n".join(code.split("\n")[17:])
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

                histories = ComponentHistoryManager.load_histories(py_file)
                latest_version = histories[-1]["version"] if histories else "V1"

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
                    if getattr(obj, 'category', ""):
                        component_name = getattr(obj, 'name', obj.__name__)
                        if not component_name:
                            continue

                        obj._version = latest_version
                        obj._source_file = py_file
                        with open(ComponentHistoryManager.get_history_file_path(py_file), 'r', encoding='utf-8') as f:
                            obj._history_file = json.load(f)

                        full_path = f"{obj.category}/{component_name}"
                        comp_map[full_path] = obj
                        file_map[full_path] = py_file

            except Exception as e:
                import traceback
                logger.error(f"⚠️ Failed to load {py_file}: {e}\n{traceback.format_exc()}")

        return comp_map, file_map

    def get_components(self, force_reload: bool = False) -> Tuple[Dict[str, Type], Dict[str, Path]]:
        if self._cache is None or force_reload:
            self._clear_dynamic_modules()
            self._cache = self._scan_impl()
        return self._cache

    def refresh(self) -> Tuple[Dict[str, Type], Dict[str, Path]]:
        return self.get_components(force_reload=True)