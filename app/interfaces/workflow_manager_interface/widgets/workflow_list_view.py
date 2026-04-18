from pathlib import Path
from typing import Optional, Dict, List

from PyQt5.QtCore import Qt, QSize, pyqtSignal, QTimer, QEvent
from PyQt5.QtGui import QPixmap, QFont, QMouseEvent
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
)
from qfluentwidgets import (
    SmoothScrollArea,
    BodyLabel,
    CaptionLabel,
    TransparentToolButton,
    FluentIcon,
)
from qfluentwidgets.components.widgets.card_widget import CardSeparator

from app.widgets.basic_widget.resizable_image_label import ResizableImageLabel
from app.utils.utils import get_icon, get_unified_font
from app.interfaces.workflow_manager_interface.utils.utils import (
    ThumbnailCache,
    FolderSizeCache,
)


class WorkflowListItem(QWidget):
    item_selected = pyqtSignal(Path)

    def __init__(
        self,
        workflow_path: Path,
        file_info: Optional[Dict] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.workflow_path = workflow_path
        self.file_info = file_info
        self.is_selected = False
        self._load_cancelled = False
        self._size_requested = False
        self._setup_ui()
        self._apply_file_info()
        self._load_thumbnail_delayed()
        self.installEventFilter(self)
        self.setToolTip(self.tr("双击打开画布"))

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(16)

        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(40, 40)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setStyleSheet("background: transparent;")
        self.thumbnail_label.setText("📄")
        layout.addWidget(self.thumbnail_label)

        self.name_label = BodyLabel()
        self.name_label.setFont(get_unified_font(13, False))
        self.name_label.setText(self.workflow_path.parent.name)
        self.name_label.setStyleSheet("background: transparent; color: #e0e0e0;")
        layout.addWidget(self.name_label, 1)

        self.mtime_label = CaptionLabel()
        self.mtime_label.setFont(get_unified_font(11))
        self.mtime_label.setStyleSheet("background: transparent; color: #888;")
        self.mtime_label.setFixedWidth(140)
        layout.addWidget(self.mtime_label)

        self.ctime_label = CaptionLabel()
        self.ctime_label.setFont(get_unified_font(11))
        self.ctime_label.setStyleSheet("background: transparent; color: #888;")
        self.ctime_label.setFixedWidth(140)
        layout.addWidget(self.ctime_label)

        self.size_label = CaptionLabel()
        self.size_label.setFont(get_unified_font(11))
        self.size_label.setStyleSheet("background: transparent; color: #888;")
        self.size_label.setFixedWidth(80)
        layout.addWidget(self.size_label)

        self.folder_size_label = CaptionLabel()
        self.folder_size_label.setFont(get_unified_font(11))
        self.folder_size_label.setStyleSheet("background: transparent; color: #888;")
        self.folder_size_label.setFixedWidth(80)
        layout.addWidget(self.folder_size_label)

        passive_widgets = [
            self.thumbnail_label,
            self.name_label,
            self.mtime_label,
            self.ctime_label,
            self.size_label,
            self.folder_size_label,
        ]
        for widget in passive_widgets:
            widget.installEventFilter(self)

    def _load_thumbnail_delayed(self):
        def load():
            if self._load_cancelled:
                return
            try:
                workflow_name = ".".join(self.workflow_path.stem.split(".")[:-1])
                preview_path = self.workflow_path.parent / f"{workflow_name}.png"
                if not preview_path.exists():
                    return

                cache_key = f"{preview_path}_list_40x40"
                cached = ThumbnailCache.get(cache_key)
                if cached and not cached.isNull():
                    if not self._load_cancelled:
                        self.thumbnail_label.setPixmap(cached.copy())
                    return

                if ThumbnailCache.is_loading(cache_key):
                    return

                ThumbnailCache.set_loading(cache_key, True)

                try:
                    pixmap = QPixmap(str(preview_path))
                    if not pixmap.isNull() and not self._load_cancelled:
                        scaled = pixmap.scaled(
                            40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation
                        )
                        ThumbnailCache.put(cache_key, scaled.copy())
                        self.thumbnail_label.setPixmap(scaled)
                finally:
                    ThumbnailCache.set_loading(cache_key, False)
            except Exception:
                pass

        QTimer.singleShot(50, load)

    def _apply_file_info(self):
        if self.file_info:
            self.mtime_label.setText(self.file_info.get("mtime", "--"))
            self.ctime_label.setText(self.file_info.get("ctime", "--"))
            size_kb = self.file_info.get("size_kb", 0)
            if size_kb > 1024:
                self.size_label.setText(f"{size_kb / 1024:.1f} MB")
            else:
                self.size_label.setText(f"{size_kb} KB" if size_kb > 0 else "--")
        else:
            self.mtime_label.setText("--")
            self.ctime_label.setText("--")
            self.size_label.setText("--")
        self.folder_size_label.setText("...")

    def _request_folder_size(self):
        if self._size_requested:
            return
        self._size_requested = True
        folder = self.workflow_path.parent

        def update(folder_size: int):
            if self._load_cancelled:
                return
            if folder_size > 0:
                if folder_size > 1024 * 1024:
                    self.folder_size_label.setText(
                        f"{folder_size / (1024 * 1024):.1f} MB"
                    )
                elif folder_size > 1024:
                    self.folder_size_label.setText(f"{folder_size / 1024:.1f} KB")
                else:
                    self.folder_size_label.setText(f"{folder_size} B")
            else:
                self.folder_size_label.setText("--")

        FolderSizeCache.request(folder, update)

    def refresh_folder_size(self):
        self._size_requested = False
        FolderSizeCache.invalidate(self.workflow_path.parent)
        self.folder_size_label.setText("...")
        self._request_folder_size()

    def update_file_info(self, file_info: Dict):
        self.file_info = file_info
        self._apply_file_info()

    def set_selected(self, selected: bool):
        self.is_selected = selected
        self.setAttribute(Qt.WA_StyledBackground)
        if selected:
            self.setStyleSheet(
                "background-color: rgba(100, 181, 246, 0.2); border-radius: 4px;"
            )
        else:
            self.setStyleSheet("background-color: transparent;")
            self.setStyleSheet("""
                WorkflowListItem {
                    background-color: transparent;
                }
                WorkflowListItem:hover {
                    background-color: rgba(255, 255, 255, 0.05);
                }
            """)

    def eventFilter(self, watched, event):
        if watched is self or watched.parent() is self:
            if event.type() == QEvent.MouseButtonPress:
                mouse_event = event
                if (
                    isinstance(mouse_event, QMouseEvent)
                    and mouse_event.button() == Qt.LeftButton
                ):
                    self.item_selected.emit(self.workflow_path)
                    return watched is not self
            elif event.type() == QEvent.MouseButtonDblClick:
                mouse_event = event
                if (
                    isinstance(mouse_event, QMouseEvent)
                    and mouse_event.button() == Qt.LeftButton
                ):
                    self._on_open()
                    return True
        return super().eventFilter(watched, event)

    def _on_open(self):
        if hasattr(self.parent(), "open_canvas"):
            self.parent().open_canvas(self.workflow_path)
        elif self.parent() and hasattr(self.parent(), "_gallery_page"):
            self.parent()._gallery_page.open_canvas(self.workflow_path)

    def _on_copy(self):
        if hasattr(self.parent(), "duplicate_workflow"):
            self.parent().duplicate_workflow(self.workflow_path)

    def _on_rename(self):
        if hasattr(self.parent(), "edit_workflow"):
            self.parent().edit_workflow(self.workflow_path)

    def _on_delete(self):
        if hasattr(self.parent(), "delete_workflow"):
            self.parent().delete_workflow(self.workflow_path)

    def hideEvent(self, event):
        self._load_cancelled = True
        super().hideEvent(event)

    def showEvent(self, event):
        self._load_cancelled = False
        if not self._size_requested:
            self._request_folder_size()
        super().showEvent(event)


class WorkflowListView(QWidget):
    LIST_INITIAL_BATCH_SIZE = 40
    LIST_INCREMENTAL_BATCH_SIZE = 20
    LIST_LOAD_MORE_THRESHOLD_PX = 800

    current_changed = pyqtSignal(Path)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._item_widgets: Dict[Path, WorkflowListItem] = {}
        self._current_path: Optional[Path] = None
        self._file_info_map: Dict[str, dict] = {}
        self._gallery_page = parent
        self._ordered_paths: List[Path] = []
        self._render_count = 0
        self._batch_inflight = False
        self._view_mode = None
        self._setup_ui()
        self.scroll_area.viewport().installEventFilter(self)

    def open_canvas(self, workflow_path: Path):
        if self._gallery_page and hasattr(self._gallery_page, "open_canvas"):
            self._gallery_page.open_canvas(workflow_path)

    def duplicate_workflow(self, workflow_path: Path):
        if self._gallery_page and hasattr(self._gallery_page, "duplicate_workflow"):
            self._gallery_page.duplicate_workflow(workflow_path)

    def edit_workflow(self, workflow_path: Path):
        if self._gallery_page and hasattr(self._gallery_page, "edit_workflow"):
            self._gallery_page.edit_workflow(workflow_path)

    def delete_workflow(self, workflow_path: Path):
        if self._gallery_page and hasattr(self._gallery_page, "delete_workflow"):
            self._gallery_page.delete_workflow(workflow_path)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header_widget = QWidget()
        self.header_widget.setFixedHeight(32)
        self.header_widget.setStyleSheet("""
            QWidget {
                background-color: rgba(255, 255, 255, 0.02);
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(12, 0, 12, 0)
        header_layout.setSpacing(16)

        header_layout.addSpacing(52)

        name_header = CaptionLabel(self.tr("名称"))
        name_header.setStyleSheet("color: #666; font-weight: 600;")
        header_layout.addWidget(name_header, 1)

        mtime_header = CaptionLabel(self.tr("修改时间"))
        mtime_header.setStyleSheet("color: #666; font-weight: 600;")
        mtime_header.setFixedWidth(140)
        header_layout.addWidget(mtime_header)

        ctime_header = CaptionLabel(self.tr("创建时间"))
        ctime_header.setStyleSheet("color: #666; font-weight: 600;")
        ctime_header.setFixedWidth(140)
        header_layout.addWidget(ctime_header)

        size_header = CaptionLabel(self.tr("文件大小"))
        size_header.setStyleSheet("color: #666; font-weight: 600;")
        size_header.setFixedWidth(80)
        header_layout.addWidget(size_header)

        folder_size_header = CaptionLabel(self.tr("文件夹"))
        folder_size_header.setStyleSheet("color: #666; font-weight: 600;")
        folder_size_header.setFixedWidth(80)
        header_layout.addWidget(folder_size_header)

        header_layout.addStretch()

        layout.addWidget(self.header_widget)

        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none; background-color: transparent;")
        self.scroll_area.setFrameShape(SmoothScrollArea.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(1)
        self.content_layout.addStretch()

        self.scroll_area.setWidget(self.content_widget)
        layout.addWidget(self.scroll_area)
        self.scroll_area.verticalScrollBar().valueChanged.connect(
            self._on_scroll_changed
        )
        self.scroll_area.verticalScrollBar().rangeChanged.connect(
            self._on_scroll_range_changed
        )

    def set_file_info_map(self, file_info_map: Dict[str, dict]):
        self._file_info_map = file_info_map

    def set_view_mode(self, mode: str):
        self._view_mode = mode
        if mode == "list" and self._ordered_paths:
            self._render_count = 0
            self._render_more_items(len(self._ordered_paths))

    def refresh(self, ordered_paths: List[Path]):
        existing_paths = set(self._item_widgets.keys())
        target_paths = set(ordered_paths)
        self._ordered_paths = list(ordered_paths)

        for path in existing_paths - target_paths:
            self.remove_workflow(path)

        if self._current_path not in target_paths:
            self._current_path = None

        self._render_count = 0
        self._batch_inflight = False

        self._render_more_items(self._initial_batch_size())
        QTimer.singleShot(0, self._ensure_viewport_filled)

    def refresh_folder_size(self, workflow_path: Path):
        if workflow_path in self._item_widgets:
            self._item_widgets[workflow_path].refresh_folder_size()

    def add_workflow(self, workflow_path: Path):
        if workflow_path in self._item_widgets:
            return

        file_info = self._file_info_map.get(str(workflow_path))
        item_widget = WorkflowListItem(workflow_path, file_info, self)
        item_widget.item_selected.connect(self._on_item_selected)

        self._item_widgets[workflow_path] = item_widget
        self.content_layout.insertWidget(self.content_layout.count() - 1, item_widget)
        item_widget.show()

    def update_workflow(self, workflow_path: Path):
        if workflow_path in self._item_widgets:
            file_info = self._file_info_map.get(str(workflow_path))
            self._item_widgets[workflow_path].update_file_info(file_info)

    def remove_workflow(self, workflow_path: Path):
        if workflow_path in self._item_widgets:
            widget = self._item_widgets.pop(workflow_path)
            self.content_layout.removeWidget(widget)
            widget.deleteLater()

        if self._current_path == workflow_path:
            self._current_path = None

    def clear(self):
        for widget in list(self._item_widgets.values()):
            self.content_layout.removeWidget(widget)
            widget.deleteLater()
        self._item_widgets.clear()
        self._current_path = None

    def _on_item_selected(self, workflow_path: Path):
        self._set_current(workflow_path)

    def _set_current(self, workflow_path: Path):
        if self._current_path and self._current_path in self._item_widgets:
            self._item_widgets[self._current_path].set_selected(False)

        self._current_path = workflow_path

        if workflow_path in self._item_widgets:
            self._item_widgets[workflow_path].set_selected(True)
            self.current_changed.emit(workflow_path)

    def get_current(self) -> Optional[Path]:
        return self._current_path

    def rendered_count(self) -> int:
        return self._render_count

    def eventFilter(self, watched, event):
        if watched is self.scroll_area.viewport():
            target_item = (
                self._item_at_viewport_pos(event.pos())
                if hasattr(event, "pos")
                else None
            )
            if target_item is not None:
                if event.type() == QEvent.MouseButtonDblClick:
                    mouse_event = event
                    if (
                        isinstance(mouse_event, QMouseEvent)
                        and mouse_event.button() == Qt.LeftButton
                    ):
                        target_item._on_open()
                        return True
        return super().eventFilter(watched, event)

    def _item_at_viewport_pos(self, viewport_pos):
        content_pos = self.content_widget.mapFrom(
            self.scroll_area.viewport(), viewport_pos
        )
        target = self.content_widget.childAt(content_pos)
        while target is not None and not isinstance(target, WorkflowListItem):
            target = target.parentWidget()
        return target

    def _initial_batch_size(self) -> int:
        viewport_height = max(self.scroll_area.viewport().height(), 1)
        estimated_item_height = 58
        estimated_rows = max(1, viewport_height // estimated_item_height + 2)
        return max(self.LIST_INITIAL_BATCH_SIZE, estimated_rows * 2)

    def _ensure_item_widget(self, workflow_path: Path) -> WorkflowListItem:
        widget = self._item_widgets.get(workflow_path)
        if widget is not None:
            return widget

        self.add_workflow(workflow_path)
        return self._item_widgets[workflow_path]

    def _render_more_items(self, count: int) -> bool:
        end = min(len(self._ordered_paths), self._render_count + max(0, count))
        if end <= self._render_count:
            return False

        for path in self._ordered_paths[self._render_count : end]:
            widget = self._ensure_item_widget(path)
            self.content_layout.removeWidget(widget)
            self.content_layout.insertWidget(self.content_layout.count() - 1, widget)
            widget.set_selected(path == self._current_path)
            widget.show()

        self._render_count = end
        self.content_layout.update()
        self.content_widget.updateGeometry()
        return True

    def _ensure_viewport_filled(self):
        scrollbar = self.scroll_area.verticalScrollBar()
        if self._render_count < len(self._ordered_paths) and scrollbar.maximum() <= 0:
            self._render_more_items(self.LIST_INCREMENTAL_BATCH_SIZE)
            QTimer.singleShot(0, self._ensure_viewport_filled)

    def _load_more_if_needed(self):
        if self._batch_inflight:
            return

        scrollbar = self.scroll_area.verticalScrollBar()
        remaining = scrollbar.maximum() - scrollbar.value()
        should_load = (
            self._render_count < len(self._ordered_paths)
            and remaining <= self.LIST_LOAD_MORE_THRESHOLD_PX
        )
        if not should_load:
            return

        self._batch_inflight = True

        def load_batch():
            self._batch_inflight = False
            rendered = self._render_more_items(self.LIST_INCREMENTAL_BATCH_SIZE)
            if rendered:
                QTimer.singleShot(0, self._load_more_if_needed)

        QTimer.singleShot(0, load_batch)

    def _on_scroll_changed(self, _value: int):
        self._load_more_if_needed()

    def _on_scroll_range_changed(self, _minimum: int, _maximum: int):
        self._load_more_if_needed()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._ensure_viewport_filled)
