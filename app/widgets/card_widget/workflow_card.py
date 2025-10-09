# -*- coding: utf-8 -*-
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QGridLayout
from PyQt5.QtWidgets import QGraphicsDropShadowEffect
from qfluentwidgets import CardWidget, BodyLabel, PrimaryPushButton, FluentIcon, ToolButton, ImageLabel


class WorkflowCard(CardWidget):
    def __init__(self, file_path: Path, parent=None):
        super().__init__(parent)
        self.home = parent
        self.file_path = file_path
        self.workflow_name = file_path.stem.split(".")[0]  # 保留原有逻辑
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedHeight(280)
        self.setFixedWidth(320)
        self.setBorderRadius(12)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        self.setStyleSheet("""
            QWidget#WorkflowCardTitle { font-size: 14px; font-weight: 600; }
            QLabel.workflowMetaKey { color: #666; }
            QLabel.workflowMetaVal { color: #333; }
        """)
        # === 尝试加载预览图 ===
        preview_path = self._get_preview_path()
        if preview_path and preview_path.exists():
            # 创建图片标签
            img_label = ImageLabel(str(preview_path), self)
            img_label.setFixedSize(200, 100)
            img_label.setBorderRadius(8, 8, 8, 8)
            layout.addWidget(img_label, 0, Qt.AlignCenter)
        else:
            # 占位符：无预览图
            placeholder = BodyLabel("无预览图")
            placeholder.setFixedSize(200, 100)
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #aaa; background-color: #f5f5f5; border-radius: 8px;")
            layout.addWidget(placeholder, 0, Qt.AlignCenter)

        # 标题
        name_label = BodyLabel(self.workflow_name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        name_label.setObjectName("WorkflowCardTitle")
        layout.addWidget(name_label)

        # 信息（网格布局）
        meta_grid = QGridLayout()
        meta_grid.setVerticalSpacing(4)
        meta_grid.setHorizontalSpacing(8)
        row = 0
        try:
            stat = self.file_path.stat()
            create_time = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M")
            change_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            size_kb = max(1, int(stat.st_size / 1024))
            k1 = BodyLabel("创建")
            k1.setProperty("class", "workflowMetaKey")
            v1 = BodyLabel(create_time)
            v1.setProperty("class", "workflowMetaVal")
            k2 = BodyLabel("修改")
            k2.setProperty("class", "workflowMetaKey")
            v2 = BodyLabel(change_time)
            v2.setProperty("class", "workflowMetaVal")
            k3 = BodyLabel("大小")
            k3.setProperty("class", "workflowMetaKey")
            v3 = BodyLabel(f"{size_kb} KB")
            v3.setProperty("class", "workflowMetaVal")
            meta_grid.addWidget(k1, row, 0); meta_grid.addWidget(v1, row, 1); row += 1
            meta_grid.addWidget(k2, row, 0); meta_grid.addWidget(v2, row, 1); row += 1
            meta_grid.addWidget(k3, row, 0); meta_grid.addWidget(v3, row, 1); row += 1
        except Exception:
            k = BodyLabel("信息")
            k.setProperty("class", "workflowMetaKey")
            v = BodyLabel("未知")
            v.setProperty("class", "workflowMetaVal")
            meta_grid.addWidget(k, row, 0); meta_grid.addWidget(v, row, 1)
        layout.addLayout(meta_grid)

        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        open_btn = PrimaryPushButton("打开画布", self, FluentIcon.EDIT)
        open_btn.setFixedHeight(28)
        open_btn.setFixedWidth(140)
        open_btn.clicked.connect(self._on_open_clicked)

        tool_layout = QHBoxLayout()
        tool_layout.setSpacing(4)

        copy_btn = ToolButton(FluentIcon.COPY, self)
        copy_btn.setToolTip("复制画布")
        copy_btn.clicked.connect(self._on_copy_clicked)

        delete_btn = ToolButton(FluentIcon.DELETE, self)
        delete_btn.setToolTip("删除画布")
        delete_btn.clicked.connect(self._on_delete_clicked)

        # 统一尺寸
        copy_btn.setFixedSize(28, 28)
        delete_btn.setFixedSize(28, 28)

        tool_layout.addWidget(copy_btn)
        tool_layout.addWidget(delete_btn)

        btn_layout.addWidget(open_btn)
        btn_layout.addStretch()
        btn_layout.addLayout(tool_layout)

        layout.addLayout(btn_layout)

        # 悬浮阴影效果
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(22)
        self._shadow.setXOffset(0)
        self._shadow.setYOffset(4)
        self._shadow.setColor(Qt.black)
        self.setGraphicsEffect(None)

    def enterEvent(self, event):
        try:
            self.setGraphicsEffect(self._shadow)
        except Exception:
            pass
        super().enterEvent(event)

    def leaveEvent(self, event):
        try:
            self.setGraphicsEffect(None)
        except Exception:
            pass
        super().leaveEvent(event)

    def _get_preview_path(self) -> Path:
        """返回对应的预览图路径（xxx.workflow.json → xxx.png）"""
        base_name = self.file_path.parent / self.file_path.stem.split(".")[0]
        return base_name.with_suffix(".png")

    def _on_open_clicked(self):
        if hasattr(self.home, 'open_canvas'):
            self.home.open_canvas(self.file_path)

    def _on_copy_clicked(self):
        if hasattr(self.home, 'duplicate_workflow'):
            self.home.duplicate_workflow(self.file_path)

    def _on_delete_clicked(self):
        if hasattr(self.home, 'delete_workflow'):
            self.home.delete_workflow(self.file_path)