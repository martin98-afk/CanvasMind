# -*- coding: utf-8 -*-
from pathlib import Path

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from qfluentwidgets import CardWidget, BodyLabel, PrimaryPushButton, FluentIcon, ToolButton
import os
from datetime import datetime


class WorkflowCard(CardWidget):
    def __init__(self, file_path: Path, parent=None):
        super().__init__(parent)
        self.home = parent
        self.file_path = file_path
        self.workflow_name = file_path.stem.split(".")[0]  # 去掉后缀
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

        # 可选：读取 workflow 内容获取描述（谨慎，避免卡顿）
        # try:
        #     with open(self.file_path, 'r', encoding='utf-8') as f:
        #         data = json.load(f)
        #         desc = data.get("metadata", {}).get("description", "")
        #         if desc:
        #             info_lines.append(f"描述: {desc[:50]}...")
        # except Exception:
        #     pass

        info_label = BodyLabel("\n".join(info_lines))
        info_label.setStyleSheet("color: #888888; font-size: 12px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # 打开按钮
        open_btn = PrimaryPushButton("打开画布", self, FluentIcon.EDIT)
        open_btn.clicked.connect(self._on_open_clicked)
        layout.addWidget(open_btn)

    def _on_open_clicked(self):
        # 触发信号，由父页面处理打开逻辑
        if hasattr(self.home, 'open_canvas'):
            self.home.open_canvas(self.file_path)