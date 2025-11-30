# -*- coding: utf-8 -*-
import asyncio
import importlib
import inspect
import json
import os
import sys
import threading
import traceback
from pathlib import Path
from typing import Tuple, Dict, Type, Optional, List

from loguru import logger

from app.components.base import COMPONENT_IMPORT_CODE
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
                logger.info(f"文件变化: {path} {change_type}")
                if path.suffix == ".json":
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
                logger.info(f"加载组件: {full_path} {node_name} {version}")
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
    _file_mtime_map: Dict[Path, int]  # 记录每个 .py 文件的最后修改时间

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._file_mtime_map = {}

    def _clear_dynamic_modules(self):
        to_remove = [name for name in sys.modules if name.startswith("dynamic_component_")]
        for name in to_remove:
            del sys.modules[name]

    def get_components(self, force_reload: bool = False) -> Tuple[Dict[str, Type], Dict[str, Path]]:
        if self._cache is None or force_reload:
            return self.refresh()
        return self._cache

    def refresh(self) -> Tuple[Dict[str, Type], Dict[str, Path]]:
        if self._cache is None:
            # 首次加载：全量扫描
            self._clear_dynamic_modules()
            self._cache = self._scan_all_components()
            comp_map, file_map = self._cache
            # 初始化 mtime 记录
            self._file_mtime_map = {
                py_file.resolve(): py_file.stat().st_mtime_ns
                for py_file in set(file_map.values())
            }
            return self._cache

        # 增量更新
        comp_path = self._components_dir.resolve()
        if not comp_path.exists():
            raise ValueError(f"components_dir does not exist: {comp_path}")

        current_py_files = set()
        for py_file in comp_path.rglob("*.py"):
            if py_file.name in ("__init__.py", "base.py"):
                continue
            current_py_files.add(py_file.resolve())

        comp_map, file_map = self._cache

        # 1. 找出已删除的文件
        deleted_files = set(self._file_mtime_map.keys()) - current_py_files
        for del_file in deleted_files:
            keys_to_remove = [k for k, v in file_map.items() if v == del_file]
            for k in keys_to_remove:
                comp_map.pop(k, None)
                file_map.pop(k, None)
            self._file_mtime_map.pop(del_file, None)
            logger.info(f"🗑️ 组件文件已删除: {del_file.name}")

        # 2. 找出新增或修改的文件
        changed_files = []
        for py_file in current_py_files:
            old_mtime = self._file_mtime_map.get(py_file, -1)
            new_mtime = py_file.stat().st_mtime_ns
            if new_mtime != old_mtime:
                changed_files.append((py_file, new_mtime))

        # 3. 重新加载变化的文件
        for py_file, new_mtime in changed_files:
            # 先移除旧组件（如果存在）
            keys_to_remove = [k for k, v in file_map.items() if v == py_file]
            for k in keys_to_remove:
                comp_map.pop(k, None)
                file_map.pop(k, None)

            try:
                self._load_single_component(py_file, comp_map, file_map)
                self._file_mtime_map[py_file] = new_mtime
            except Exception as e:
                traceback.print_exc()
                logger.error(f"⚠️ 组件加载失败且无有效历史回退: {py_file} - {e}")

        self._cache = (comp_map, file_map)
        return self._cache

    def _scan_all_components(self) -> Tuple[Dict[str, Type], Dict[str, Path]]:
        """全量扫描（仅用于首次加载）"""
        comp_path = self._components_dir.resolve()
        if not comp_path.exists():
            raise ValueError(f"components_dir does not exist: {comp_path}")

        comp_map = {}
        file_map = {}

        for py_file in comp_path.rglob("*.py"):
            if py_file.name in ("__init__.py", "base.py"):
                continue
            try:
                self._load_single_component(py_file, comp_map, file_map)
            except Exception as e:
                traceback.print_exc()
                logger.error(f"首次加载组件失败（无历史）: {py_file} - {e}")

        return comp_map, file_map

    def _load_single_component(self, py_file: Path, comp_map: Dict, file_map: Dict):
        """加载单个组件，失败时尝试回退到历史版本"""
        current_code = None
        try:
            current_code = py_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"无法读取组件文件 {py_file}: {e}")

        # 尝试加载当前文件
        if current_code is not None:
            try:
                self._do_load_component_from_file(
                    py_file, current_code, comp_map, file_map, is_fallback=False
                )
                return
            except Exception as e:
                logger.error(f"当前组件文件加载失败 {py_file}: {e}")

        # 回退到历史版本
        histories = ComponentHistoryManager.load_histories(py_file)
        if not histories:
            raise RuntimeError(f"组件 {py_file} 加载失败，且无可用历史版本")

        latest_hist = histories[-2] if len(histories) > 1 else histories[0]
        fallback_code = COMPONENT_IMPORT_CODE + latest_hist["code"]
        version = latest_hist["version"]
        logger.warning(f"⚠️ 回退到历史版本 {version} for {py_file.name}")

        try:
            py_file.write_text(fallback_code, encoding="utf-8")
            # 用你的标准方法加载临时文件
            self._do_load_component_from_file(
                py_file, fallback_code, comp_map, file_map, is_fallback=True, fallback_version=version
            )
        except Exception as e:
            raise RuntimeError(f"历史版本 {version} 回退失败: {e}") from e

    def _do_load_component_from_file(
        self,
        py_file: Path,
        code: str,
        comp_map: Dict,
        file_map: Dict,
        is_fallback: bool = False,
        fallback_version: str = ""
    ):
        # 若代码为空，跳过
        if not code.strip():
            raise ValueError("组件代码为空")

        # 创建唯一模块名
        unique_id = f"{hash(code)}_{py_file.stem}"
        module_name = f"dynamic_component_{unique_id}"
        if module_name in sys.modules:
            del sys.modules[module_name]

        # 创建模块
        spec = importlib.util.spec_from_file_location(module_name, py_file)
        if spec is None:
            raise RuntimeError("无法创建模块 spec")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # 查找组件类
        comp_cls = None
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if getattr(obj, 'category', ""):
                comp_cls = obj
                break

        if comp_cls is None:
            raise ValueError("未找到有效组件类（缺少 category 属性）")

        # 确定版本
        if is_fallback:
            version = fallback_version
        else:
            # 保存历史（仅当是当前文件且未保存过）
            histories = ComponentHistoryManager.load_histories(py_file)
            if not histories:
                component_name = getattr(comp_cls, 'name')
                ComponentHistoryManager.save_history(py_file, component_name, code)
                version = "V1"
                logger.info(f"✅ 自动创建 V1 历史: {py_file.name}")
            else:
                version = histories[-1]["version"]

        # 注入元信息
        comp_cls._version = version
        comp_cls._source_file = py_file
        comp_cls._is_fallback = is_fallback

        # 加载完整历史
        hist_path = ComponentHistoryManager.get_history_file_path(py_file)
        with open(hist_path, 'r', encoding='utf-8') as f:
            comp_cls._history_file = json.load(f)

        component_name = getattr(comp_cls, 'name')
        full_path = f"{comp_cls.category}/{component_name}"

        comp_map[full_path] = comp_cls
        file_map[full_path] = py_file

        status = "✅ 加载成功" if not is_fallback else f"✅ 回退到 {version}"
        logger.info(f"{status}: {full_path} ({py_file.name})")