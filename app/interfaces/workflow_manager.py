import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set, Optional

from PyQt5.QtCore import QEasingCurve, QTimer, QThread, Qt, pyqtSignal, QMutex, QMutexLocker
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QFileDialog, QFrame, QHBoxLayout
from qfluentwidgets import (
    FlowLayout, InfoBar, FluentIcon, CardWidget, BodyLabel, SmoothScrollArea,
    PipsPager, PipsScrollButtonDisplayMode
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
        self.page_size = 12  # 初始值，会被动态覆盖
        self.fixed_card_count = 2  # 新建 + 导入
        self.current_page = 0
        self.total_pages = 1
        self.all_workflow_paths: List[Path] = []

        # === 缓存机制 ===
        self._card_map: Dict[Path, WorkflowCard] = {}
        self._known_files: Set[Path] = set()
        self._file_info_map: Dict[str, dict] = {}
        self._fixed_cards: List[CardWidget] = []

        self._refresh_pending = False

        self._setup_ui()
        QTimer.singleShot(50, self.load_workflows)

    def _get_workflow_dir(self):
        wf_dir = Path("workflows")
        wf_dir.mkdir(parents=True, exist_ok=True)
        return wf_dir

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # 左侧：卡片区域
        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none; background-color: transparent;")
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.scroll_widget = QWidget()
        self.scroll_widget.setStyleSheet("background-color: transparent;")

        self.flow_layout = FlowLayout(self.scroll_widget, needAni=True)
        self.flow_layout.setAnimation(250, QEasingCurve.OutQuad)
        self.flow_layout.setContentsMargins(30, 30, 30, 30)
        self.flow_layout.setVerticalSpacing(20)
        self.flow_layout.setHorizontalSpacing(30)

        self.scroll_area.setWidget(self.scroll_widget)

        # 右侧：竖向分页器
        self.pips_pager = PipsPager(Qt.Vertical)
        self.pips_pager.setPageNumber(1)
        self.pips_pager.currentIndexChanged.connect(self._on_page_changed)
        self.pips_pager.setNextButtonDisplayMode(PipsScrollButtonDisplayMode.ALWAYS)
        self.pips_pager.setPreviousButtonDisplayMode(PipsScrollButtonDisplayMode.ALWAYS)
        self.pips_pager.setFixedWidth(10)

        main_layout.addWidget(self.scroll_area, 1)
        main_layout.addWidget(self.pips_pager, 0)

    def _calculate_cards_per_page(self) -> int:
        """动态计算每页卡片数（3 行）"""
        if not self.scroll_area or self.scroll_area.viewport().width() <= 0:
            return 12

        # 获取卡片宽度（优先工作流卡片，其次固定卡片）
        card_width = 320  # 默认值
        if self._card_map:
            sample_card = next(iter(self._card_map.values()))
            if sample_card.width() > 50:  # 合理最小值
                card_width = sample_card.width()
        elif self._fixed_cards and self._fixed_cards[0].width() > 50:
            card_width = self._fixed_cards[0].width()

        # 计算可用宽度
        margins = self.flow_layout.contentsMargins()
        spacing = self.flow_layout.horizontalSpacing()
        available_width = self.scroll_area.viewport().width() - margins.left() - margins.right()

        if available_width <= card_width:
            cards_per_row = 1
        else:
            # 公式: n * card_width + (n - 1) * spacing <= available_width
            cards_per_row = max(1, int((available_width + spacing) / (card_width + spacing)))

        return cards_per_row * 3  # 3 行

    def _schedule_refresh(self):
        if not hasattr(self, '_refresh_timer'):
            self._refresh_timer = QTimer(self)
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.timeout.connect(self._load_workflows_safe)
        self._refresh_timer.start(150)

    def _load_workflows_safe(self):
        if not self._refresh_pending:
            self._refresh_pending = True
            self.load_workflows()
            self._refresh_pending = False

    def load_workflows(self):
        if self._is_loading:
            if hasattr(self, '_scanner') and hasattr(self, '_thread'):
                try:
                    self._scanner.stop()
                    self._thread.quit()
                    self._thread.wait(100)
                except:
                    pass
            return

        self._is_loading = True
        self._scanner = WorkflowFileInfoScanner(self.workflow_dir)
        self._thread = QThread()
        self._scanner.moveToThread(self._thread)
        self._thread.started.connect(self._scanner.run)
        self._scanner.scan_finished.connect(self._on_detailed_scan_finished)
        self._scanner.scan_finished.connect(self._thread.quit)
        self._scanner.scan_finished.connect(self._scanner.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_detailed_scan_finished(self, workflow_files: List[Path], file_info_map: dict):
        self._is_loading = False
        if hasattr(self, '_refresh_timer') and self._refresh_timer.isActive():
            return

        self._file_info_map = file_info_map
        self._known_files = set(workflow_files)

        # 按修改时间倒序：最新在最前
        file_with_mtime = []
        for wf_path in workflow_files:
            info = file_info_map.get(str(wf_path))
            mtime_ts = info.get('mtime_ts', 0) if info else 0
            file_with_mtime.append((wf_path, mtime_ts))
        file_with_mtime.sort(key=lambda x: x[1], reverse=True)
        self.all_workflow_paths = [wf for wf, _ in file_with_mtime]

        # 创建缺失的卡片
        for wf_path in self.all_workflow_paths:
            if wf_path not in self._card_map:
                try:
                    card = WorkflowCard(wf_path, self, self._file_info_map.get(str(wf_path)))
                    card.hide()
                    self._card_map[wf_path] = card
                except Exception:
                    import traceback
                    traceback.print_exc()

        # 创建固定卡片（仅一次）
        if not self._fixed_cards:
            self._fixed_cards = [
                WorkflowCard(parent=self, type="create"),
                WorkflowCard(parent=self, type="import")
            ]
            for card in self._fixed_cards:
                card.hide()

        self._ensure_all_cards_in_layout()

        # ✅ 动态计算每页卡片数（3 行）
        self.page_size = self._calculate_cards_per_page()

        # 重新计算分页（考虑固定卡片只在第一页）
        total_workflow = len(self.all_workflow_paths)
        if total_workflow == 0:
            self.total_pages = 1
        else:
            first_page_workflow_slots = max(0, self.page_size - self.fixed_card_count)
            if first_page_workflow_slots <= 0:
                self.total_pages = 1
            else:
                remaining = total_workflow - first_page_workflow_slots
                if remaining <= 0:
                    self.total_pages = 1
                else:
                    self.total_pages = 1 + ((remaining + self.page_size - 1) // self.page_size)

        self.pips_pager.setPageNumber(self.total_pages)
        target_page = min(self.current_page, self.total_pages - 1)
        self._show_page(target_page)

    def _ensure_all_cards_in_layout(self):
        """确保所有卡片都在 flow_layout 中"""
        for card in self._fixed_cards:
            if card.parent() != self.scroll_widget:
                self.flow_layout.addWidget(card)
        for card in self._card_map.values():
            if card.parent() != self.scroll_widget:
                self.flow_layout.addWidget(card)

    def _show_page(self, page_index: int):
        self.current_page = page_index

        # 隐藏所有
        for card in self._fixed_cards:
            card.hide()
        for card in self._card_map.values():
            card.hide()

        # 清空布局
        while self.flow_layout.count():
            self.flow_layout.takeAt(0)

        if page_index == 0:
            for card in self._fixed_cards:
                self.flow_layout.addWidget(card)
                card.show()

            workflow_slots = self.page_size - self.fixed_card_count
            workflow_to_show = self.all_workflow_paths[:workflow_slots]
            for wf_path in workflow_to_show:
                card = self._card_map.get(wf_path)
                if card is not None:
                    self.flow_layout.addWidget(card)
                    card.show()
        else:
            first_page_count = max(0, self.page_size - self.fixed_card_count)
            start = first_page_count + (page_index - 1) * self.page_size
            end = start + self.page_size
            workflow_to_show = self.all_workflow_paths[start:end]
            for wf_path in workflow_to_show:
                card = self._card_map.get(wf_path)
                if card is not None:
                    self.flow_layout.addWidget(card)
                    card.show()

        self.scroll_widget.adjustSize()

    def _on_page_changed(self, index: int):
        self._show_page(index)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 延迟触发，确保布局已更新
        QTimer.singleShot(100, self._on_resize)

    def _on_resize(self):
        """窗口大小变化时重新计算分页"""
        if self._is_loading:
            return

        new_page_size = self._calculate_cards_per_page()
        if new_page_size != self.page_size:
            self.page_size = new_page_size

            # 重新计算总页数
            total_workflow = len(self.all_workflow_paths)
            if total_workflow == 0:
                self.total_pages = 1
            else:
                first_page_workflow_slots = max(0, self.page_size - self.fixed_card_count)
                if first_page_workflow_slots <= 0:
                    self.total_pages = 1
                else:
                    remaining = total_workflow - first_page_workflow_slots
                    if remaining <= 0:
                        self.total_pages = 1
                    else:
                        self.total_pages = 1 + ((remaining + self.page_size - 1) // self.page_size)

            self.pips_pager.setPageNumber(self.total_pages)
            target_page = min(self.current_page, self.total_pages - 1)
            self._show_page(target_page)

    # ================== 业务逻辑 ==================

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
        card = self._card_map.get(workflow_path)
        if card and hasattr(card, 'refresh_preview'):
            card.refresh_preview()