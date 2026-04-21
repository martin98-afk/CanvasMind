import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set

from PyQt5.QtCore import QEasingCurve, QTimer, QThread, Qt, pyqtSignal, QSize
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QSplitter,
    QStackedWidget,
)
from loguru import logger
from qfluentwidgets import (
    FlowLayout,
    InfoBar,
    SmoothScrollArea,
    ComboBox,
    CaptionLabel,
    SearchLineEdit,
    TransparentToggleToolButton,
    SegmentedWidget,
    FluentIcon,
    TransparentPushButton,
)

from app.interfaces.canvas_interaface import CanvasPage
from app.interfaces.workflow_manager_interface.utils.utils import (
    _migrate_legacy_workflow_structure,
    WorkflowFileInfoScanner,
    _normalize_canvas_folder,
    FolderSizeCache,
)
from app.scan_components import ComponentScanner
from app.scheduler.node_recommendation_engine import NodeRecommendationEngine
from app.utils.config import Settings
from app.utils.utils import get_icon, get_pinyin_search_keys
from app.interfaces.workflow_manager_interface.widgets.workflow_card import WorkflowCard
from app.interfaces.workflow_manager_interface.widgets.workflow_list_view import (
    WorkflowListView,
)
from app.interfaces.workflow_manager_interface.widgets.workflow_preview_panel import (
    WorkflowPreviewPanel,
)
from app.widgets.dialog_widget.custom_messagebox import CustomInputDialog
from app.server_manager.cloud_bakup.canvas_cloud_manager import CanvasCloudManager

VIEW_MODE_GRID = "grid"
VIEW_MODE_LIST = "list"


class WorkflowCanvasGalleryPage(QWidget):
    GRID_INITIAL_BATCH_SIZE = 8
    GRID_INCREMENTAL_BATCH_SIZE = 6
    GRID_LOAD_MORE_THRESHOLD_PX = 600
    SORT_BY_MTIME = 0
    SORT_BY_CTIME = 1
    SORT_BY_NAME = 2
    SORT_BY_CACHE_SIZE = 3

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
        self.all_workflow_paths: List[Path] = []
        self._card_map: Dict[Path, WorkflowCard] = {}
        self._known_files: Set[Path] = set()
        self._file_info_map: Dict[str, dict] = {}
        self._refresh_pending = False
        self._recommendation_engine_built = False
        self._recommendation_engine = None
        self._canvas_cloud_mgr = CanvasCloudManager()
        self._grid_render_count = 0
        self._grid_batch_inflight = False
        self._cache_size_refresh_timer = QTimer(self)
        self._cache_size_refresh_timer.setSingleShot(True)
        self._cache_size_refresh_timer.timeout.connect(
            self._refresh_after_cache_size_update
        )

        self._view_mode = VIEW_MODE_GRID
        self._setup_ui()
        self.load_workflows()

    def _get_workflow_dir(self):
        wf_dirs = []
        for path in self.config.workflow_paths.value:
            path = Path(path)
            path.mkdir(parents=True, exist_ok=True)
            wf_dirs.append(path)
        return wf_dirs

    def get_recommendations_for_node(self, node_full_path: str):
        if not self._recommendation_engine:
            return []
        return self._recommendation_engine.get_recommendations_sync(node_full_path)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.addSpacing(60)
        self.search_line_edit = SearchLineEdit(self)
        self.search_line_edit.setPlaceholderText(self.tr("搜索..."))
        self.search_line_edit.setFixedWidth(350)
        self._search_debounce_timer = QTimer(self)
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.timeout.connect(self._do_search)
        self.search_line_edit.textChanged.connect(self._on_search_changed)
        self.search_line_edit.searchSignal.connect(self._on_search_changed)
        self.search_line_edit.clearSignal.connect(self._on_search_changed)
        top_bar.addWidget(self.search_line_edit)

        self.sort_field_combo = ComboBox(self)
        self.sort_field_combo.addItems(
            [
                self.tr("修改时间"),
                self.tr("创建时间"),
                self.tr("名称"),
                self.tr("缓存大小"),
            ]
        )
        self.sort_field_combo.setCurrentIndex(0)
        self.sort_field_combo.currentIndexChanged.connect(self._on_sort_changed)
        top_bar.addWidget(self.sort_field_combo)

        self.sort_order_button = TransparentToggleToolButton(self)
        self.sort_order_button.setIcon(get_icon("降序"))
        self.sort_order_button.setIconSize(QSize(16, 16))
        self.sort_order_button.setChecked(False)
        self.sort_order_button.setToolTip(self.tr("降序"))
        self.sort_order_button.clicked.connect(self._on_sort_order_changed)
        top_bar.addWidget(self.sort_order_button)
        self.view_segment = SegmentedWidget(self)
        self.view_segment.setFixedHeight(28)
        self.view_segment.setFixedWidth(120)
        self.view_segment.addItem("grid", self.tr("网格"), icon=get_icon("网格"))
        self.view_segment.addItem("list", self.tr("列表"), icon=get_icon("列表"))
        self.view_segment.setCurrentItem("grid")
        self.view_segment.currentItemChanged.connect(self._on_view_mode_changed)
        top_bar.addSpacing(8)
        top_bar.addWidget(self.view_segment)

        top_bar.addStretch()
        self.new_btn = TransparentPushButton(self.tr("新建画布"), self, FluentIcon.ADD)
        self.new_btn.setIconSize(QSize(20, 20))
        self.new_btn.clicked.connect(lambda: self.new_canvas())
        top_bar.addWidget(self.new_btn)

        self.template_btn = TransparentPushButton(
            self.tr("从模板创建"), self, FluentIcon.DOWNLOAD
        )
        self.template_btn.setIconSize(QSize(20, 20))
        self.template_btn.clicked.connect(lambda: self.new_canvas(from_template=True))
        top_bar.addWidget(self.template_btn)

        self.import_btn = TransparentPushButton(
            self.tr("导入画布"), self, get_icon("导入文件")
        )
        self.import_btn.setIconSize(QSize(20, 20))
        self.import_btn.clicked.connect(lambda: self.import_canvas())
        top_bar.addWidget(self.import_btn)
        top_bar.addSpacing(150)

        status_bar = QHBoxLayout()
        status_bar.setSpacing(12)
        status_bar.setContentsMargins(60, 0, 0, 0)
        self.status_label = CaptionLabel(self.tr("准备就绪"))
        self.status_label.setStyleSheet("color: #8a8f99;")
        status_bar.addWidget(self.status_label)
        status_bar.addStretch()
        self.grid_container = QWidget()
        self.grid_layout = QVBoxLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none; background-color: transparent;")
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.scroll_widget = QWidget()
        self.scroll_widget.setStyleSheet("background-color: transparent;")

        self.flow_layout = FlowLayout(self.scroll_widget, needAni=False)
        # self.flow_layout.setAnimation(250, QEasingCurve.OutQuad)
        self.flow_layout.setContentsMargins(30, 30, 30, 30)
        self.flow_layout.setVerticalSpacing(20)
        self.flow_layout.setHorizontalSpacing(30)

        self.scroll_area.setWidget(self.scroll_widget)
        self.grid_layout.addWidget(self.scroll_area)
        self.scroll_area.verticalScrollBar().valueChanged.connect(
            self._on_grid_scroll_changed
        )
        self.scroll_area.verticalScrollBar().rangeChanged.connect(
            self._on_grid_scroll_range_changed
        )

        self.list_container = QWidget()
        self.list_container.hide()
        self.list_layout = QHBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)

        self.workflow_list_view = WorkflowListView(self)
        self.workflow_list_view.current_changed.connect(self._on_list_selection_changed)

        self.preview_panel = WorkflowPreviewPanel(self)
        self.preview_panel.setMinimumWidth(400)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.workflow_list_view)
        splitter.addWidget(self.preview_panel)
        splitter.setSizes([600, 300])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        self.list_layout.addWidget(splitter)

        self.content_container = QStackedWidget()
        self.content_container.addWidget(self.grid_container)
        self.content_container.addWidget(self.list_container)

        main_layout.addLayout(top_bar)
        main_layout.addLayout(status_bar)
        main_layout.addWidget(self.content_container, 1)

    def _on_view_mode_changed(self, mode: str):
        if mode == "grid":
            self._view_mode = VIEW_MODE_GRID
            self.content_container.setCurrentWidget(self.grid_container)
            QTimer.singleShot(10, self._refresh_grid_view)
        else:
            self._view_mode = VIEW_MODE_LIST
            self.content_container.setCurrentWidget(self.list_container)
            QTimer.singleShot(10, self._refresh_list_view)

    def _on_list_selection_changed(self, workflow_path: Path):
        file_info = self._file_info_map.get(str(workflow_path))
        self.preview_panel.set_workflow(workflow_path, file_info)

    def build_recommendation_engine(self):
        if self._recommendation_engine_built:
            return
        self._recommendation_engine_built = True
        self._recommendation_engine = NodeRecommendationEngine()
        component_map, _ = ComponentScanner().get_components()
        self._recommendation_engine._recommendation_cache.clear()
        self._recommendation_engine._build_index(component_map)

    def _on_sort_order_changed(self):
        is_ascending = self.sort_order_button.isChecked()
        if is_ascending:
            self.sort_order_button.setIcon(get_icon("升序"))
            self.sort_order_button.setToolTip(self.tr("当前：升序（点击切换为降序）"))
        else:
            self.sort_order_button.setIcon(get_icon("降序"))
            self.sort_order_button.setToolTip(self.tr("当前：降序（点击切换为升序）"))
        self._on_sort_changed()

    def _schedule_refresh(self):
        if not hasattr(self, "_refresh_timer"):
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
        self._update_status_label(extra_text=self.tr("扫描中..."))

        if self._is_loading:
            if hasattr(self, "_scanner") and hasattr(self, "_thread"):
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

    def _on_detailed_scan_finished(
        self, workflow_files: List[Path], file_info_map: dict
    ):
        self._is_loading = False
        if hasattr(self, "_refresh_timer") and self._refresh_timer.isActive():
            return

        old_file_info_map = self._file_info_map.copy()
        self._file_info_map = file_info_map
        self._known_files = set(workflow_files)

        removed_paths = [
            path for path in self._card_map if path not in self._known_files
        ]
        for wf_path in removed_paths:
            card = self._card_map.pop(wf_path, None)
            if card is not None:
                self.flow_layout.removeWidget(card)
                card.hide()
                card.deleteLater()

        for wf_path, card in self._card_map.items():
            old_info = old_file_info_map.get(str(wf_path))
            new_info = self._file_info_map.get(str(wf_path))
            if old_info and new_info:
                if old_info.get("mtime_ts") != new_info.get("mtime_ts") or old_info.get(
                    "ctime_ts"
                ) != new_info.get("ctime_ts"):
                    card.update_file_info(new_info)
            elif new_info:
                card.update_file_info(new_info)

        QTimer.singleShot(0, lambda: self._request_cache_sizes(workflow_files))
        QTimer.singleShot(0, lambda: self._apply_sort_and_filter_and_refresh())
        QTimer.singleShot(500, self.build_recommendation_engine)
        self.scan_finished.emit(workflow_files, file_info_map)

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
                ctime_ts = info.get("ctime_ts", 0)
                mtime_ts = info.get("mtime_ts", 0)
                cache_size = info.get("folder_size_bytes", -1)
                name = wf_path.parent.name
                if self._filter_text:
                    if name not in self._pinyin_cache:
                        self._pinyin_cache[name] = get_pinyin_search_keys(name)

                    search_keys = self._pinyin_cache[name]
                    if self._filter_text not in search_keys:
                        continue

                file_with_info.append((wf_path, ctime_ts, mtime_ts, name, cache_size))

            if field_index == self.SORT_BY_MTIME:
                key_func = lambda x: x[2]
            elif field_index == self.SORT_BY_CTIME:
                key_func = lambda x: x[1]
            elif field_index == self.SORT_BY_NAME:
                key_func = lambda x: x[3].lower()
            else:
                key_func = lambda x: x[4]

            file_with_info.sort(key=key_func, reverse=not is_ascending)
            self.all_workflow_paths = [item[0] for item in file_with_info]

        if self._view_mode == VIEW_MODE_GRID:
            QTimer.singleShot(0, self._refresh_grid_view)
        else:
            QTimer.singleShot(0, self._refresh_list_view)
        self._update_status_label()

    def _refresh_grid_view(self):
        for card in self._card_map.values():
            card.hide()

        self._grid_render_count = 0
        self._grid_batch_inflight = False

        while self.flow_layout.count():
            self.flow_layout.takeAt(0)

        if self._view_mode != VIEW_MODE_GRID or not self.all_workflow_paths:
            self.flow_layout.invalidate()
            QTimer.singleShot(0, self.scroll_widget.update)
            return

        self._render_more_grid_cards(self._initial_grid_batch_size())
        QTimer.singleShot(0, self._ensure_grid_viewport_filled)

    def _refresh_list_view(self):
        self.workflow_list_view.set_file_info_map(self._file_info_map)
        self.workflow_list_view.refresh(self.all_workflow_paths)

    def _initial_grid_batch_size(self) -> int:
        viewport = self.scroll_area.viewport().size()
        viewport_width = max(viewport.width(), 1)
        viewport_height = max(viewport.height(), 1)

        estimated_card_width = 400
        estimated_card_height = 340
        estimated_columns = max(1, viewport_width // estimated_card_width)
        estimated_rows = max(1, viewport_height // estimated_card_height + 1)
        estimated_visible = estimated_columns * estimated_rows
        return max(self.GRID_INITIAL_BATCH_SIZE, estimated_visible * 2)

    def _ensure_workflow_card(self, wf_path: Path):
        card = self._card_map.get(wf_path)
        if card is not None:
            return card

        try:
            card = WorkflowCard(wf_path, self, self._file_info_map.get(str(wf_path)))
            card.hide()
            self._card_map[wf_path] = card
            return card
        except Exception:
            import traceback

            traceback.print_exc()
            return None

    def _render_more_grid_cards(self, count: int) -> bool:
        if self._view_mode != VIEW_MODE_GRID:
            return False

        end = min(len(self.all_workflow_paths), self._grid_render_count + max(0, count))
        if end <= self._grid_render_count:
            return False

        for wf_path in self.all_workflow_paths[self._grid_render_count : end]:
            card = self._ensure_workflow_card(wf_path)
            if card is None:
                continue
            self.flow_layout.addWidget(card)
            card.show()

        self._grid_render_count = end
        self.flow_layout.invalidate()
        QTimer.singleShot(0, self.scroll_widget.update)
        self._update_status_label()
        return True

    def _ensure_grid_viewport_filled(self):
        if self._view_mode != VIEW_MODE_GRID:
            return
        scrollbar = self.scroll_area.verticalScrollBar()
        if (
            self._grid_render_count < len(self.all_workflow_paths)
            and scrollbar.maximum() <= 0
        ):
            self._render_more_grid_cards(self.GRID_INCREMENTAL_BATCH_SIZE)
            QTimer.singleShot(0, self._ensure_grid_viewport_filled)

    def _load_more_grid_cards_if_needed(self):
        if self._view_mode != VIEW_MODE_GRID or self._grid_batch_inflight:
            return

        scrollbar = self.scroll_area.verticalScrollBar()
        remaining = scrollbar.maximum() - scrollbar.value()
        should_load = (
            self._grid_render_count < len(self.all_workflow_paths)
            and remaining <= self.GRID_LOAD_MORE_THRESHOLD_PX
        )
        if not should_load:
            return

        self._grid_batch_inflight = True

        def load_batch():
            self._grid_batch_inflight = False
            rendered = self._render_more_grid_cards(self.GRID_INCREMENTAL_BATCH_SIZE)
            if rendered:
                QTimer.singleShot(0, self._load_more_grid_cards_if_needed)

        QTimer.singleShot(0, load_batch)

    def _on_grid_scroll_changed(self, _value: int):
        self._load_more_grid_cards_if_needed()

    def _on_grid_scroll_range_changed(self, _minimum: int, _maximum: int):
        self._load_more_grid_cards_if_needed()

    def _on_search_changed(self, text: str):
        self._filter_text = text.strip().lower()
        self._search_debounce_timer.start(300)

    def _do_search(self):
        self._apply_sort_and_filter_and_refresh()

    def _on_sort_changed(self, index=None):
        self._apply_sort_and_filter_and_refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._view_mode == VIEW_MODE_GRID:
            QTimer.singleShot(0, self._ensure_grid_viewport_filled)

    def showEvent(self, event):
        super().showEvent(event)

    def _request_cache_sizes(self, workflow_files: List[Path]):
        pending_updates = []
        for wf_path in workflow_files:
            folder = wf_path.parent
            cached_size = FolderSizeCache.get(folder)
            if cached_size is not None:
                info = self._file_info_map.get(str(wf_path))
                if info is not None:
                    info["folder_size_bytes"] = cached_size
                continue

            def update(total_size: int, current_path=wf_path):
                info = self._file_info_map.get(str(current_path))
                if info is None:
                    return
                info["folder_size_bytes"] = total_size
                pending_updates.append(current_path)
                if len(pending_updates) >= 5:
                    self._flush_pending_workflow_updates(pending_updates)
                    pending_updates.clear()

            FolderSizeCache.request(folder, update)

        if pending_updates:
            QTimer.singleShot(
                100, lambda: self._flush_pending_workflow_updates(pending_updates)
            )

    def _flush_pending_workflow_updates(self, paths):
        for p in paths:
            self.workflow_list_view.update_workflow(p)
        self._cache_size_refresh_timer.start(120)

    def _refresh_after_cache_size_update(self):
        if self.sort_field_combo.currentIndex() == self.SORT_BY_CACHE_SIZE:
            self._apply_sort_and_filter_and_refresh()
        else:
            self._update_status_label()

    def _update_status_label(self, extra_text: str = ""):
        total_count = len(self._known_files)
        filtered_count = len(self.all_workflow_paths)
        cache_known_count = sum(
            1
            for info in self._file_info_map.values()
            if info.get("folder_size_bytes", -1) >= 0
        )

        if self._view_mode == VIEW_MODE_GRID:
            rendered_count = self._grid_render_count
        else:
            rendered_count = getattr(
                self.workflow_list_view, "rendered_count", lambda: 0
            )()

        parts = [
            self.tr("总数 {0}").format(total_count),
            self.tr("筛选 {0}").format(filtered_count),
            self.tr("已渲染 {0}").format(rendered_count),
            self.tr("缓存统计 {0}").format(cache_known_count),
        ]
        if extra_text:
            parts.append(extra_text)
        self.status_label.setText(" | ".join(parts))

    def open_canvas(self, file_path: Path):
        if file_path not in self.opened_workflows:
            canvas_page = CanvasPage(
                self.parent_window, object_name=file_path, manager=self
            )
            canvas_page.property_panel.set_allowed_update(False)
            canvas_page.load_full_workflow(file_path)
            canvas_page.canvas_deleted.connect(
                lambda: (
                    self.opened_workflows.pop(file_path, None),
                    self._schedule_refresh(),
                )
            )
            canvas_page.canvas_saved.connect(self._on_canvas_saved)
            self.parent_window.addSubInterface(
                canvas_page, get_icon("模型"), file_path.parent.name, parent=self
            )
            self.opened_workflows[file_path] = canvas_page

        self.parent_window.switchTo(self.opened_workflows[file_path])

    def new_canvas(self, window=None, from_template=False):
        name_dialog = CustomInputDialog(
            self.tr("新建画布"), self.tr("请输入画布名称"), parent=window or self
        )
        if not name_dialog.exec():
            return
        base_name = name_dialog.get_text().strip()
        if not base_name:
            InfoBar.warning(
                self.tr("名称无效"), self.tr("画布名称不能为空"), parent=window or self
            )
            return

        counter = 0
        while True:
            canvas_folder = self.workflow_dir[0] / (
                base_name if counter == 0 else f"{base_name}_{counter}"
            )
            if not (canvas_folder / f"{base_name}.workflow.json").exists():
                break
            counter += 1

        canvas_folder.mkdir(parents=True, exist_ok=True)
        file_path = canvas_folder / f"{canvas_folder.name}.workflow.json"

        if file_path not in self.opened_workflows:
            canvas_page = CanvasPage(
                self.parent_window, object_name=file_path, manager=self
            )
            (canvas_page._deferred_initialization(),)
            canvas_page.environment_manager.load_env_combos()
            canvas_page.property_panel.set_allowed_update(True)
            canvas_page.property_panel.update_properties(None)
            canvas_page.canvas_deleted.connect(
                lambda: (
                    self.opened_workflows.pop(file_path, None),
                    self._schedule_refresh(),
                )
            )
            canvas_page.canvas_saved.connect(self._on_canvas_saved)
            if from_template:
                canvas_page.start_from_template()
            self.parent_window.addSubInterface(
                canvas_page, get_icon("模型"), file_path.parent.name, parent=self
            )
            self.opened_workflows[file_path] = canvas_page

        self.parent_window.switchTo(self.opened_workflows[file_path])
        self._schedule_refresh()

    def import_canvas(self):
        folder_path = QFileDialog.getExistingDirectory(
            self, self.tr("选择要导入的画布文件夹"), str(self.workflow_dir[0])
        )
        if not folder_path:
            return

        src_folder = Path(folder_path)
        if not src_folder.is_dir():
            InfoBar.error(
                self.tr("无效目录"), self.tr("请选择有效的画布文件夹"), parent=self
            )
            return

        wf_files = list(src_folder.glob("*.workflow.json"))
        if not wf_files:
            InfoBar.error(
                self.tr("无效画布"),
                self.tr("所选文件夹中未找到 .workflow.json 文件"),
                parent=self,
            )
            return

        base_name = src_folder.name
        counter = 0
        while True:
            dest_folder = self.workflow_dir[0] / (
                base_name if counter == 0 else f"{base_name}_{counter}"
            )
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

            InfoBar.success(
                self.tr("导入成功"),
                self.tr('已导入画布 "{}"').format(dest_folder.name),
                parent=self,
            )
            self._schedule_refresh()

        except Exception as e:
            InfoBar.error(
                self.tr("导入失败"),
                self.tr("无法复制文件夹：{}").format(e),
                parent=self,
            )

    def edit_workflow(self, src_path: Path):
        src_folder = src_path.parent
        old_name = src_folder.name

        dialog = CustomInputDialog(
            self.tr("重命名画布"), self.tr("请输入新名称"), old_name, self
        )
        if not dialog.exec():
            return
        new_name = dialog.get_text().strip()
        if not new_name:
            InfoBar.warning(
                self.tr("名称无效"), self.tr("画布名称不能为空"), parent=self
            )
            return

        counter = 0
        while True:
            new_folder = self.workflow_dir[0] / (
                new_name if counter == 0 else f"{new_name}_{counter}"
            )
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

            if src_path in self.workflow_list_view._item_widgets:
                widget = self.workflow_list_view._item_widgets.pop(src_path)
                widget.deleteLater()

            old_name_key = src_path.parent.name
            if old_name_key in self._pinyin_cache:
                del self._pinyin_cache[old_name_key]

            InfoBar.success(
                self.tr("重命名成功"),
                self.tr("已重命名为 {}").format(new_name),
                parent=self,
            )
            self._schedule_refresh()
        except Exception as e:
            InfoBar.error(self.tr("重命名失败"), str(e), parent=self)

    def duplicate_workflow(self, src_path: Path):
        src_folder = src_path.parent
        old_name = src_folder.name

        dialog = CustomInputDialog(
            self.tr("复制画布"), self.tr("请输入新画布名称"), old_name + "_copy", self
        )
        if not dialog.exec():
            return
        new_name = dialog.get_text().strip()
        if not new_name:
            InfoBar.warning(
                self.tr("名称无效"), self.tr("画布名称不能为空"), parent=self
            )
            return

        counter = 0
        while True:
            new_folder = self.workflow_dir[0] / (
                new_name if counter == 0 else f"{new_name}_{counter}"
            )
            if not new_folder.exists():
                break
            counter += 1

        try:
            shutil.copytree(src_folder, new_folder)
            _normalize_canvas_folder(new_folder)

            InfoBar.success(
                self.tr("复制成功"), self.tr("已创建 {}").format(new_name), parent=self
            )
            self._schedule_refresh()
        except Exception as e:
            InfoBar.error(self.tr("复制失败"), str(e), parent=self)

    def delete_workflow(self, file_path: Path):
        from qfluentwidgets import MessageBox

        name = file_path.parent.name
        title = self.tr("确认删除")
        content = self.tr('确定要删除画布 "{}" 吗？\n此操作不可恢复！').format(name)

        w = MessageBox(title, content, self)
        if not w.exec():
            return

        try:
            shutil.rmtree(file_path.parent)

            InfoBar.success(
                self.tr("删除成功"),
                self.tr("画布 '{}' 已删除").format(name),
                parent=self,
            )

            if file_path in self.opened_workflows:
                self.parent_window.removeInterface(self.opened_workflows[file_path])
                del self.opened_workflows[file_path]

            if file_path in self._card_map:
                old_card = self._card_map.pop(file_path)
                self.flow_layout.removeWidget(old_card)
                old_card.hide()
                old_card.deleteLater()

            if file_path in self.workflow_list_view._item_widgets:
                widget = self.workflow_list_view._item_widgets.pop(file_path)
                widget.deleteLater()

            self._schedule_refresh()
        except Exception as e:
            InfoBar.error(self.tr("删除失败"), str(e), parent=self)

    def backup_workflow_to_cloud(self, file_path: Path):
        try:
            folder = file_path.parent
            workflow_name = folder.name
            json_path = file_path
            image_path = folder / f"{workflow_name}.png"

            meta_info = {
                "id": workflow_name,
                "name": workflow_name,
                "category": "默认",
                "description": "",
                "version": "1.0.0",
            }

            success = self._canvas_cloud_mgr.add_canvas(
                meta_info=meta_info,
                json_path=str(json_path),
                image_path=str(image_path) if image_path.exists() else None,
            )

            if success:
                InfoBar.success(
                    self.tr("备份成功"),
                    self.tr("画布 '{}' 已备份到云端").format(workflow_name),
                    parent=self,
                )
            else:
                InfoBar.error(
                    self.tr("备份失败"),
                    self.tr("云端返回失败，请检查网络和配置"),
                    parent=self,
                )
        except Exception as e:
            logger.error(f"Backup workflow failed: {e}")
            InfoBar.error(self.tr("备份失败"), str(e), parent=self)

    def refresh_workflow_folder_size(self, file_path: Path):
        self.workflow_list_view.refresh_folder_size(file_path)

    def _on_canvas_saved(self, workflow_path: Path):
        try:
            stat = workflow_path.stat()
            file_info = {
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
            self._file_info_map[str(workflow_path)] = file_info
            card = self._card_map.get(workflow_path)
            if card:
                card.update_file_info(file_info)
        except Exception as e:
            logger.error(f"Update card info failed: {e}")

        card = self._card_map.get(workflow_path)
        if card and hasattr(card, "refresh_preview"):
            card.refresh_preview()
