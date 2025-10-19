import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set, Optional

from PyQt5.QtCore import QEasingCurve, QTimer, QThread, Qt, pyqtSignal, QMutex, QMutexLocker
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QFileDialog, QFrame
from qfluentwidgets import (
    FlowLayout, InfoBar, FluentIcon, CardWidget, BodyLabel, SmoothScrollArea, ScrollArea
)

from app.interfaces.canvas_interface import CanvasPage
from app.utils.utils import get_icon
from app.widgets.card_widget.workflow_card import WorkflowCard
from app.widgets.dialog_widget.custom_messagebox import CustomInputDialog


class WorkflowFileInfoScanner(QThread):
    """扫描工作流文件信息的线程"""
    scan_finished = pyqtSignal(list, dict)  # (文件列表, 文件信息)

    def __init__(self, workflow_dir: Path):
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

        if self.workflow_dir.exists():
            workflow_files = list(self.workflow_dir.glob("*.workflow.json"))
            workflow_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

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
                        'mtime_ts': stat.st_mtime  # 用于排序
                    }
                except Exception:
                    pass

        with QMutexLocker(self._mutex):
            if self._should_stop:
                return

        self.scan_finished.emit(workflow_files, file_info_map)


class WorkflowCanvasGalleryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workflow_canvas_gallery_page")
        self.parent_window = parent
        self.workflow_dir = self._get_workflow_dir()
        self.opened_workflows = {}
        self._is_loading = False

        # === 缓存机制 ===
        self._card_map: Dict[Path, WorkflowCard] = {}  # 文件路径 -> 卡片
        self._known_files: Set[Path] = set()  # 当前已知文件集合
        self._file_info_map: Dict[str, dict] = {}  # 文件信息缓存
        self._fixed_cards: List[CardWidget] = []  # 固定卡片（新建/导入）

        # 性能优化相关
        self._refresh_pending = False
        self._current_scroll_position = 0

        self._setup_ui()
        QTimer.singleShot(50, self.load_workflows)

    def _get_workflow_dir(self):
        wf_dir = Path("workflows")
        wf_dir.mkdir(parents=True, exist_ok=True)
        return wf_dir

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none; background-color: transparent;")
        # 性能优化：设置滚动策略
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.scroll_widget = QWidget()
        self.scroll_widget.setStyleSheet("background-color: transparent;")

        # 关键：禁用动画以提升批量操作性能
        self.flow_layout = FlowLayout(self.scroll_widget, needAni=False)  # 禁用动画
        self.flow_layout.setContentsMargins(30, 30, 30, 30)
        self.flow_layout.setVerticalSpacing(20)
        self.flow_layout.setHorizontalSpacing(30)

        self.scroll_area.setWidget(self.scroll_widget)
        layout.addWidget(self.scroll_area)

    def _open_workflow_dir(self):
        try:
            if os.name == 'nt':
                os.startfile(self.workflow_dir)
            else:
                subprocess.call(['xdg-open', self.workflow_dir])
        except Exception:
            pass

    def _schedule_refresh(self):
        """防抖刷新，避免频繁触发"""
        if not hasattr(self, '_refresh_timer'):
            self._refresh_timer = QTimer(self)
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.timeout.connect(self._load_workflows_safe)
        self._refresh_timer.start(150)  # 增加到150ms防抖，减少频繁刷新

    def _load_workflows_safe(self):
        """安全的加载工作流，避免重复加载"""
        if not self._refresh_pending:
            self._refresh_pending = True
            self.load_workflows()
            self._refresh_pending = False

    def load_workflows(self):
        if self._is_loading:
            # 如果正在加载，取消之前的扫描并重新开始
            if hasattr(self, '_scanner') and hasattr(self, '_thread'):
                try:
                    self._scanner.stop()
                    self._thread.quit()
                    self._thread.wait(100)  # 等待最多100ms
                except:
                    pass
            return

        self._is_loading = True

        # 启动后台扫描
        self._scanner = WorkflowFileInfoScanner(self.workflow_dir)
        self._thread = QThread()
        self._scanner.moveToThread(self._thread)
        self._thread.started.connect(self._scanner.run)
        self._scanner.scan_finished.connect(self._on_detailed_scan_finished)
        self._scanner.scan_finished.connect(self._thread.quit)
        self._scanner.scan_finished.connect(self._scanner.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _create_new_card(self):
        new_card = CardWidget()
        new_card.setFixedSize(320, 300)
        new_card.setBorderRadius(12)
        layout = QVBoxLayout(new_card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        icon = FluentIcon.ADD.icon()
        plus_label = QLabel()
        plus_label.setPixmap(icon.pixmap(64, 64))
        plus_label.setAlignment(Qt.AlignCenter)

        text_label = BodyLabel("新建画布")
        text_label.setAlignment(Qt.AlignCenter)

        layout.addStretch()
        layout.addWidget(plus_label)
        layout.addSpacing(40)
        layout.addWidget(text_label)
        layout.addStretch()

        new_card.mousePressEvent = lambda e: self.new_canvas()
        new_card.setCursor(Qt.PointingHandCursor)
        return new_card

    def _create_import_card(self):
        import_card = CardWidget()
        import_card.setFixedSize(320, 300)
        import_card.setBorderRadius(12)
        layout = QVBoxLayout(import_card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        icon = FluentIcon.FOLDER_ADD.icon()
        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(64, 64))
        icon_label.setAlignment(Qt.AlignCenter)

        text_label = BodyLabel("导入画布")
        text_label.setAlignment(Qt.AlignCenter)

        layout.addStretch()
        layout.addWidget(icon_label)
        layout.addSpacing(40)
        layout.addWidget(text_label)
        layout.addStretch()

        import_card.mousePressEvent = lambda e: self.import_canvas()
        import_card.setCursor(Qt.PointingHandCursor)
        return import_card

    def _on_detailed_scan_finished(self, workflow_files: List[Path], file_info_map: dict):
        self._is_loading = False

        # 检查是否有新的扫描任务在等待，如果有则取消当前处理
        if hasattr(self, '_refresh_timer') and self._refresh_timer.isActive():
            return

        self._file_info_map = file_info_map

        current_files = set(workflow_files)
        old_files = self._known_files.copy()  # 使用副本避免在迭代时修改

        # 1. 处理删除文件（先删除）
        deleted_files = old_files - current_files
        for wf_path in deleted_files:
            card = self._card_map.pop(wf_path, None)
            if card:
                self.flow_layout.removeWidget(card)
                card.deleteLater()

        # 2. 处理新增文件
        new_files = current_files - old_files
        cards_to_add = []
        for wf_path in new_files:
            try:
                card = WorkflowCard(wf_path, self, file_info_map.get(str(wf_path)))
                self._card_map[wf_path] = card
                cards_to_add.append((wf_path, card))
            except Exception:
                continue

        # 3. 更新已知文件集合
        self._known_files = current_files

        # 4. 批量重建布局（优化性能）
        self._batch_rebuild_layout(cards_to_add)

    def _batch_rebuild_layout(self, new_cards: List[tuple]):
        """批量重建布局，减少布局更新次数"""
        # 保存当前滚动位置
        self._current_scroll_position = self.scroll_area.verticalScrollBar().value()

        # === 批量操作：先清空再重建 ===
        # 先隐藏滚动区域以避免中间状态的布局更新
        self.scroll_area.setVisible(False)

        # 清空现有布局（但不删除卡片）
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)

        # 添加固定卡片
        if not self._fixed_cards:
            self._fixed_cards = [self._create_new_card(), self._create_import_card()]
        for card in self._fixed_cards:
            self.flow_layout.addWidget(card)

        # 添加工作流卡片（按时间排序）
        file_with_mtime = []
        for wf_path in self._known_files:
            info = self._file_info_map.get(str(wf_path))
            mtime_ts = info.get('mtime_ts', 0) if info else 0
            file_with_mtime.append((wf_path, mtime_ts))
        file_with_mtime.sort(key=lambda x: x[1], reverse=True)

        for wf_path, _ in file_with_mtime:
            card = self._card_map.get(wf_path)
            if card:
                self.flow_layout.addWidget(card)

        # 恢复可见性并更新布局
        self.scroll_area.setVisible(True)

        # 强制更新布局
        self.flow_layout.update()
        self.scroll_widget.adjustSize()

        # 恢复滚动位置
        QTimer.singleShot(0, lambda: self.scroll_area.verticalScrollBar().setValue(self._current_scroll_position))

    def open_canvas(self, file_path: Path):
        if file_path not in self.opened_workflows:
            canvas_page = CanvasPage(self.parent_window, object_name=file_path)
            canvas_page.load_full_workflow(file_path)
            canvas_page.canvas_deleted.connect(
                lambda: (
                    self.opened_workflows.pop(file_path, None),
                    self._schedule_refresh()
                )
            )
            canvas_page.canvas_saved.connect(self._on_canvas_saved)
            canvas_interface = self.parent_window.addSubInterface(
                canvas_page, get_icon("模型"), file_path.stem.split(".")[0], parent=self
            )
            canvas_interface.clicked.connect(
                lambda: (
                    canvas_page.register_components(),
                    canvas_page.nav_view.refresh_components(),
                    canvas_page._setup_pipeline_style()
                )
            )
            self.opened_workflows[file_path] = canvas_page

        self.parent_window.switchTo(self.opened_workflows[file_path])

    def new_canvas(self):
        name_dialog = CustomInputDialog("新建画布", "请输入画布名称", parent=self)
        if not name_dialog.exec():
            return
        base_name = name_dialog.get_text().strip()
        if not base_name:
            InfoBar.warning("名称无效", "画布名称不能为空", parent=self)
            return

        file_path = self.workflow_dir / f"{base_name}.workflow.json"
        counter = 1
        while file_path.exists():
            file_path = self.workflow_dir / f"{base_name}_{counter}.workflow.json"
            counter += 1

        if file_path not in self.opened_workflows:
            canvas_page = CanvasPage(self.parent_window, object_name=file_path)
            canvas_page.canvas_deleted.connect(
                lambda: (
                    self.opened_workflows.pop(file_path, None),
                    self._schedule_refresh()
                )
            )
            canvas_page.canvas_saved.connect(self._on_canvas_saved)
            canvas_interface = self.parent_window.addSubInterface(
                canvas_page, get_icon("模型"), file_path.stem.split(".")[0], parent=self)
            canvas_interface.clicked.connect(
                lambda: (
                    canvas_page.register_components(),
                    canvas_page.nav_view.refresh_components(),
                    canvas_page._setup_pipeline_style()
                )
            )
            canvas_page.create_name_label()
            self.opened_workflows[file_path] = canvas_page

        self.parent_window.switchTo(self.opened_workflows[file_path])
        self._schedule_refresh()

    def import_canvas(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择画布文件",
            "",
            "Workflow Files (*.workflow.json);;All Files (*)"
        )
        if not file_path:
            return

        src_path = Path(file_path)
        if not src_path.exists():
            InfoBar.error("文件不存在", "请选择有效的画布文件", parent=self)
            return

        base_name = src_path.stem.split(".")[0]

        dest_path = self.workflow_dir / f"{base_name}.workflow.json"
        counter = 1
        while dest_path.exists():
            dest_path = self.workflow_dir / f"{base_name}_{counter}.workflow.json"
            counter += 1

        try:
            shutil.copy2(src_path, dest_path)
            src_png = src_path.parent / f'{base_name}.png'
            if src_png.exists():
                dest_png = dest_path.parent / f'{base_name}.png'
                shutil.copy2(src_png, dest_png)

            InfoBar.success("导入成功", f"已导入 {dest_path.stem}", parent=self)
            self._schedule_refresh()

        except Exception as e:
            InfoBar.error("导入失败", str(e), parent=self)

    def duplicate_workflow(self, src_path: Path):
        dialog = CustomInputDialog("复制画布", "请输入新画布名称", src_path.stem.split(".")[0] + "_copy", self)
        if not dialog.exec():
            return
        new_name = dialog.get_text().strip()
        if not new_name:
            InfoBar.warning("名称无效", "画布名称不能为空", parent=self)
            return

        dest_path = self.workflow_dir / f"{new_name}.workflow.json"
        dest_png = self.workflow_dir / f"{new_name}.png"
        src_png = self.workflow_dir / f"{src_path.stem.split('.')[0]}.png"
        counter = 1
        base_name = new_name
        while dest_path.exists():
            new_name = f"{base_name}_{counter}"
            dest_path = self.workflow_dir / f"{new_name}.workflow.json"
            dest_png = self.workflow_dir / f"{new_name}.png"
            counter += 1

        try:
            shutil.copy2(src_path, dest_path)
            if src_png.exists():
                shutil.copy2(src_png, dest_png)
            InfoBar.success("复制成功", f"已创建 {new_name}", parent=self)
            self._schedule_refresh()
        except Exception as e:
            InfoBar.error("复制失败", str(e), parent=self)

    def delete_workflow(self, file_path: Path):
        from qfluentwidgets import MessageBox, InfoBar

        w = MessageBox("确认删除", f"确定要删除画布 \"{file_path.stem}\" 吗？\n此操作不可恢复！", self)
        if not w.exec():
            return

        try:
            file_path.unlink()
            preview_path = self.workflow_dir / f"{file_path.stem.split('.')[0]}.png"
            if preview_path.exists():
                preview_path.unlink()

            InfoBar.success("删除成功", f"画布 '{file_path.stem}' 已删除", parent=self)
            if file_path in self.opened_workflows:
                self.parent_window.removeInterface(self.opened_workflows[file_path])
                del self.opened_workflows[file_path]
            self._schedule_refresh()
        except Exception as e:
            InfoBar.error("删除失败", str(e), parent=self)

    def _on_canvas_saved(self, workflow_path: Path):
        """当画布保存完成时，刷新对应卡片的预览图"""
        card = self._card_map.get(workflow_path)
        if card and hasattr(card, 'refresh_preview'):
            card.refresh_preview()

    def resizeEvent(self, event):
        """优化窗口大小改变时的性能"""
        super().resizeEvent(event)
        # 在大小改变后延迟更新布局
        QTimer.singleShot(50, lambda: self.flow_layout.update() if hasattr(self, 'flow_layout') else None)