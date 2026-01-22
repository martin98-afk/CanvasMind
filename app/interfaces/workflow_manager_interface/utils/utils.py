import shutil
from datetime import datetime
from pathlib import Path
from typing import List

from PyQt5.QtCore import QThread, pyqtSignal, QMutexLocker, QMutex


def _migrate_legacy_workflow_structure(workflow_dirs: List[Path]):
    """将旧版平铺结构自动迁移到新版：每个画布一个子文件夹"""
    for root in workflow_dirs:
        legacy_files = [
            f for f in root.iterdir()
            if f.is_file() and f.suffix == '.json' and f.name.endswith('.workflow.json')
        ]
        for wf_file in legacy_files:
            name = wf_file.stem
            if name.endswith('.workflow'):
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

        workflow_files = []
        file_info_map = {}
        for path in self.workflow_dir:
            if path.exists():
                workflow_files.extend(list(path.rglob("*.workflow.json")))

        for wf_path in workflow_files:
            with QMutexLocker(self._mutex):
                if self._should_stop:
                    return

            try:
                stat = wf_path.stat()
                file_info_map[str(wf_path)] = {
                    'ctime': datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M"),
                    'mtime': datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    'size_kb': stat.st_size // 1024,
                    'mtime_ts': stat.st_mtime,
                    'ctime_ts': stat.st_ctime,
                }
            except Exception:
                pass

        with QMutexLocker(self._mutex):
            if self._should_stop:
                return

        self.scan_finished.emit(workflow_files, file_info_map)