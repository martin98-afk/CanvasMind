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
        self.setSizePolicy(1, 0)
        self.setStyleSheet("""
            CardWidget {
                background-color: rgba(40, 40, 45, 252);
                border: 1px solid #6366f1;
                border-radius: 10px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 10, 14, 10)
        main_layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(10)

        title_icon = QLabel("📋", self)
        title_icon.setFont(QFont("", 14))

        title = QLabel("待办事项", self)
        title.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        title.setStyleSheet("color: #f0f0f0;")

        self.progress_label = QLabel("", self)
        self.progress_label.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        self.progress_label.setStyleSheet("color: #818cf8;")

        header.addWidget(title_icon)
        header.addWidget(title)
        header.addWidget(self.progress_label)
        header.addStretch()

        close_btn = QPushButton("✕", self)
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.1);
                color: #a0a0a0;
                border: none;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
                color: #ffffff;
            }
        """)
        close_btn.clicked.connect(self._on_close)
        header.addWidget(close_btn)

        self.content_label = QLabel("暂无待办", self)
        self.content_label.setFont(QFont("Microsoft YaHei", 10))
        self.content_label.setStyleSheet("color: #b0b0b0;")
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
                status_icon = "✓"
            else:
                status_icon = "○"

            priority_colors = {"high": "#f87171", "medium": "#fbbf24", "low": "#34d399"}
            priority_color = priority_colors.get(priority, "#fbbf24")

            priority_labels = {"high": "🔴", "medium": "🟡", "low": "🟢"}
            priority_icon = priority_labels.get(priority, "🟡")

            if status == "completed":
                content_style = "color: #808080; text-decoration: line-through;"
            else:
                content_style = "color: #e0e0e0;"

            lines.append(
                f'<span style="color: #818cf8; font-weight: bold;">{status_icon}</span> '
                f'<span style="color: {priority_color};">{priority_icon}</span> '
                f'<span style="{content_style}">{content}</span>'
            )

        total = len(self._todo_list)
        if completed == total and completed > 0:
            progress_text = f"🎉 {completed}/{total} 全部完成"
            self.progress_label.setStyleSheet("color: #34d399; font-weight: bold;")
        else:
            progress_text = f"{completed}/{total}"
            self.progress_label.setStyleSheet("color: #818cf8; font-weight: bold;")

        self.progress_label.setText(progress_text)
        self.content_label.setText("<br>".join(lines))

    def clear(self):
        """清空 TODO 显示"""
        self._todo_list = []
        self.setVisible(False)
