# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QTextEdit,
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QPainter, QLinearGradient, QColor
from qfluentwidgets import CardWidget
from app.utils.utils import get_unified_font


class ToolFloatingWidget(CardWidget):
    """工具执行悬浮框组件 - 当工具执行时间过长时显示"""

    cancelled = pyqtSignal()
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._task_start_time = None
        self._is_running = False
        self._current_tool = None
        self._current_process = None
        self._setup_ui()

    def _setup_ui(self):
        self.setSizePolicy(1, 0)
        self.setFixedHeight(80)
        self.setStyleSheet("""
            CardWidget {
                background-color: rgba(33, 33, 38, 250);
                border: 1px solid #f59e0b;
                border-radius: 8px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 10, 16, 10)
        main_layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(10)

        self.icon_label = QLabel("⚙️", self)
        self.icon_label.setFont(get_unified_font(14))

        self.tool_name_label = QLabel("", self)
        self.tool_name_label.setFont(get_unified_font(10))
        self.tool_name_label.setStyleSheet(
            "color: #64b5f6; background-color: rgba(100, 181, 246, 0.1); padding: 2px 8px; border-radius: 4px;"
        )

        self.title_label = QLabel("正在执行工具", self)
        self.title_label.setFont(get_unified_font(11, True))
        self.title_label.setStyleSheet("color: #f59e0b;")

        header.addWidget(self.icon_label)
        header.addWidget(self.tool_name_label)
        header.addWidget(self.title_label)
        header.addStretch()

        self.cancel_btn = QPushButton("中止", self)
        self.cancel_btn.setFixedSize(50, 24)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e53935;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c62828;
            }
            QPushButton:disabled {
                background-color: #757575;
            }
        """)
        self.cancel_btn.clicked.connect(self._on_cancel)
        header.addWidget(self.cancel_btn)

        main_layout.addLayout(header)

        self.task_label = QLabel("等待执行...", self)
        self.task_label.setFont(get_unified_font(10))
        self.task_label.setStyleSheet("color: #9e9e9e;")
        self.task_label.setWordWrap(True)
        self.task_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        main_layout.addWidget(self.task_label)

    def _on_close(self):
        self.setVisible(False)
        self.closed.emit()

    def _on_cancel(self):
        self._is_running = False
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("已中止")
        self.title_label.setText("执行已中止")
        self.title_label.setStyleSheet("color: #ef5350;")
        self.cancelled.emit()

    def set_process(self, process):
        """设置当前进程以便中止"""
        self._current_process = process

    def start_tool(self, tool_name: str, args: dict = None):
        """开始执行工具"""
        import time
        import json
        from PyQt5.QtWidgets import QApplication

        self._task_start_time = time.time()
        self._is_running = True
        self._current_tool = tool_name
        self._current_process = None

        self.title_label.setText("正在执行工具")
        self.title_label.setStyleSheet("color: #f59e0b;")

        self.icon_label.setText("⚙️")

        self.tool_name_label.setText(f" {tool_name} ")

        args_preview = ""
        if args:
            args_str = json.dumps(args, ensure_ascii=False)
            if len(args_str) > 60:
                args_preview = f" | {args_str[:60]}..."
            else:
                args_preview = f" | {args_str}"

        self.task_label.setText(f"⏳ 正在运行{args_preview}")

        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("中止")

        self.setVisible(True)
        self.raise_()
        QApplication.processEvents()
        QApplication.processEvents()

    def _create_spinner(self):
        from PyQt5.QtCore import QByteArray

        return None

    def _append_progress(self, text: str):
        self.task_label.setText(text)

    def update_progress(self, message: str):
        """更新进度"""
        import time

        elapsed = time.time() - self._task_start_time if self._task_start_time else 0

        if elapsed > 3:
            self.setVisible(True)

        self.task_label.setText(f"⏳ {message}")

    def add_tool_call(self, tool_name: str, args: dict = None):
        """添加工具调用"""
        import time

        elapsed = time.time() - self._task_start_time if self._task_start_time else 0

        if elapsed > 3:
            self.setVisible(True)

        self.tool_name_label.setText(f" {tool_name} ")

    def add_tool_result(self, result: str, success: bool = True):
        """添加工具结果"""
        import time

        elapsed = time.time() - self._task_start_time if self._task_start_time else 0

        if elapsed > 3:
            self.setVisible(True)

    def finish_tool(self, result: str = None, success: bool = True):
        """完成工具执行"""
        self._is_running = False
        self._current_process = None

        self.icon_label.setText("✅" if success else "❌")

        if success:
            self.title_label.setText("执行完成")
            self.title_label.setStyleSheet("color: #66bb6a;")
            self.task_label.setText("✓ 工具执行成功")
        else:
            self.title_label.setText("执行失败")
            self.title_label.setStyleSheet("color: #ef5350;")
            error_msg = result if result else "执行失败"
            self.task_label.setText(f"✗ {error_msg[:50]}")

        self.cancel_btn.setVisible(False)

        self.setVisible(True)
        self.raise_()

        QTimer.singleShot(2000, self.hide)

    def is_cancelled(self) -> bool:
        """检查是否已被中止"""
        return not self._is_running

    def clear(self):
        """清空显示"""
        self._task_start_time = None
        self._is_running = False
        self._current_tool = None
        self._current_process = None
        self.setVisible(False)
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setVisible(True)
        self.cancel_btn.setText("中止")
        self.icon_label.setText("⚙️")
        self.title_label.setText("正在执行工具")
        self.title_label.setStyleSheet("color: #f59e0b;")

    def show_if_needed(self, elapsed: float):
        """根据耗时决定是否显示"""
        if elapsed > 3:
            self.setVisible(True)
