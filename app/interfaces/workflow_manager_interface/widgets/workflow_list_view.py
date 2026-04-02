from pathlib import Path
from typing import Optional, Dict, List

from PyQt5.QtCore import Qt, QSize, pyqtSignal, QTimer
from PyQt5.QtGui import QPixmap, QFont, QContextMenuEvent
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
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
        self._setup_ui()
        self._apply_file_info()
        self._load_thumbnail_delayed()

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

    def _load_thumbnail_delayed(self):
        def load():
            try:
                workflow_name = ".".join(self.workflow_path.stem.split(".")[:-1])
                preview_path = self.workflow_path.parent / f"{workflow_name}.png"
                if preview_path.exists():
                    pixmap = QPixmap(str(preview_path))
                    if not pixmap.isNull():
                        scaled = pixmap.scaled(
                            40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation
                        )
                        self.thumbnail_label.setPixmap(scaled)
            except Exception:
                pass

        QTimer.singleShot(100, load)

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

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.item_selected.emit(self.workflow_path)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._on_open()
        super().mouseDoubleClickEvent(event)

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

    def contextMenuEvent(self, event: QContextMenuEvent):
        menu = QMenu(self)
        open_action = menu.addAction(self.tr("打开"))
        copy_action = menu.addAction(self.tr("复制"))
        rename_action = menu.addAction(self.tr("重命名"))
        menu.addSeparator()
        delete_action = menu.addAction(self.tr("删除"))

        action = menu.exec_(self.mapToGlobal(event.pos()))
        if action == open_action:
            self._on_open()
        elif action == copy_action:
            self._on_copy()
        elif action == rename_action:
            self._on_rename()
        elif action == delete_action:
            self._on_delete()


class WorkflowListView(QWidget):
    current_changed = pyqtSignal(Path)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._item_widgets: Dict[Path, WorkflowListItem] = {}
        self._current_path: Optional[Path] = None
        self._file_info_map: Dict[str, dict] = {}
        self._gallery_page = parent
        self._setup_ui()

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

        size_header = CaptionLabel(self.tr("大小"))
        size_header.setStyleSheet("color: #666; font-weight: 600;")
        size_header.setFixedWidth(80)
        header_layout.addWidget(size_header)

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

    def set_file_info_map(self, file_info_map: Dict[str, dict]):
        self._file_info_map = file_info_map

    def refresh(self, ordered_paths: List[Path]):
        existing_paths = set(self._item_widgets.keys())
        target_paths = set(ordered_paths)

        for path in existing_paths - target_paths:
            self.remove_workflow(path)

        for i, path in enumerate(ordered_paths):
            if path not in self._item_widgets:
                self.add_workflow(path)
            else:
                widget = self._item_widgets[path]
                self.content_layout.removeWidget(widget)
                self.content_layout.insertWidget(i, widget)

        self.content_layout.update()

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
