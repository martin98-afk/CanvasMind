# -*- coding: utf-8 -*-
from pathlib import Path

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from qfluentwidgets import CardWidget, BodyLabel, PrimaryPushButton, FluentIcon, ToolButton
import os
from datetime import datetime


class WorkflowCard(CardWidget):
    def __init__(self, file_path: Path, parent=None):
        super().__init__(parent)
        self.home = parent
        self.file_path = file_path
        self.workflow_name = file_path.stem.split(".")[0]  # ✅ 直接用 .stem，它已经去掉了所有后缀（包括 .workflow.json）
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedHeight(220)
        self.setFixedWidth(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 标题
        name_label = BodyLabel(self.workflow_name)
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

        # 按钮区域：打开 + 右侧工具按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        open_btn = PrimaryPushButton("打开画布", self, FluentIcon.EDIT)
        open_btn.setFixedWidth(100)
        open_btn.clicked.connect(self._on_open_clicked)

        # 工具按钮（复制、删除）
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

    def _on_open_clicked(self):
        if hasattr(self.home, 'open_canvas'):
            self.home.open_canvas(self.file_path)

    def _on_copy_clicked(self):
        if hasattr(self.home, 'duplicate_workflow'):
            self.home.duplicate_workflow(self.file_path)

    def _on_delete_clicked(self):
        if hasattr(self.home, 'delete_workflow'):
            self.home.delete_workflow(self.file_path)