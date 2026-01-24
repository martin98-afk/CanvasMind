import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set

from PyQt5.QtCore import QEasingCurve, QTimer, QThread, Qt, pyqtSignal, QSize, QEvent, QObject
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QFileDialog, QFrame, QHBoxLayout
from loguru import logger
from qfluentwidgets import (
    FlowLayout, InfoBar, SmoothScrollArea,
    PipsPager, PipsScrollButtonDisplayMode, ComboBox, CaptionLabel, SearchLineEdit, TransparentToggleToolButton
)

from .constants import *
from app.interfaces.canvas_interaface import CanvasPage
from app.interfaces.workflow_manager_interface.utils.utils import _migrate_legacy_workflow_structure, \
    WorkflowFileInfoScanner, _normalize_canvas_folder
from app.scan_components import ComponentScanner
from app.scheduler.node_recommendation_engine import NodeRecommendationEngine
from app.utils.config import Settings
from app.utils.utils import get_icon, get_pinyin_search_keys
from app.interfaces.workflow_manager_interface.widgets.workflow_card import WorkflowCard, ActionCard
from app.widgets.dialog_widget.custom_messagebox import CustomInputDialog



class WorkflowCanvasGalleryPage(QWidget, QObject):
    scan_finished = pyqtSignal(list, dict)
    component_code_changed = pyqtSignal(str, str)
    exported_projects_changed = pyqtSignal(str, str)
    running_projects_changed = pyqtSignal(str, str)
    node_request_edit = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workflow_canvas_gallery_page")
        self.config = Settings.get_instance()
        self.parent_window = parent
        self._pinyin_cache = {}
        self.opened_workflows = {}
        self._is_loading = False
        self._filter_text = ""
        self.page_size = 12
        self.fixed_card_count = 1
        self.current_page = 0
        self.total_pages = 1
        self.all_workflow_paths: List[Path] = []
        self._card_map: Dict[Path, WorkflowCard] = {}
        self._known_files: Set[Path] = set()
        self._file_info_map: Dict[str, dict] = {}
        self._fixed_card: ActionCard = None
        self._refresh_pending = False
        self.recommendation_engine = NodeRecommendationEngine()
        self._last_wheel_time = 0
        self._wheel_threshold = 100

        self._setup_ui()
        self._create_fixed_card()
        self.build_recommendation_engine()
        self.load_workflows()

    def _create_fixed_card(self):
        if self._fixed_card is None:
            self._fixed_card = ActionCard(parent=self)

    def _get_workflow_dir(self):
        wf_dirs = []
        for path in self.config.workflow_paths.value:
            path = Path(path)
            path.mkdir(parents=True, exist_ok=True)
            wf_dirs.append(path)
        return wf_dirs

    def get_recommendations_for_node(self, node_full_path: str):
        if not self.recommendation_engine:
            return []
        return self.recommendation_engine.get_recommendations_sync(node_full_path)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(16)
        top_bar.setContentsMargins(50, 0, 70, 0)

        # 国际化标签
        sort_label = CaptionLabel(self.tr("排序字段："), self)
        self.sort_field_combo = ComboBox(self)
        self.sort_field_combo.addItems([
            self.tr("修改时间"),
            self.tr("创建时间"),
            self.tr("画布名称")
        ])
        self.sort_field_combo.setCurrentIndex(0)
        self.sort_field_combo.setFixedWidth(100)
        self.sort_field_combo.currentIndexChanged.connect(self._on_sort_changed)

        self.sort_order_button = TransparentToggleToolButton(self)
        self.sort_order_button.setIcon(get_icon("降序"))
        self.sort_order_button.setIconSize(QSize(20, 20))
        self.sort_order_button.setChecked(False)
        self.sort_order_button.setToolTip(self.tr("点击切换排序方向"))
        self.sort_order_button.clicked.connect(self._on_sort_order_changed)

        self.search_line_edit = SearchLineEdit(self)
        self.search_line_edit.setPlaceholderText(self.tr("搜索画布名称..."))
        self.search_line_edit.setFixedWidth(220)
        self.search_line_edit.textChanged.connect(self._on_search_changed)
        self.search_line_edit.searchSignal.connect(self._on_search_changed)
        self.search_line_edit.clearSignal.connect(self._on_search_changed)

        top_bar.addStretch()
        top_bar.addWidget(self.search_line_edit)
        top_bar.addWidget(sort_label)
        top_bar.addWidget(self.sort_field_combo)
        top_bar.addWidget(self.sort_order_button)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)

        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none; background-color: transparent;")
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.viewport().installEventFilter(self)

        self.scroll_widget = QWidget()
        self.scroll_widget.setStyleSheet("background-color: transparent;")

        self.flow_layout = FlowLayout(self.scroll_widget, needAni=True)
        self.flow_layout.setAnimation(250, QEasingCurve.OutQuad)
        self.flow_layout.setContentsMargins(30, 30, 30, 30)
        self.flow_layout.setVerticalSpacing(20)
        self.flow_layout.setHorizontalSpacing(30)

        self.scroll_area.setWidget(self.scroll_widget)

        self.pips_pager = PipsPager(Qt.Vertical)
        self.pips_pager.setPageNumber(1)
        self.pips_pager.currentIndexChanged.connect(self._on_page_changed)
        self.pips_pager.setNextButtonDisplayMode(PipsScrollButtonDisplayMode.ALWAYS)
        self.pips_pager.setPreviousButtonDisplayMode(PipsScrollButtonDisplayMode.ALWAYS)
        self.pips_pager.setFixedWidth(10)

        content_layout.addWidget(self.scroll_area, 1)
        content_layout.addWidget(self.pips_pager, 0)

        main_layout.addLayout(top_bar)
        main_layout.addLayout(content_layout)

    def eventFilter(self, obj, event):
        if obj == self.scroll_area.viewport() and event.type() == QEvent.Wheel:
            from PyQt5.QtCore import QTime
            current_time = QTime.currentTime().msecsSinceStartOfDay()
            if current_time - self._last_wheel_time < self._wheel_threshold:
                return True
            self._last_wheel_time = current_time

            scrollbar = self.scroll_area.verticalScrollBar()
            current_value = scrollbar.value()
            max_value = scrollbar.maximum()
            min_value = scrollbar.minimum()

            if (current_value >= max_value - 5 and event.angleDelta().y() < 0) or \
                    (max_value == 0 and event.angleDelta().y() < 0 and self.current_page < self.total_pages - 1):
                if self.current_page < self.total_pages - 1:
                    new_page_index = self.current_page + 1
                    self.pips_pager.setCurrentIndex(new_page_index)
                    QTimer.singleShot(5, lambda: scrollbar.setValue(min_value))
                    return True

            elif (current_value <= min_value + 5 and event.angleDelta().y() > 0) or \
                    (max_value == 0 and event.angleDelta().y() > 0 and self.current_page > 0):
                if self.current_page > 0:
                    new_page_index = self.current_page - 1
                    self.pips_pager.setCurrentIndex(new_page_index)
                    QTimer.singleShot(5, lambda: scrollbar.setValue(scrollbar.maximum()))
                    return True

        return super().eventFilter(obj, event)

    def build_recommendation_engine(self):
        component_map, _ = ComponentScanner().get_components()
        self.recommendation_engine._recommendation_cache.clear()
        self.recommendation_engine._build_index(component_map)

    def _on_sort_order_changed(self):
        is_ascending = self.sort_order_button.isChecked()
        if is_ascending:
            self.sort_order_button.setIcon(get_icon("升序"))
            self.sort_order_button.setToolTip(self.tr("当前：升序（点击切换为降序）"))
        else:
            self.sort_order_button.setIcon(get_icon("降序"))
            self.sort_order_button.setToolTip(self.tr("当前：降序（点击切换为升序）"))
        self._on_sort_changed()

    def _calculate_cards_per_page(self) -> int:
        if not self.scroll_area or self.scroll_area.viewport().width() <= 0:
            return 12

        card_width = 320
        if self._card_map:
            sample_card = next(iter(self._card_map.values()))
            if sample_card.width() > 50:
                card_width = sample_card.width()
        elif self._fixed_card and self._fixed_card.width() > 50:
            card_width = self._fixed_card.width()

        margins = self.flow_layout.contentsMargins()
        spacing = self.flow_layout.horizontalSpacing()
        available_width = self.scroll_area.viewport().width() - margins.left() - margins.right()

        if available_width <= card_width:
            cards_per_row = 1
        else:
            cards_per_row = max(1, int((available_width + spacing) / (card_width + spacing)))

        return cards_per_row * 3

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
        self.workflow_dir = self._get_workflow_dir()
        _migrate_legacy_workflow_structure(self.workflow_dir)

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

        old_file_info_map = self._file_info_map.copy()
        self._file_info_map = file_info_map
        self._known_files = set(workflow_files)

        for wf_path in workflow_files:
            if wf_path not in self._card_map:
                try:
                    card = WorkflowCard(wf_path, self, self._file_info_map.get(str(wf_path)))
                    card.hide()
                    self._card_map[wf_path] = card
                except Exception:
                    import traceback
                    traceback.print_exc()

        for wf_path, card in self._card_map.items():
            old_info = old_file_info_map.get(str(wf_path))
            new_info = self._file_info_map.get(str(wf_path))
            if old_info and new_info:
                if (old_info.get('mtime_ts') != new_info.get('mtime_ts') or
                        old_info.get('ctime_ts') != new_info.get('ctime_ts')):
                    card.update_file_info(new_info)
            elif new_info:
                card.update_file_info(new_info)

        self._apply_sort_and_filter_and_refresh()
        self.scan_finished.emit(workflow_files, file_info_map)

    def _show_page(self, page_index: int):
        self.current_page = page_index

        if self._fixed_card is None:
            self._create_fixed_card()

        self._fixed_card.hide()
        for card in self._card_map.values():
            card.hide()

        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)

        if page_index == 0:
            self.flow_layout.addWidget(self._fixed_card)
            self._fixed_card.show()

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

    def _on_search_changed(self, text: str):
        self._filter_text = text.strip().lower()
        self._apply_sort_and_filter_and_refresh()

    def _on_sort_changed(self, index=None):
        self._apply_sort_and_filter_and_refresh()

    def _apply_sort_and_filter_and_refresh(self):
        if self._is_loading:
            return

        if not self._known_files:
            self.all_workflow_paths = []
        else:
            field_index = self.sort_field_combo.currentIndex()
            is_ascending = self.sort_order_button.isChecked()

            file_with_info = []
            for wf_path in self._known_files:
                info = self._file_info_map.get(str(wf_path), {})
                ctime_ts = info.get('ctime_ts', 0)
                mtime_ts = info.get('mtime_ts', 0)
                name = wf_path.parent.name
                if self._filter_text:
                    if name not in self._pinyin_cache:
                        self._pinyin_cache[name] = get_pinyin_search_keys(name)

                    search_keys = self._pinyin_cache[name]
                    if self._filter_text not in search_keys:
                        continue

                file_with_info.append((wf_path, ctime_ts, mtime_ts, name))

            if field_index == 0:
                key_func = lambda x: x[2]
            elif field_index == 1:
                key_func = lambda x: x[1]
            else:
                key_func = lambda x: x[3].lower()

            file_with_info.sort(key=key_func, reverse=not is_ascending)
            self.all_workflow_paths = [item[0] for item in file_with_info]

        self.page_size = self._calculate_cards_per_page()
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(100, self._on_resize)

    def _on_resize(self):
        if self._is_loading:
            return
        new_page_size = self._calculate_cards_per_page()
        if new_page_size != self.page_size:
            self.page_size = new_page_size
            self._apply_sort_and_filter_and_refresh()

    # ================== 业务逻辑 ==================

    def open_canvas(self, file_path: Path):
        if file_path not in self.opened_workflows:
            canvas_page = CanvasPage(self.parent_window, object_name=file_path, manager=self)
            canvas_page.load_full_workflow(file_path)
            canvas_page.canvas_deleted.connect(
                lambda: (
                    self.opened_workflows.pop(file_path, None),
                    self._schedule_refresh()
                )
            )
            canvas_page.canvas_saved.connect(self._on_canvas_saved)
            # "模型" 是图标名，通常不需要翻译，但 label 参数 file_path.parent.name 是动态的
            self.parent_window.addSubInterface(canvas_page, get_icon("模型"), file_path.parent.name, parent=self)
            self.opened_workflows[file_path] = canvas_page

        self.parent_window.switchTo(self.opened_workflows[file_path])

    def new_canvas(self, window=None, from_template=False):
        name_dialog = CustomInputDialog(self.tr("新建画布"), self.tr("请输入画布名称"), parent=window or self)
        if not name_dialog.exec():
            return
        base_name = name_dialog.get_text().strip()
        if not base_name:
            InfoBar.warning(self.tr("名称无效"), self.tr("画布名称不能为空"), parent=window or self)
            return

        counter = 0
        while True:
            canvas_folder = self.workflow_dir[0] / (base_name if counter == 0 else f"{base_name}_{counter}")
            if not (canvas_folder / f"{base_name}.workflow.json").exists():
                break
            counter += 1

        canvas_folder.mkdir(parents=True, exist_ok=True)
        file_path = canvas_folder / f"{canvas_folder.name}.workflow.json"

        if file_path not in self.opened_workflows:
            canvas_page = CanvasPage(self.parent_window, object_name=file_path, manager=self)
            canvas_page.create_name_label()
            canvas_page._deferred_initialization(),
            canvas_page.environment_manager.load_env_combos()
            canvas_page.property_panel.set_allowed_update(True)
            canvas_page.property_panel.update_properties(None)
            canvas_page.canvas_deleted.connect(
                lambda: (
                    self.opened_workflows.pop(file_path, None),
                    self._schedule_refresh()
                )
            )
            canvas_page.canvas_saved.connect(self._on_canvas_saved)
            if from_template:
                canvas_page.start_from_template()
            self.parent_window.addSubInterface(canvas_page, get_icon("模型"), file_path.parent.name, parent=self)
            self.opened_workflows[file_path] = canvas_page

        self.parent_window.switchTo(self.opened_workflows[file_path])
        self._schedule_refresh()

    def import_canvas(self):
        folder_path = QFileDialog.getExistingDirectory(
            self,
            self.tr("选择要导入的画布文件夹"),
            str(self.workflow_dir[0])
        )
        if not folder_path:
            return

        src_folder = Path(folder_path)
        if not src_folder.is_dir():
            InfoBar.error(self.tr("无效目录"), self.tr("请选择有效的画布文件夹"), parent=self)
            return

        wf_files = list(src_folder.glob("*.workflow.json"))
        if not wf_files:
            InfoBar.error(self.tr("无效画布"), self.tr("所选文件夹中未找到 .workflow.json 文件"), parent=self)
            return

        base_name = src_folder.name
        counter = 0
        while True:
            dest_folder = self.workflow_dir[0] / (base_name if counter == 0 else f"{base_name}_{counter}")
            if not dest_folder.exists():
                break
            counter += 1

        try:
            shutil.copytree(src_folder, dest_folder)
            _normalize_canvas_folder(dest_folder)

            now = datetime.now().timestamp()
            for f in dest_folder.iterdir():
                if f.is_file():
                    os.utime(f, (now, now))

            InfoBar.success(self.tr("导入成功"), self.tr("已导入画布 “{}”").format(dest_folder.name), parent=self)
            self._schedule_refresh()

        except Exception as e:
            InfoBar.error(self.tr("导入失败"), self.tr("无法复制文件夹：{}").format(e), parent=self)

    def edit_workflow(self, src_path: Path):
        src_folder = src_path.parent
        old_name = src_folder.name

        dialog = CustomInputDialog(self.tr("重命名画布"), self.tr("请输入新名称"), old_name, self)
        if not dialog.exec():
            return
        new_name = dialog.get_text().strip()
        if not new_name:
            InfoBar.warning(self.tr("名称无效"), self.tr("画布名称不能为空"), parent=self)
            return

        counter = 0
        while True:
            new_folder = self.workflow_dir[0] / (new_name if counter == 0 else f"{new_name}_{counter}")
            if not new_folder.exists():
                break
            counter += 1

        try:
            shutil.move(str(src_folder), str(new_folder))
            _normalize_canvas_folder(new_folder)

            if src_path in self.opened_workflows:
                self.parent_window.removeInterface(self.opened_workflows[src_path])
                del self.opened_workflows[src_path]

            if src_path in self._card_map:
                old_card = self._card_map.pop(src_path)
                self.flow_layout.removeWidget(old_card)
                old_card.hide()
                old_card.deleteLater()

            old_name_key = src_path.parent.name
            if old_name_key in self._pinyin_cache:
                del self._pinyin_cache[old_name_key]

            InfoBar.success(self.tr("重命名成功"), self.tr("已重命名为 {}").format(new_name), parent=self)
            self._schedule_refresh()
        except Exception as e:
            InfoBar.error(self.tr("重命名失败"), str(e), parent=self)

    def duplicate_workflow(self, src_path: Path):
        src_folder = src_path.parent
        old_name = src_folder.name

        dialog = CustomInputDialog(self.tr("复制画布"), self.tr("请输入新画布名称"), old_name + "_copy", self)
        if not dialog.exec():
            return
        new_name = dialog.get_text().strip()
        if not new_name:
            InfoBar.warning(self.tr("名称无效"), self.tr("画布名称不能为空"), parent=self)
            return

        counter = 0
        while True:
            new_folder = self.workflow_dir[0] / (new_name if counter == 0 else f"{new_name}_{counter}")
            if not new_folder.exists():
                break
            counter += 1

        try:
            shutil.copytree(src_folder, new_folder)
            _normalize_canvas_folder(new_folder)

            InfoBar.success(self.tr("复制成功"), self.tr("已创建 {}").format(new_name), parent=self)
            self._schedule_refresh()
        except Exception as e:
            InfoBar.error(self.tr("复制失败"), str(e), parent=self)

    def delete_workflow(self, file_path: Path):
        from qfluentwidgets import MessageBox

        name = file_path.parent.name
        # 使用 tr() 格式化确认消息
        title = self.tr("确认删除")
        content = self.tr("确定要删除画布 \"{}\" 吗？\n此操作不可恢复！").format(name)

        w = MessageBox(title, content, self)
        if not w.exec():
            return

        try:
            shutil.rmtree(file_path.parent)

            InfoBar.success(self.tr("删除成功"), self.tr("画布 '{}' 已删除").format(name), parent=self)

            if file_path in self.opened_workflows:
                self.parent_window.removeInterface(self.opened_workflows[file_path])
                del self.opened_workflows[file_path]

            if file_path in self._card_map:
                old_card = self._card_map.pop(file_path)
                self.flow_layout.removeWidget(old_card)
                old_card.hide()
                old_card.deleteLater()

            self._schedule_refresh()
        except Exception as e:
            InfoBar.error(self.tr("删除失败"), str(e), parent=self)

    def _on_canvas_saved(self, workflow_path: Path):
        try:
            stat = workflow_path.stat()
            file_info = {
                'ctime': datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M"),
                'mtime': datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                'size_kb': stat.st_size // 1024,
                'mtime_ts': stat.st_mtime,
                'ctime_ts': stat.st_ctime,
            }
            self._file_info_map[str(workflow_path)] = file_info
            card = self._card_map.get(workflow_path)
            if card:
                card.update_file_info(file_info)
        except Exception as e:
            logger.error(f"Update card info failed: {e}")

        card = self._card_map.get(workflow_path)
        if card and hasattr(card, 'refresh_preview'):
            card.refresh_preview()