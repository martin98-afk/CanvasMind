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
        self.recommendation_engine = NodeRecommendationEngine()
        self._canvas_cloud_mgr = CanvasCloudManager()

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
        if not self.recommendation_engine:
            return []
        return self.recommendation_engine.get_recommendations_sync(node_full_path)

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
            [self.tr("修改时间"), self.tr("创建时间"), self.tr("名称")]
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

        self.flow_layout = FlowLayout(self.scroll_widget, needAni=True)
        self.flow_layout.setAnimation(250, QEasingCurve.OutQuad)
        self.flow_layout.setContentsMargins(30, 30, 30, 30)
        self.flow_layout.setVerticalSpacing(20)
        self.flow_layout.setHorizontalSpacing(30)

        self.scroll_area.setWidget(self.scroll_widget)
        self.grid_layout.addWidget(self.scroll_area)

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
        main_layout.addWidget(self.content_container, 1)

    def _on_view_mode_changed(self, mode: str):
        if mode == "grid":
            self._view_mode = VIEW_MODE_GRID
            self.content_container.setCurrentWidget(self.grid_container)
            QTimer.singleShot(10, self._refresh_grid_view)
        else:
            self._view_mode = VIEW_MODE_LIST
            self.content_container.setCurrentWidget(self.list_container)

    def _on_list_selection_changed(self, workflow_path: Path):
        file_info = self._file_info_map.get(str(workflow_path))
        self.preview_panel.set_workflow(workflow_path, file_info)

    def build_recommendation_engine(self):
        if self._recommendation_engine_built:
            return
        self._recommendation_engine_built = True
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
        _migrate_legacy_workflow_structure(self.workflow_dir)

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

        for wf_path in workflow_files:
            if wf_path not in self._card_map:
                try:
                    card = WorkflowCard(
                        wf_path, self, self._file_info_map.get(str(wf_path))
                    )
                    card.hide()
                    self._card_map[wf_path] = card
                except Exception:
                    import traceback

                    traceback.print_exc()

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

        self._apply_sort_and_filter_and_refresh()
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

        self._refresh_grid_view()
        self._refresh_list_view()

    def _refresh_grid_view(self):
        for card in self._card_map.values():
            card.hide()

        while self.flow_layout.count():
            self.flow_layout.takeAt(0)

        for wf_path in self.all_workflow_paths:
            card = self._card_map.get(wf_path)
            if card is not None:
                self.flow_layout.addWidget(card)
                card.show()

        self.flow_layout.invalidate()
        QTimer.singleShot(0, self.scroll_widget.update)

    def _refresh_list_view(self):
        self.workflow_list_view.set_file_info_map(self._file_info_map)
        self.workflow_list_view.refresh(self.all_workflow_paths)

    def _on_search_changed(self, text: str):
        self._filter_text = text.strip().lower()
        self._search_debounce_timer.start(300)

    def _do_search(self):
        self._apply_sort_and_filter_and_refresh()

    def _on_sort_changed(self, index=None):
        self._apply_sort_and_filter_and_refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)

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
