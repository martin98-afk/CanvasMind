import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Callable

from PyQt5.QtCore import (
    QThread,
    pyqtSignal,
    QMutexLocker,
    QMutex,
    QObject,
    QRunnable,
    QThreadPool,
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


class _FolderSizeWorkerSignals(QObject):
    finished = pyqtSignal(str, int)


class _FolderSizeWorker(QRunnable):
    def __init__(self, folder: Path):
        super().__init__()
        self.folder = folder
        self.signals = _FolderSizeWorkerSignals()

    def run(self):
        total = 0
        try:
            for item in self.folder.rglob("*"):
                if item.is_file():
                    total += item.stat().st_size
        except Exception:
            total = 0
        self.signals.finished.emit(str(self.folder), total)


class FolderSizeCache:
    _cache: Dict[str, int] = {}
    _callbacks: Dict[str, List[Callable[[int], None]]] = {}
    _loading: Dict[str, bool] = {}
    _thread_pool = QThreadPool.globalInstance()

    @classmethod
    def get(cls, folder: Path) -> Optional[int]:
        return cls._cache.get(str(folder))

    @classmethod
    def invalidate(cls, folder: Path):
        key = str(folder)
        cls._cache.pop(key, None)
        cls._callbacks.pop(key, None)
        cls._loading.pop(key, None)

    @classmethod
    def request(cls, folder: Path, callback: Callable[[int], None]):
        key = str(folder)
        cached = cls._cache.get(key)
        if cached is not None:
            callback(cached)
            return

        cls._callbacks.setdefault(key, []).append(callback)
        if cls._loading.get(key):
            return

        cls._loading[key] = True
        worker = _FolderSizeWorker(folder)
        worker.signals.finished.connect(cls._on_finished)
        cls._thread_pool.start(worker)

    @classmethod
    def _on_finished(cls, folder_key: str, total: int):
        cls._cache[folder_key] = total
        cls._loading[folder_key] = False
        callbacks = cls._callbacks.pop(folder_key, [])
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
