# -*- coding: utf-8 -*-
from datetime import datetime
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
)
from qfluentwidgets import (
    FluentIcon, ToolTipFilter, ToolButton, CardWidget, TextBrowser
)


class MessageCard(CardWidget):
    deleteRequested = pyqtSignal()
    copyRequested = pyqtSignal(str)
    regenerateRequested = pyqtSignal()

    def __init__(self, role: str, content: str, timestamp: str = None, parent=None):
        super().__init__(parent)
        self.role = role
        self.content = content
        self.timestamp = timestamp or datetime.now().strftime('%H:%M')
        self.setup_ui(content)

    def setup_ui(self, content: str):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(6)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(10)

        # 头像
        avatar_label = QLabel(self)
        avatar_text = "👤" if self.role == "user" else "🤖"
        avatar_color = "#FFFFFF" if self.role == "user" else "#4DA6FF"
        avatar_label.setText(avatar_text)
        avatar_label.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {avatar_color};")
        avatar_label.setFixedSize(28, 28)
        avatar_label.setAlignment(Qt.AlignCenter)
        name = "用户" if self.role == "user" else "大模型助手"
        name_label = QLabel(name, self)
        name_label.setStyleSheet("font-size: 15px; font-weight: bold; color: white;")
        top_layout.addWidget(avatar_label)
        top_layout.addWidget(name_label)
        if self.role == "assistant":
            time_label = QLabel(self.timestamp, self)
            time_label.setStyleSheet("font-size: 12px; color: #AAAAAA;")
            top_layout.addWidget(time_label)

        top_layout.addStretch()

        # 按钮（右上角）
        button_container = QWidget(self)
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(4)

        if self.role == "assistant":
            for icon, tooltip, slot in [
                (FluentIcon.COPY, "复制", lambda: self.copyRequested.emit(self.content)),
                (FluentIcon.SYNC, "重新生成", self.regenerateRequested),
                (FluentIcon.DELETE, "删除", self.deleteRequested),
            ]:
                btn = ToolButton(icon, self)
                btn.setToolTip(tooltip)
                btn.clicked.connect(slot)
                btn.setFixedSize(24, 24)
                btn.installEventFilter(ToolTipFilter(btn))
                button_layout.addWidget(btn)
        else:
            copy_btn = ToolButton(FluentIcon.COPY, self)
            copy_btn.setToolTip("复制")
            copy_btn.clicked.connect(lambda: self.copyRequested.emit(self.content))
            copy_btn.setFixedSize(24, 24)
            copy_btn.installEventFilter(ToolTipFilter(copy_btn))
            button_layout.addWidget(copy_btn)

        top_layout.addWidget(button_container)

        # TextBrowser - 关键设置
        self.content_textbrowser = TextBrowser(self)
        self.content_textbrowser.setReadOnly(True)
        self.content_textbrowser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content_textbrowser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content_textbrowser.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        self.content_textbrowser.setMaximumHeight(16777215)
        self.content_textbrowser.setMinimumHeight(1)
        self.content_textbrowser.setText(content)
        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.content_textbrowser, 1)

        # 卡片样式
        bg_color = "#2A2A2A" if self.role == "user" else "#1E1E1E"
        self.setStyleSheet(f"""
            CardWidget {{
                background-color: {bg_color};
                border: 1px solid #444444;
                border-radius: 8px;
            }}
        """)

    def update_content(self, new_content: str):
        self.content = new_content
        self.content_textbrowser.setText(new_content)