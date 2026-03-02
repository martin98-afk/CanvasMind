# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from qfluentwidgets import CardWidget


class TodoFloatingWidget(CardWidget):
    """TODO 悬浮框组件"""

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._todo_list = []
        self._setup_ui()

    def _setup_ui(self):
        self.setSizePolicy(1, 0)  # 水平扩展
        self.setStyleSheet("""
            CardWidget {
                background-color: rgba(30, 30, 30, 240);
                border: 1px solid #404040;
                border-radius: 6px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(4)

        # 标题栏
        header = QHBoxLayout()
        header.setSpacing(8)

        title = QLabel("📋 待办", self)
        title.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        title.setStyleSheet("color: #ffffff;")

        self.progress_label = QLabel("", self)
        self.progress_label.setFont(QFont("Microsoft YaHei", 10))
        self.progress_label.setStyleSheet("color: #64b5f6;")

        header.addWidget(title)
        header.addWidget(self.progress_label)
        header.addStretch()

        close_btn = QPushButton("✕", self)
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #757575;
                border: none;
                font-size: 12px;
            }
            QPushButton:hover {
                color: #ffffff;
                background-color: #404040;
                border-radius: 3px;
            }
        """)
        close_btn.clicked.connect(self._on_close)
        header.addWidget(close_btn)

        # 内容区域
        self.content_label = QLabel("暂无待办", self)
        self.content_label.setFont(QFont("Microsoft YaHei", 10))
        self.content_label.setStyleSheet("color: #ffffff;")
        self.content_label.setWordWrap(True)
        self.content_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.content_label.setAlignment(Qt.AlignTop)

        main_layout.addLayout(header)
        main_layout.addWidget(self.content_label, 1)

    def _on_close(self):
        self.setVisible(False)
        self.closed.emit()

    def update_todos(self, todos):
        """更新 TODO 列表显示"""
        self._todo_list = todos or []

        if not self._todo_list:
            self.setVisible(False)
            return

        self.setVisible(True)

        lines = []
        completed = 0
        for todo in self._todo_list:
            status = todo.get("status", "")
            content = todo.get("content", "")
            priority = todo.get("priority", "medium")

            if status == "completed":
                completed += 1
                status_icon = "✅"
            else:
                status_icon = "⬜"

            priority_colors = {"high": "#ef5350", "medium": "#ffb74d", "low": "#81c784"}
            priority_color = priority_colors.get(priority, "#ffb74d")

            lines.append(
                f'{status_icon} <span style="color: {priority_color};">●</span> <span style="color: #ffffff;">{content}</span>'
            )

        if completed == len(self._todo_list) and completed > 0:
            progress_text = f"🎉 全部完成 ({completed})"
            self.progress_label.setStyleSheet("color: #66bb6a; font-weight: bold;")
        else:
            progress_text = f"{completed}/{len(self._todo_list)}"
            self.progress_label.setStyleSheet("color: #64b5f6;")

        self.progress_label.setText(progress_text)
        self.content_label.setText("<br>".join(lines))

    def clear(self):
        """清空 TODO 显示"""
        self._todo_list = []
        self.setVisible(False)
