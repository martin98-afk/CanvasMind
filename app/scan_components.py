# -*- coding: utf-8 -*-
import asyncio
import importlib
import inspect
import json
import os
import sys
import threading
import traceback
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Tuple, Dict, Type, Optional, List, Set

from PyQt5.QtCore import QTimer
from loguru import logger

from app.components.base import COMPONENT_IMPORT_CODE
from app.interfaces.component_developer.utils.component_history_manager import ComponentHistoryManager

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
            cls._instance._index: Dict[str, List[UsageRecord]] = defaultdict(list)
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
                path = Path(file_path).resolve()  # ← 统一为绝对路径
                if str(path).endswith(".workflow.json"):  # 或更严格：path.name.endswith(".workflow.json")
                    logger.info(f"文件变化: {path} {change_type}")
                    if change_type in (Change.added, Change.modified):
                        await self._update_index(path)
                    elif change_type == Change.deleted:
                        await self._remove_canvas(path)

    async def _rebuild_index(self):
        self._index.clear()
        for canvas in CANVAS_DIR.rglob("*.workflow.json"):
            await self._update_index(canvas.resolve())  # ← 统一为绝对路径

    async def _update_index(self, canvas_path: Path):
        # ✅ 统一为绝对路径（防御性）
        canvas_path = canvas_path.resolve()
        try:
            with open(canvas_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            nodes = data.get("graph", {}).get("nodes", {})
            runtime = data.get("runtime", {})
            # 清理该画布旧记录（用绝对路径）
            await self._remove_canvas(canvas_path)

            for node_id, node_data in nodes.items():
                version = node_data.get("custom", {}).get("version", "latest")
                node_name = node_data.get("name", "")
                if "StatusDynamicNode_" not in node_data.get("type_", "Unknown"):
                    continue
                node_uuid = node_data.get("type_", "Unknown").split("StatusDynamicNode_")[1]
                # 存储绝对路径
                self._index[node_uuid].append(UsageRecord(canvas_path, node_name, version))
        except Exception as e:
            logger.warning(f"解析画布失败 {canvas_path}: {e}")

    async def _remove_canvas(self, canvas_path: Path):
        # ✅ 统一为绝对路径
        canvas_path = canvas_path.resolve()
        for records in self._index.values():
            # 使用 Path.resolve() 后，== 可正确比较同一文件
            records[:] = [r for r in records if r.canvas_path != canvas_path]

    def get_usage(self, node_uuid: str) -> List[UsageRecord]:
        return self._index.get(node_uuid, [])


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
    _uuid_map: Dict[str, Type] = {}
    _components_dir: Path = Path(resource_path("app/components"))
    _file_mtime_map: Dict[Path, int]
    _refresh_pending: bool = False
    _pending_changes: List[Tuple[Change, Path]] = list()  # 暂存待处理的变更
    _lock = threading.Lock()  # 保护 pending_changes
    _main_loop: Optional[asyncio.AbstractEventLoop] = None
    _callbacks = []  # 存储外部注册的回调函数
    _qtimers = []

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._file_mtime_map = {}
            self._refresh_pending = False
            try:
                self._main_loop = asyncio.get_running_loop()
            except RuntimeError:
                # 未在 asyncio loop 中运行（例如在 Qt 主线程）
                self._main_loop = None
            if HAS_WATCHFILES:
                self._start_component_watcher()

    @classmethod
    def register_on_change(cls, callback, qtimer=True):
        """外部注册刷新回调（如 UI 刷新）"""
        if callback not in cls._callbacks:
            cls._callbacks.append(callback)
            cls._qtimers.append(qtimer)

    @classmethod
    def unregister_on_change(cls, callback):
        if callback in cls._callbacks:
            cls._qtimers.pop(cls._callbacks.index(callback))
            cls._callbacks.remove(callback)

    def _notify_change(self):
        """内部通知所有监听者"""
        for cb in self._callbacks:
            try:
                logger.info(f"Notify change: {cb}")
                if self._qtimers[self._callbacks.index(cb)]:
                    QTimer.singleShot(0, cb)
                else:
                    cb()
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _start_component_watcher(self):
        """启动组件代码监听器（后台线程）"""
        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._watch_component_files())
        threading.Thread(target=run, daemon=True, name="ComponentWatcher").start()

    async def _watch_component_files(self):
        """监听文件变更，并将具体的变更信息传递下去"""
        comp_dir = self._components_dir.resolve()
        if not comp_dir.exists(): return

        logger.info(f"✅ 开始监听组件代码变化: {comp_dir}")
        async for changes in awatch(comp_dir, recursive=True):
            filtered_changes = []
            for change_type, file_path in changes:
                path = Path(file_path).resolve()

                # 过滤规则
                if ".temp" in path.parts: continue
                if path.suffix != ".py": continue
                if path.name in ("__init__.py", "base.py"): continue

                filtered_changes.append((change_type, path))

            if filtered_changes:
                self._schedule_refresh(filtered_changes)

    def _schedule_refresh(self, changes: list):
        """安排一次 refresh，并合并多次快速变更"""
        with self._lock:
            for c in changes:
                self._pending_changes.append(c)

        if self._refresh_pending:
            return
        self._refresh_pending = True

        def do_refresh():
            with self._lock:
                current_changes = list(self._pending_changes)
                self._pending_changes.clear()

            try:
                # 直接将变更信息传给 refresh
                self.refresh(changes=current_changes)
            except Exception as e:
                logger.error(f"组件重载失败: {e}")
            finally:
                self._refresh_pending = False

        if self._main_loop and self._main_loop.is_running():
            self._main_loop.call_soon_threadsafe(do_refresh)
        else:
            do_refresh()

    def refresh(self, changes: Optional[list] = None) -> Tuple[Dict[str, Type], Dict[str, Path]]:
        """
        组件刷新逻辑
        :param changes: watchfiles 捕获的变更列表 [(Change, path), ...]
        """
        # --- 1. 全量扫描逻辑（保持不变，作为回退或首次加载） ---
        if self._cache is None or changes is None:
            logger.info("执行组件全量扫描...")
            self._clear_dynamic_modules()
            self._cache = self._scan_all_components()
            # 兼容旧逻辑：重建 mtime 映射（虽然增量模式不再强依赖它，但保留以防万一）
            comp_map, file_map = self._cache
            self._file_mtime_map = {
                p.resolve(): p.stat().st_mtime_ns for p in set(file_map.values())
            }
            self._notify_change()
            return self._cache

        # --- 2. 增量更新逻辑 ---
        comp_map, file_map = self._cache

        # 2.1 归一化路径并分类变更，强制“先删后加”
        # 使用 dict 去重，以路径为准，保留最后一次变更类型
        unique_changes = {}
        for c_type, c_path in changes:
            unique_changes[c_path.resolve()] = c_type

        # 将变更分为两组：删除组 和 新增/修改组
        to_delete = [p for p, t in unique_changes.items() if t == Change.deleted]
        to_upsert = [p for p, t in unique_changes.items() if t != Change.deleted]

        # 2.2 处理删除 (必须先跑)
        for py_file in to_delete:
            self._remove_component_from_cache(py_file, comp_map, file_map)
            # 同步清理 mtime map
            self._file_mtime_map.pop(py_file, None)
            logger.info(f"🗑️ 增量同步：清理已删除文件 {py_file.name}")

        # 2.3 处理新增或修改
        for py_file in to_upsert:
            # 无论修改还是新增，都先尝试清理旧缓存（防止移动导致的冲突）
            self._remove_component_from_cache(py_file, comp_map, file_map)

            try:
                # 重新加载单个组件
                self._load_single_component(py_file, comp_map, file_map)
                # 更新 mtime 记录
                if py_file.exists():
                    self._file_mtime_map[py_file] = py_file.stat().st_mtime_ns
                logger.info(f"✅ 增量同步：更新/新增组件 {py_file.name}")
            except Exception as e:
                logger.error(f"⚠️ 组件加载失败: {py_file} - {e}")
                traceback.print_exc()

        self._cache = (comp_map, file_map)
        self._notify_change()
        return self._cache

    def _remove_component_from_cache(self, py_file: Path, comp_map: Dict, file_map: Dict):
        """精准清理缓存，不再产生误伤"""
        resolved_path = py_file.resolve()

        # 1. 清理 file_map 和 comp_map
        keys_to_remove = [k for k, v in file_map.items() if v.resolve() == resolved_path]
        for k in keys_to_remove:
            comp_map.pop(k, None)
            file_map.pop(k, None)

        # 2. 清理 uuid_map (这是防止冲突判断失误的关键)
        # 通过文件名 stem 寻找并删除，因为你的 UUID 机制依赖文件名
        target_uuid = resolved_path.stem
        if target_uuid in self._uuid_map:
            # 确认该 UUID 对应的确实是这个路径，才删除
            existing_comp = self._uuid_map[target_uuid]
            existing_path = Path(getattr(existing_comp, '_source_file', ""))
            if not existing_path.exists() or existing_path.resolve() == resolved_path:
                self._uuid_map.pop(target_uuid, None)

    def _clear_dynamic_modules(self):
        to_remove = [name for name in sys.modules if name.startswith("dynamic_component_")]
        for name in to_remove:
            del sys.modules[name]

    def get_component_by_uuid(self, node_uuid: str) -> Optional[Type]:
        return self._uuid_map.get(node_uuid)

    def get_components(self, force_reload: bool = False) -> Tuple[Dict[str, Type], Dict[str, Path]]:
        if self._cache is None or force_reload:
            return self.refresh()
        return self._cache

    def get_component(self, full_path: str):
        return self._cache[0].get(full_path)

    def get_file_maps(self):
        return self._cache[1]

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

    def _do_load_component_from_file(
            self,
            py_file: Path,
            code: str,
            comp_map: Dict,
            file_map: Dict,
            is_fallback: bool = False,
            fallback_version: str = ""
    ):
        if not code.strip():
            raise ValueError("组件代码为空")

        # 1. 动态加载模块
        source_lines = code.splitlines(keepends=True)
        # 假设 COMPONENT_IMPORT_CODE 是预定义的导入块
        start = len(COMPONENT_IMPORT_CODE.split("\n")) - 1
        clean_code = ''.join(source_lines[start:])

        unique_id = f"{hash(clean_code)}_{py_file.stem}"
        module_name = f"dynamic_component_{unique_id}"

        if module_name in sys.modules:
            del sys.modules[module_name]

        spec = importlib.util.spec_from_file_location(module_name, py_file)
        if spec is None:
            raise RuntimeError(f"无法创建模块 spec: {py_file}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error(f"模块执行失败: {e}")
            raise

        # 2. 提取组件类
        comp_cls = None
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if getattr(obj, 'category', ""):
                comp_cls = obj
                break

        if comp_cls is None:
            raise ValueError(f"文件 {py_file.name} 中未找到有效组件类（缺少 category 属性）")

        # 3. 【核心优化】处理 UUID 冲突但 Category 不同的情况
        current_uuid = py_file.stem
        current_category = getattr(comp_cls, 'category', 'Default')

        if current_uuid in self._uuid_map:
            existing_comp = self._uuid_map[current_uuid]
            existing_path = Path(getattr(existing_comp, '_source_file', ""))

            # 如果旧文件还活着，且路径不一样，才叫真正的冲突
            if existing_path.resolve() != py_file.resolve() and existing_path.exists():
                if existing_comp.category != current_category:
                    # 只有在这里才执行你那个重命名的逻辑
                    new_uuid = str(uuid.uuid4())
                    new_py_file = py_file.with_name(f"{new_uuid}.py")
                    logger.warning(f"检测到真实UUID冲突: {current_uuid}，正在重命名...")

                    # (执行 rename 逻辑...)
                    py_file.rename(new_py_file)
                    py_file = new_py_file
                    current_uuid = new_uuid

        # 4. 版本与历史处理
        if is_fallback:
            version = fallback_version
        else:
            histories = ComponentHistoryManager.load_histories(py_file)
            if not histories:
                component_name = getattr(comp_cls, 'name', py_file.stem)
                version = ComponentHistoryManager.save_history(py_file, component_name, clean_code)
            else:
                version = histories[-1]["version"]

        # 5. 注入元数据
        comp_cls._version = version
        comp_cls._source_file = py_file
        comp_cls._source_code = code
        comp_cls.uuid = current_uuid  # 确保使用的是最终确定的 UUID
        comp_cls._is_fallback = is_fallback

        # 加载历史数据到类属性
        hist_path = ComponentHistoryManager.get_history_file_path(py_file)
        comp_cls._history_file = []
        if hist_path.exists():
            try:
                with open(hist_path, 'r', encoding='utf-8') as f:
                    comp_cls._history_file = json.load(f)
            except Exception as e:
                logger.error(f"加载历史文件失败: {e}")

        # 6. 处理路径冲突 (Category/Name 相同但 UUID 不同)
        component_name = getattr(comp_cls, 'name', py_file.stem)
        base_full_path = f"{current_category}/{component_name}"
        full_path = base_full_path

        for existing_path, cls in comp_map.items():
            if existing_path == full_path and getattr(cls, 'uuid', None) != current_uuid:
                full_path = f"{base_full_path} ({current_uuid[:4]})"
                logger.warning(f"检测到显示路径冲突: {base_full_path}，已重命名显示名为: {full_path}")
                break

        # 7. 写入最终缓存
        comp_map[full_path] = comp_cls
        file_map[full_path] = py_file
        self._uuid_map[current_uuid] = comp_cls

        return comp_cls