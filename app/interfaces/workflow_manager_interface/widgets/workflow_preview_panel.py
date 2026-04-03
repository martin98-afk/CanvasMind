from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import shutil

from PyQt5.QtCore import Qt, QSize, QTimer
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QPushButton,
    QDialog,
    QLabel,
    QApplication,
)
from qfluentwidgets import (
    CardWidget,
    BodyLabel,
    FluentIcon,
    CaptionLabel,
)
from qfluentwidgets.components.widgets.card_widget import CardSeparator

from app.widgets.basic_widget.resizable_image_label import ResizableImageLabel
from app.utils.utils import get_icon, get_unified_font


class WorkflowPreviewPanel(CardWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.current_workflow_path: Optional[Path] = None
        self._gallery_page = parent
        self.setBorderRadius(12)
        self._setup_ui()
        self._show_empty_state()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        self.preview_label = ResizableImageLabel(self)
        self.preview_label.setMaxHeight(280)
        self.preview_label.setStyleSheet("""
            ResizableImageLabel {
                background-color: rgba(255, 255, 255, 0.05);
                border-radius: 8px;
            }
        """)
        self.preview_label.clicked.connect(self._show_preview_dialog)
        layout.addWidget(self.preview_label)

        layout.addWidget(CardSeparator())

        self.info_grid = QGridLayout()
        self.info_grid.setVerticalSpacing(12)
        self.info_grid.setHorizontalSpacing(20)

        self.name_label = BodyLabel()
        self.name_label.setFont(get_unified_font(16, True))
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setWordWrap(True)
        self.name_label.setStyleSheet("color: #e0e0e0;")
        self.info_grid.addWidget(self.name_label, 0, 0, 1, 2)

        row = 1
        self.ctime_key = CaptionLabel(self.tr("创建时间"))
        self.ctime_key.setStyleSheet("color: #888;")
        self.ctime_val = BodyLabel()
        self.ctime_val.setStyleSheet("color: #ccc;")

        self.mtime_key = CaptionLabel(self.tr("修改时间"))
        self.mtime_key.setStyleSheet("color: #888;")
        self.mtime_val = BodyLabel()
        self.mtime_val.setStyleSheet("color: #ccc;")

        self.size_key = CaptionLabel(self.tr("大小"))
        self.size_key.setStyleSheet("color: #888;")
        self.size_val = BodyLabel()
        self.size_val.setStyleSheet("color: #ccc;")

        self.path_key = CaptionLabel(self.tr("路径"))
        self.path_key.setStyleSheet("color: #888;")
        self.path_val = BodyLabel()
        self.path_val.setStyleSheet("color: #ccc;")
        self.path_val.setWordWrap(True)

        self.info_grid.addWidget(self.ctime_key, row, 0)
        self.info_grid.addWidget(self.ctime_val, row, 1)
        row += 1
        self.info_grid.addWidget(self.mtime_key, row, 0)
        self.info_grid.addWidget(self.mtime_val, row, 1)
        row += 1
        self.info_grid.addWidget(self.size_key, row, 0)
        self.info_grid.addWidget(self.size_val, row, 1)
        row += 1
        self.info_grid.addWidget(self.path_key, row, 0)
        self.info_grid.addWidget(self.path_val, row, 1)

        layout.addLayout(self.info_grid)

        self.btn_layout = QHBoxLayout()
        self.btn_layout.setSpacing(8)

        btn_style = """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                color: #e0e0e0;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.2);
            }
            QPushButton:disabled {
                background-color: rgba(255, 255, 255, 0.05);
                color: #666;
            }
        """

        self.open_btn = QPushButton(self.tr("打开"), self)
        self.open_btn.setIcon(FluentIcon.LINK.icon())
        self.open_btn.setIconSize(QSize(16, 16))
        self.open_btn.setStyleSheet(btn_style)
        self.open_btn.clicked.connect(self._on_open_clicked)

        self.copy_btn = QPushButton(self.tr("复制"), self)
        self.copy_btn.setIcon(FluentIcon.COPY.icon())
        self.copy_btn.setIconSize(QSize(16, 16))
        self.copy_btn.setStyleSheet(btn_style)
        self.copy_btn.clicked.connect(self._on_copy_clicked)

        self.rename_btn = QPushButton(self.tr("重命名"), self)
        self.rename_btn.setIcon(FluentIcon.EDIT.icon())
        self.rename_btn.setIconSize(QSize(16, 16))
        self.rename_btn.setStyleSheet(btn_style)
        self.rename_btn.clicked.connect(self._on_rename_clicked)

        self.delete_btn = QPushButton(self.tr("删除"), self)
        self.delete_btn.setIcon(FluentIcon.DELETE.icon())
        self.delete_btn.setIconSize(QSize(16, 16))
        self.delete_btn.setStyleSheet(btn_style)
        self.delete_btn.clicked.connect(self._on_delete_clicked)

        self.btn_layout.addWidget(self.open_btn)
        self.btn_layout.addWidget(self.copy_btn)
        self.btn_layout.addWidget(self.rename_btn)
        self.btn_layout.addWidget(self.delete_btn)

        self.clear_cache_btn = QPushButton(self.tr("清除缓存"), self)
        self.clear_cache_btn.setIcon(FluentIcon.DELETE.icon())
        self.clear_cache_btn.setIconSize(QSize(16, 16))
        self.clear_cache_btn.setStyleSheet(btn_style)
        self.clear_cache_btn.clicked.connect(self._on_clear_cache_clicked)

        self.backup_btn = QPushButton(self.tr("备份"), self)
        self.backup_btn.setIcon(FluentIcon.UPDATE.icon())
        self.backup_btn.setIconSize(QSize(16, 16))
        self.backup_btn.setStyleSheet(btn_style)
        self.backup_btn.clicked.connect(self._on_backup_clicked)

        self.btn_layout.addWidget(self.clear_cache_btn)
        self.btn_layout.addWidget(self.backup_btn)
        layout.addLayout(self.btn_layout)

        self._set_buttons_enabled(False)

    def _show_empty_state(self):
        self.preview_label.setOriginalPixmap(QPixmap())
        self.name_label.setText("")
        self.ctime_val.setText("")
        self.mtime_val.setText("")
        self.size_val.setText("")
        self.path_val.setText("")
        self._set_buttons_enabled(False)

    def _set_buttons_enabled(self, enabled: bool):
        self.open_btn.setEnabled(enabled)
        self.copy_btn.setEnabled(enabled)
        self.rename_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)

    def set_workflow(
        self, workflow_path: Optional[Path], file_info: Optional[Dict[str, Any]] = None
    ):
        if workflow_path is None:
            self.current_workflow_path = None
            self._show_empty_state()
            return

        self.current_workflow_path = workflow_path
        self._set_buttons_enabled(True)

        self.name_label.setText(workflow_path.parent.name)
        self._load_preview_delayed(workflow_path)

        if file_info:
            self.ctime_val.setText(file_info.get("ctime", "未知"))
            self.mtime_val.setText(file_info.get("mtime", "未知"))
            size_kb = file_info.get("size_kb", 0)
            if size_kb > 1024:
                self.size_val.setText(f"{size_kb / 1024:.1f} MB")
            else:
                self.size_val.setText(f"{size_kb} KB")
        else:
            try:
                stat = workflow_path.stat()
                self.ctime_val.setText(
                    datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M")
                )
                self.mtime_val.setText(
                    datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                )
                size_kb = stat.st_size // 1024
                if size_kb > 1024:
                    self.size_val.setText(f"{size_kb / 1024:.1f} MB")
                else:
                    self.size_val.setText(f"{size_kb} KB")
            except Exception:
                self.ctime_val.setText("未知")
                self.mtime_val.setText("未知")
                self.size_val.setText("未知")

        self.path_val.setText(str(workflow_path.parent))

    def _load_preview_delayed(self, workflow_path: Path):
        def load():
            if self.current_workflow_path != workflow_path:
                return
            workflow_name = ".".join(workflow_path.stem.split(".")[:-1])
            preview_path = workflow_path.parent / f"{workflow_name}.png"
            if preview_path.exists():
                pixmap = QPixmap(str(preview_path))
                if not pixmap.isNull():
                    self.preview_label.setOriginalPixmap(pixmap)

        QTimer.singleShot(100, load)

    def _on_open_clicked(self):
        if (
            self.current_workflow_path
            and self._gallery_page
            and hasattr(self._gallery_page, "open_canvas")
        ):
            self._gallery_page.open_canvas(self.current_workflow_path)

    def _on_copy_clicked(self):
        if (
            self.current_workflow_path
            and self._gallery_page
            and hasattr(self._gallery_page, "duplicate_workflow")
        ):
            self._gallery_page.duplicate_workflow(self.current_workflow_path)

    def _on_rename_clicked(self):
        if (
            self.current_workflow_path
            and self._gallery_page
            and hasattr(self._gallery_page, "edit_workflow")
        ):
            self._gallery_page.edit_workflow(self.current_workflow_path)

    def _on_delete_clicked(self):
        if (
            self.current_workflow_path
            and self._gallery_page
            and hasattr(self._gallery_page, "delete_workflow")
        ):
            self._gallery_page.delete_workflow(self.current_workflow_path)

    def _on_clear_cache_clicked(self):
        if not self.current_workflow_path:
            return
        folder = self.current_workflow_path.parent
        workflow_name = ".".join(self.current_workflow_path.stem.split(".")[:-1])
        protected_names = {f"{workflow_name}.png", f"{workflow_name}.workflow.json"}

        deleted_count = 0
        try:
            for item in folder.iterdir():
                if item.is_file():
                    continue
                if item.name not in protected_names:
                    shutil.rmtree(item)
                    deleted_count += 1
                else:
                    for subitem in item.rglob("*"):
                        if subitem.is_file() and subitem.name not in protected_names:
                            subitem.unlink()
                            deleted_count += 1
        except Exception as e:
            from loguru import logger

            logger.error(f"Clear cache failed: {e}")
            return

        from qfluentwidgets import InfoBar

        if deleted_count > 0:
            InfoBar.success(
                self.tr("清除成功"),
                self.tr(f"已删除 {deleted_count} 个缓存项"),
                parent=self,
            )
        else:
            InfoBar.info(
                self.tr("无需清理"), self.tr("没有找到可清理的缓存"), parent=self
            )

    def _on_backup_clicked(self):
        if not self.current_workflow_path:
            return
        if self._gallery_page and hasattr(
            self._gallery_page, "backup_workflow_to_cloud"
        ):
            self._gallery_page.backup_workflow_to_cloud(self.current_workflow_path)

    def _show_preview_dialog(self):
        if not self.current_workflow_path:
            return
        workflow_name = ".".join(self.current_workflow_path.stem.split(".")[:-1])
        preview_path = self.current_workflow_path.parent / f"{workflow_name}.png"
        if not preview_path.exists():
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("预览图"))
        screen_size = QApplication.primaryScreen().availableGeometry().size() * 0.8
        dialog.resize(int(screen_size.width() * 0.7), int(screen_size.height() * 0.7))
        dialog.setStyleSheet("background-color: #1e1e1e;")
        layout = QVBoxLayout(dialog)
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        from PyQt5.QtGui import QPixmap

        pixmap = QPixmap(str(preview_path))
        if not pixmap.isNull():
            label.setPixmap(
                pixmap.scaled(
                    dialog.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
        label.mousePressEvent = lambda e: dialog.accept()
        layout.addWidget(label)
        dialog.exec_()
