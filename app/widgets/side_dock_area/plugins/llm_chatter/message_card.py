# -*- coding: utf-8 -*-
from datetime import datetime
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
)
from qfluentwidgets import (
    FluentIcon, ToolTipFilter, ToolButton, CardWidget
)


class StreamingLabel(QLabel):
    def __init__(self, parent=None, update_interval_ms=30):
        super().__init__(parent)
        self.setText("")
        self.setWordWrap(True)
        self.setTextFormat(Qt.PlainText)

        self._buffer = []  # 临时缓存 incoming chunks
        self._timer = QTimer(self)
        self._timer.setInterval(update_interval_ms)  # 如 30ms ~ 60ms
        self._timer.timeout.connect(self._flush_buffer)

    def append_chunk(self, chunk: str):
        if not self._timer.isActive():
            self._timer.start()
        self._buffer.append(chunk)

    def _flush_buffer(self):
        if self._buffer:
            text = self.text() + "".join(self._buffer)
            self.setText(text)
            self._buffer.clear()


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
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(2)

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

        # 按钮容器（右上角）
        button_container = QWidget(self)
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(4)

        if self.role == "assistant":
            for icon, tooltip, slot in [
                (FluentIcon.COPY, "复制", lambda: self.copyRequested.emit(self.content)),
                (FluentIcon.SYNC, "重新生成", self.regenerateRequested.emit),
                (FluentIcon.DELETE, "删除", self.deleteRequested.emit),
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

        # 使用 QLabel 替代 TextBrowser（支持自动高度）
        self.content_label = StreamingLabel(self)
        self.content_label.setText(content)
        self.content_label.setWordWrap(True)
        self.content_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.content_label.setTextFormat(Qt.PlainText)  # 避免 HTML 干扰
        self.content_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                color: white;
                background: transparent;
                border: none;
                padding: 4px 0;
            }
        """)
        self.content_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        self.content_label.setMinimumHeight(1)

        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.content_label, 1)

        # 卡片背景色
        bg_color = "#2A2A2A" if self.role == "user" else "#1E1E1E"
        self.setStyleSheet(f"""
            CardWidget {{
                background-color: {bg_color};
                border: 1px solid #444444;
                border-radius: 8px;
            }}
        """)

        # 初始刷新高度
        self._update_height()

    def _update_height(self):
        """强制更新 QLabel 高度以适配内容"""
        self.content_label.adjustSize()
        # 触发布局重排
        self.updateGeometry()
        if self.parent():
            self.parent().updateGeometry()

    def update_content(self, new_content: str):
        self.content_label.append_chunk(new_content)
        # 延迟刷新高度，确保文本测量准确（尤其流式）
        QTimer.singleShot(0, self._update_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 关键：将内容标签的最大宽度限制为当前卡片的宽度（减去边距）
        if hasattr(self, 'content_label'):
            margin = 24  # 根据你的 setContentsMargins(12, 10, 12, 10) => 左右共 24
            max_width = self.width() - margin
            if max_width > 0:
                self.content_label.setMaximumWidth(max_width)
                # 强制重新计算高度
                self.content_label.adjustSize()
                self.updateGeometry()