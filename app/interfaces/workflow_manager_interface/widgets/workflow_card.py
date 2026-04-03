from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from PyQt5.QtCore import Qt, QSize, QTimer
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QGridLayout, QWidget
from qfluentwidgets import (
    CardWidget,
    BodyLabel,
    FluentIcon,
    TransparentToolButton,
    ImageLabel,
    PushButton,
    SimpleCardWidget,
)
from qfluentwidgets.components.widgets.card_widget import CardSeparator

from app.utils.utils import get_icon, get_unified_font
from app.interfaces.workflow_manager_interface.utils.utils import ThumbnailCache


class ActionCard(SimpleCardWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.home = parent
        self.setFixedSize(400, 330)
        self.setBorderRadius(12)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(10)

        title = BodyLabel(self.tr("创建画布"))
        title.setFont(get_unified_font(13, True))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(CardSeparator())

        btn_container = QWidget(self)
        btn_layout = QVBoxLayout(btn_container)
        btn_layout.setSpacing(8)

        create_btn = PushButton(
            text=self.tr("新建画布"), icon=FluentIcon.ADD, parent=self
        )
        create_btn.clicked.connect(lambda: self.home.new_canvas())
        create_btn.setIconSize(QSize(16, 16))
        create_btn.setFont(get_unified_font(12))

        template_btn = PushButton(
            text=self.tr("从模板创建"), icon=get_icon("从模板创建"), parent=self
        )
        template_btn.clicked.connect(lambda: self.home.new_canvas(from_template=True))
        template_btn.setIconSize(QSize(16, 16))
        template_btn.setFont(get_unified_font(12))

        import_btn = PushButton(
            text=self.tr("导入画布"), icon=get_icon("导入文件"), parent=self
        )
        import_btn.clicked.connect(lambda: self.home.import_canvas())
        import_btn.setIconSize(QSize(16, 16))
        import_btn.setFont(get_unified_font(12))

        btn_layout.addWidget(create_btn)
        btn_layout.addWidget(template_btn)
        btn_layout.addWidget(import_btn)
        layout.addWidget(btn_container, 1)


class WorkflowCard(CardWidget):
    def __init__(
        self,
        file_path: Path = None,
        parent: Optional[QWidget] = None,
        file_info: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(parent)
        self.home = parent
        self.file_path = file_path
        self._file_info = file_info
        self.image_label = None
        self._image_loader = None
        self._image_thread = None
        self._load_cancelled = False
        self._preview_loaded = False
        self._cache_key = f"card_{file_path}" if file_path else None

        self.setFixedSize(400, 330)
        self.setBorderRadius(12)

        self.workflow_name = ".".join(file_path.stem.split(".")[:-1])
        self._setup_ui()
        self.setCursor(Qt.PointingHandCursor)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        self.setStyleSheet("""
                   QWidget#WorkflowCardTitle { font-size: 14px; font-weight: 600; }
                   QLabel.workflowMetaKey { color: #666; }
                   QLabel.workflowMetaVal { color: #333; }
               """)

        # 标题（可点击区域的一部分）
        self.name_label = BodyLabel(self.workflow_name)
        self.name_label.setFont(get_unified_font(18, True))
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setWordWrap(True)
        self.name_label.setObjectName("WorkflowCardTitle")
        layout.addWidget(self.name_label)

        # 预览图
        self.image_label = ImageLabel(self)
        self.image_label.setBorderRadius(8, 8, 8, 8)
        self.image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.image_label, 0, Qt.AlignCenter)

        preview_path = self._get_preview_path()
        QTimer.singleShot(0, lambda: self._load_preview_async(preview_path))

        # 信息栏
        bottom_layout = QHBoxLayout()
        # 元数据
        meta_grid = QGridLayout()
        meta_grid.setVerticalSpacing(8)
        meta_grid.setHorizontalSpacing(8)

        if self._file_info:
            create_time = self._file_info.get("ctime", "未知")
            change_time = self._file_info.get("mtime", "未知")
        else:
            try:
                stat = self.file_path.stat()
                create_time = datetime.fromtimestamp(stat.st_ctime).strftime(
                    "%Y-%m-%d %H:%M"
                )
                change_time = datetime.fromtimestamp(stat.st_mtime).strftime(
                    "%Y-%m-%d %H:%M"
                )
            except Exception:
                create_time = change_time = "未知"

        # 保存时间标签的引用，方便后续更新
        k1 = BodyLabel("创建")
        v1 = BodyLabel(create_time)
        k2 = BodyLabel("修改")
        v2 = BodyLabel(change_time)

        # 设置对象名称，便于识别
        v1.setObjectName("create_time_label")
        v2.setObjectName("modify_time_label")

        meta_grid.addWidget(k1, 0, 0)
        meta_grid.addWidget(v1, 0, 1)
        meta_grid.addWidget(k2, 1, 0)
        meta_grid.addWidget(v2, 1, 1)
        bottom_layout.addLayout(meta_grid)

        # 保存时间标签的引用
        self.create_time_label = v1
        self.modify_time_label = v2

        # 按钮区域（仅保留编辑、复制、删除）
        copy_btn = TransparentToolButton(FluentIcon.COPY, self)
        copy_btn.setIconSize(QSize(20, 20))
        copy_btn.setToolTip(self.tr("复制画布"))
        copy_btn.clicked.connect(self._on_copy_clicked)

        edit_btn = TransparentToolButton(FluentIcon.EDIT, self)
        edit_btn.setIconSize(QSize(20, 20))
        edit_btn.setToolTip(self.tr("重命名"))
        edit_btn.clicked.connect(self._on_edit_clicked)

        delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
        delete_btn.setIconSize(QSize(20, 20))
        delete_btn.setToolTip(self.tr("删除画布"))
        delete_btn.clicked.connect(self._on_delete_clicked)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(edit_btn)
        btn_layout.addWidget(copy_btn)
        btn_layout.addWidget(delete_btn)
        bottom_layout.addLayout(btn_layout)
        layout.addLayout(bottom_layout)

    def _load_preview_async(self, preview_path: Path):
        """异步加载预览图，使用缓存"""
        if self._load_cancelled:
            return

        cache_key = f"{preview_path}_card_330x220"
        cached = ThumbnailCache.get(cache_key)
        if cached and not cached.isNull():
            if not self._load_cancelled:
                self.image_label.setPixmap(cached.copy())
                self.image_label.setFixedSize(cached.width(), cached.height())
                self._preview_loaded = True
            return

        if ThumbnailCache.is_loading(cache_key):
            return

        ThumbnailCache.set_loading(cache_key, True)

        def load():
            if self._load_cancelled:
                ThumbnailCache.set_loading(cache_key, False)
                return
            try:
                pixmap = QPixmap(str(preview_path))
                if not pixmap.isNull():
                    scaled = pixmap.scaled(
                        330, 220, Qt.IgnoreAspectRatio, Qt.SmoothTransformation
                    )
                    ThumbnailCache.put(cache_key, scaled.copy())
                    if not self._load_cancelled:
                        self.image_label.setPixmap(scaled)
                        self.image_label.setFixedSize(scaled.width(), scaled.height())
                        self._preview_loaded = True
                else:
                    if not self._load_cancelled:
                        QTimer.singleShot(0, self._create_placeholder)
            except Exception:
                if not self._load_cancelled:
                    QTimer.singleShot(0, self._create_placeholder)
            finally:
                ThumbnailCache.set_loading(cache_key, False)

        QTimer.singleShot(50, load)

    def _create_placeholder(self):
        """创建"无预览图"占位"""
        self.image_label.setText(self.tr("无预览图"))
        self.image_label.setStyleSheet("""
            color: #999;
            background-color: #fafafa;
            border-radius: 8px;
            border: 1px dashed #e0e0e0;
            font-size: 12px;
        """)
        self.image_label.setFixedSize(300, 180)

    def _get_preview_path(self) -> Path:
        return self.file_path.parent / f"{self.workflow_name}.png"

    def refresh_preview(self):
        if self._load_cancelled:
            return
        preview_path = self._get_preview_path()
        if preview_path.exists():
            self._load_preview_async(preview_path)
        else:
            self._create_placeholder()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._on_open_clicked()
        super().mousePressEvent(event)

    def _on_open_clicked(self):
        if hasattr(self.home, "open_canvas"):
            self.home.open_canvas(self.file_path)

    def _on_copy_clicked(self):
        if hasattr(self.home, "duplicate_workflow"):
            self.home.duplicate_workflow(self.file_path)

    def _on_delete_clicked(self):
        if hasattr(self.home, "delete_workflow"):
            self.home.delete_workflow(self.file_path)

    def _on_edit_clicked(self):
        """编辑画布名称"""
        if hasattr(self.home, "edit_workflow"):
            self.home.edit_workflow(self.file_path)

    def closeEvent(self, event):
        self._load_cancelled = True
        if self._image_thread and self._image_thread.isRunning():
            self._image_thread.quit()
            self._image_thread.wait()
        super().closeEvent(event)

    def hideEvent(self, event):
        self._load_cancelled = True
        super().hideEvent(event)

    def showEvent(self, event):
        self._load_cancelled = False
        super().showEvent(event)
        needs_load = False
        if not self._preview_loaded:
            needs_load = True
        elif self.image_label.pixmap() is None or self.image_label.pixmap().isNull():
            needs_load = True

        if needs_load:
            preview_path = self._get_preview_path()
            if preview_path.exists():
                self._load_preview_async(preview_path)
            else:
                self._create_placeholder()

    def sizeHint(self):
        default_width = 320
        if self.parent():
            parent_width = self.parent().width()
            if parent_width > 100:
                ideal_width = max(280, min(450, (parent_width - 60) // 2))
                return QSize(ideal_width, 340)
        return QSize(default_width, 340)

    def update_file_info(self, file_info: Optional[Dict[str, Any]] = None):
        """更新卡片上的文件信息"""
        self._file_info = file_info

        # 使用保存的标签引用直接更新文本
        if file_info:
            create_time = file_info.get("ctime", "未知")
            change_time = file_info.get("mtime", "未知")
        else:
            try:
                stat = self.file_path.stat()
                create_time = datetime.fromtimestamp(stat.st_ctime).strftime(
                    "%Y-%m-%d %H:%M"
                )
                change_time = datetime.fromtimestamp(stat.st_mtime).strftime(
                    "%Y-%m-%d %H:%M"
                )
            except Exception:
                create_time = change_time = "未知"

        # 直接更新时间标签
        if hasattr(self, "create_time_label") and self.create_time_label:
            self.create_time_label.setText(create_time)
        if hasattr(self, "modify_time_label") and self.modify_time_label:
            self.modify_time_label.setText(change_time)
