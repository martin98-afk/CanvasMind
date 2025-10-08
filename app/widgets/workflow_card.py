# -*- coding: utf-8 -*-
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout
from qfluentwidgets import CardWidget, BodyLabel, PrimaryPushButton, FluentIcon, ToolButton, ImageLabel


class WorkflowCard(CardWidget):
    def __init__(self, file_path: Path, parent=None):
        super().__init__(parent)
        self.home = parent
        self.file_path = file_path
        self.workflow_name = file_path.stem.split(".")[0]  # 保留原有逻辑
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedHeight(220)
        self.setFixedWidth(310)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
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
        layout.addWidget(name_label)

        # 信息
        info_lines = []
        try:
            stat = self.file_path.stat()
            create_time = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M")
            info_lines.append(f"创建: {create_time}")
        except Exception:
            info_lines.append("创建: 未知")

        info_label = BodyLabel("\n".join(info_lines))
        info_label.setStyleSheet("color: #888888; font-size: 12px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        open_btn = PrimaryPushButton("打开画布", self, FluentIcon.EDIT)
        open_btn.setFixedWidth(130)
        open_btn.clicked.connect(self._on_open_clicked)

        tool_layout = QHBoxLayout()
        tool_layout.setSpacing(4)

        copy_btn = ToolButton(FluentIcon.COPY, self)
        copy_btn.setToolTip("复制画布")
        copy_btn.clicked.connect(self._on_copy_clicked)

        delete_btn = ToolButton(FluentIcon.DELETE, self)
        delete_btn.setToolTip("删除画布")
        delete_btn.clicked.connect(self._on_delete_clicked)

        tool_layout.addWidget(copy_btn)
        tool_layout.addWidget(delete_btn)

        btn_layout.addWidget(open_btn)
        btn_layout.addStretch()
        btn_layout.addLayout(tool_layout)

        layout.addLayout(btn_layout)

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