import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Callable

from PyQt5.QtCore import (
    QThread,
    pyqtSignal,
    QMutexLocker,
    QMutex,
    QTimer,
)
from PyQt5.QtGui import QPixmap, QPixmapCache


class ThumbnailCache:
    _cache: Dict[str, QPixmap] = {}
    _loading: Dict[str, bool] = {}

    @classmethod
    def get(cls, key: str) -> Optional[QPixmap]:
        if key in cls._cache:
            return cls._cache[key]
        return None

    @classmethod
    def put(cls, key: str, pixmap: QPixmap):
        if not pixmap.isNull():
            cls._cache[key] = pixmap
            QPixmapCache.insert(key, pixmap)

    @classmethod
    def is_loading(cls, key: str) -> bool:
        return cls._loading.get(key, False)

    @classmethod
    def set_loading(cls, key: str, loading: bool):
        cls._loading[key] = loading


class FolderSizeCache:
    _cache: Dict[str, int] = {}
    _callbacks: Dict[str, List[Callable[[int], None]]] = {}
    _pending_folders: List[Path] = []
    _batch_timer: Optional[QTimer] = None
    _batch_delay_ms = 200

    @classmethod
    def get(cls, folder: Path) -> Optional[int]:
        return cls._cache.get(str(folder))

    @classmethod
    def invalidate(cls, folder: Path):
        key = str(folder)
        cls._cache.pop(key, None)
        cls._callbacks.pop(key, None)
        cls._pending_folders = [f for f in cls._pending_folders if str(f) != key]
        if cls._batch_timer and cls._batch_timer.isActive():
            cls._batch_timer.stop()

    @classmethod
    def request(
        cls, folder: Path, callback: Callable[[int], None], delay_ms: int = None
    ):
        key = str(folder)
        cached = cls._cache.get(key)
        if cached is not None:
            callback(cached)
            return

        cls._callbacks.setdefault(key, []).append(callback)

        if any(str(f) == key for f in cls._pending_folders):
            return

        cls._pending_folders.append(folder)

        if cls._batch_timer is None:
            cls._batch_timer = QTimer()
            cls._batch_timer.setSingleShot(True)
            cls._batch_timer.timeout.connect(cls._process_batch)

        if not cls._batch_timer.isActive():
            delay = delay_ms if delay_ms is not None else cls._batch_delay_ms
            cls._batch_timer.start(delay)

    @classmethod
    def _process_batch(cls):
        folders = list(cls._pending_folders)
        cls._pending_folders.clear()

        results = []
        for folder in folders:
            key = str(folder)
            total = 0
            try:
                for item in folder.iterdir():
                    if item.is_file():
                        total += item.stat().st_size
            except Exception:
                total = -1
            results.append((key, total))

        for key, total in results:
            cls._cache[key] = total
            callbacks = cls._callbacks.pop(key, [])
            for callback in callbacks:
                try:
                    callback(total)
                except Exception:
                    pass


def iter_workflow_files(workflow_dirs: List[Path]) -> List[Path]:
    """仅扫描根目录和一级画布目录，避免深入 workspace 等大目录。"""
    workflow_files: List[Path] = []

    for root in workflow_dirs:
        if not root.exists():
            continue

        try:
            for entry in root.iterdir():
                if entry.is_file() and entry.name.endswith(".workflow.json"):
                    workflow_files.append(entry)
                    continue

                if not entry.is_dir():
                    continue

                expected = entry / f"{entry.name}.workflow.json"
                if expected.exists():
                    workflow_files.append(expected)
                    continue

                fallback = next(entry.glob("*.workflow.json"), None)
                if fallback is not None:
                    workflow_files.append(fallback)
        except Exception:
            continue

    return workflow_files


def _migrate_legacy_workflow_structure(workflow_dirs: List[Path]):
    """将旧版平铺结构自动迁移到新版：每个画布一个子文件夹"""
    for root in workflow_dirs:
        legacy_files = [
            f
            for f in root.iterdir()
            if f.is_file() and f.suffix == ".json" and f.name.endswith(".workflow.json")
        ]
        for wf_file in legacy_files:
            name = wf_file.stem
            if name.endswith(".workflow"):
                name = name[:-9]
            if not name:
                continue

            canvas_folder = root / name
            canvas_folder.mkdir(exist_ok=True)

            new_wf_path = canvas_folder / wf_file.name
            if not new_wf_path.exists():
                shutil.move(str(wf_file), str(new_wf_path))

            png_file = root / f"{name}.png"
            if png_file.exists():
                new_png_path = canvas_folder / f"{name}.png"
                if not new_png_path.exists():
                    shutil.move(str(png_file), str(new_png_path))


def _normalize_canvas_folder(folder: Path):
    """规范化画布文件夹内容"""
    if not folder.is_dir():
        return

    # 处理 .workflow.json
    wf_files = list(folder.glob("*.workflow.json"))
    if wf_files:
        expected_wf = folder / f"{folder.name}.workflow.json"
        if not expected_wf.exists():
            wf_files[0].rename(expected_wf)

    # 处理 .png
    png_files = list(folder.glob("*.png"))
    if png_files:
        expected_png = folder / f"{folder.name}.png"
        if not expected_png.exists():
            png_files[0].rename(expected_png)


class WorkflowFileInfoScanner(QThread):
    scan_finished = pyqtSignal(list, dict)

    def __init__(self, workflow_dir: List[Path]):
        super().__init__()
        self.workflow_dir = workflow_dir
        self._mutex = QMutex()
        self._should_stop = False

    def stop(self):
        with QMutexLocker(self._mutex):
            self._should_stop = True

    def run(self):
        should_stop = False
        with QMutexLocker(self._mutex):
            should_stop = self._should_stop
        if should_stop:
            return

        workflow_files = iter_workflow_files(self.workflow_dir)
        file_info_map = {}

        for wf_path in workflow_files:
            with QMutexLocker(self._mutex):
                if self._should_stop:
                    return

            try:
                stat = wf_path.stat()
                file_info_map[str(wf_path)] = {
                    "ctime": datetime.fromtimestamp(stat.st_ctime).strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                    "mtime": datetime.fromtimestamp(stat.st_mtime).strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                    "size_kb": stat.st_size // 1024,
                    "mtime_ts": stat.st_mtime,
                    "ctime_ts": stat.st_ctime,
                }
            except Exception:
                pass

        with QMutexLocker(self._mutex):
            if self._should_stop:
                return

        self.scan_finished.emit(workflow_files, file_info_map)
