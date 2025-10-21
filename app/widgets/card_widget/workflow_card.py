from datetime import datetime
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QLabel
from qfluentwidgets import CardWidget, BodyLabel, FluentIcon, TransparentToolButton, ImageLabel


class WorkflowCard(CardWidget):
    def __init__(
        self,
        file_path: Path = None,
        parent: Optional[QWidget] = None,
        file_info: Optional[Dict[str, Any]] = None,
        type: str = "normal"
    ):
        super().__init__(parent)
        self.home = parent
        self.file_path = file_path
        self._file_info = file_info
        self.image_label = None
        self._image_loader = None
        self._image_thread = None

        # 设置卡片尺寸范围
        self.setMinimumSize(280, 300)
        self.setMaximumSize(400, 400)
        self.setBorderRadius(12)

        if type == "normal":
            self.workflow_name = file_path.stem.split(".")[0]
            self._setup_ui()
            # ✅ 点击卡片任意位置打开画布
            self.setCursor(Qt.PointingHandCursor)
        elif type == "create":
            self.mousePressEvent = lambda e: self.home.new_canvas()
            self.setCursor(Qt.PointingHandCursor)
            self._setup_create_ui()
        elif type == "import":
            self.mousePressEvent = lambda e: self.home.import_canvas()
            self.setCursor(Qt.PointingHandCursor)
            self._setup_import_ui()

    def _setup_create_ui(self):
        layout = QVBoxLayout(self)
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

    def _setup_import_ui(self):
        layout = QVBoxLayout(self)
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
        self.name_label.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setWordWrap(True)
        self.name_label.setObjectName("WorkflowCardTitle")
        layout.addWidget(self.name_label)

        # 预览图
        self.image_label = ImageLabel(self)
        self.image_label.setBorderRadius(8,8,8,8)
        self.image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.image_label, 0, Qt.AlignCenter)

        preview_path = self._get_preview_path()
        if preview_path.exists():
            self._load_and_scale_preview(preview_path)
        else:
            self._create_placeholder()

        # 信息栏
        bottom_layout = QHBoxLayout()
        # 元数据
        meta_grid = QGridLayout()
        meta_grid.setVerticalSpacing(8)
        meta_grid.setHorizontalSpacing(8)

        if self._file_info:
            create_time = self._file_info.get('ctime', '未知')
            change_time = self._file_info.get('mtime', '未知')
        else:
            try:
                stat = self.file_path.stat()
                create_time = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M")
                change_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            except Exception:
                create_time = change_time = "未知"

        k1 = BodyLabel("创建")
        v1 = BodyLabel(create_time)
        k2 = BodyLabel("修改")
        v2 = BodyLabel(change_time)

        meta_grid.addWidget(k1, 0, 0)
        meta_grid.addWidget(v1, 0, 1)
        meta_grid.addWidget(k2, 1, 0)
        meta_grid.addWidget(v2, 1, 1)
        bottom_layout.addLayout(meta_grid)

        # 按钮区域（仅保留编辑、复制、删除）
        copy_btn = TransparentToolButton(FluentIcon.COPY, self)
        copy_btn.setToolTip("复制画布")
        copy_btn.clicked.connect(self._on_copy_clicked)
        copy_btn.setFixedSize(28, 28)

        edit_btn = TransparentToolButton(FluentIcon.EDIT, self)
        edit_btn.setToolTip("重命名")
        edit_btn.clicked.connect(self._on_edit_clicked)
        edit_btn.setFixedSize(28, 28)

        delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
        delete_btn.setToolTip("删除画布")
        delete_btn.clicked.connect(self._on_delete_clicked)
        delete_btn.setFixedSize(28, 28)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(edit_btn)
        btn_layout.addWidget(copy_btn)
        btn_layout.addWidget(delete_btn)
        bottom_layout.addLayout(btn_layout)
        layout.addLayout(bottom_layout)

    def _load_and_scale_preview(self, preview_path: Path):
        """加载并缩放预览图到统一尺寸（300x180）"""
        try:
            pixmap = QPixmap(str(preview_path))
            if pixmap.isNull():
                self._create_placeholder()
                return

            # 保持宽高比，居中裁剪（或用 Qt.KeepAspectRatio）
            scaled_pixmap = pixmap.scaled(330, 220, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

            # 如果你想强制填满（可能变形），用：
            # scaled_pixmap = pixmap.scaled(target_width, target_height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.setFixedSize(scaled_pixmap.width(), scaled_pixmap.height())
        except Exception:
            self._create_placeholder()

    def _create_placeholder(self):
        """创建“无预览图”占位"""
        self.image_label.setText("无预览图")
        self.image_label.setStyleSheet("""
            color: #999;
            background-color: #fafafa;
            border-radius: 8px;
            border: 1px dashed #e0e0e0;
            font-size: 12px;
        """)
        self.image_label.setFixedSize(300, 180)  # ✅ 统一占位尺寸

    def _get_preview_path(self) -> Path:
        base_name = self.file_path.parent / self.file_path.stem.split(".")[0]
        return base_name.with_suffix(".png")

    def refresh_preview(self):
        preview_path = self._get_preview_path()
        if preview_path.exists():
            self._load_and_scale_preview(preview_path)
        else:
            self._create_placeholder()

    # ✅ 点击卡片任意位置打开画布
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._on_open_clicked()
        super().mousePressEvent(event)

    def _on_open_clicked(self):
        if hasattr(self.home, 'open_canvas'):
            self.home.open_canvas(self.file_path)

    def _on_copy_clicked(self):
        if hasattr(self.home, 'duplicate_workflow'):
            self.home.duplicate_workflow(self.file_path)

    def _on_delete_clicked(self):
        if hasattr(self.home, 'delete_workflow'):
            self.home.delete_workflow(self.file_path)

    def _on_edit_clicked(self):
        """编辑画布名称"""
        if hasattr(self.home, 'edit_workflow'):
            self.home.edit_workflow(self.file_path)

    def closeEvent(self, event):
        if self._image_thread and self._image_thread.isRunning():
            self._image_thread.quit()
            self._image_thread.wait()
        super().closeEvent(event)

    def sizeHint(self):
        default_width = 320
        if self.parent():
            parent_width = self.parent().width()
            if parent_width > 100:
                ideal_width = max(280, min(450, (parent_width - 60) // 2))
                return QSize(ideal_width, 340)
        return QSize(default_width, 340)