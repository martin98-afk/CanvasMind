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
from PyQt5.QtGui import QFont
from qfluentwidgets import CardWidget
from app.utils.utils import get_unified_font


class SubAgentFloatingWidget(CardWidget):
    """子智能体悬浮框组件"""

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._task_start_time = None
        self._setup_ui()

    def _setup_ui(self):
        self.setSizePolicy(1, 0)
        self.setFixedHeight(180)
        self.setStyleSheet("""
            CardWidget {
                background-color: rgba(30, 30, 30, 240);
                border: 1px solid #9C27B0;
                border-radius: 6px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(8)

        title = QLabel("🤖 子智能体执行中", self)
        title.setFont(get_unified_font(11, True))
        title.setStyleSheet("color: #9C27B0;")

        self.agent_label = QLabel("", self)
        self.agent_label.setFont(get_unified_font(10))
        self.agent_label.setStyleSheet("color: #FFA500;")

        header.addWidget(title)
        header.addWidget(self.agent_label)
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

        self.task_label = QLabel("正在启动...", self)
        self.task_label.setFont(get_unified_font(10))
        self.task_label.setStyleSheet("color: #ffffff;")
        self.task_label.setWordWrap(True)
        self.task_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.task_label.setAlignment(Qt.AlignTop)

        self.progress_text = QTextEdit("", self)
        self.progress_text.setFont(get_unified_font(9))
        self.progress_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        self.progress_text.setReadOnly(True)
        self.progress_text.setMaximumHeight(100)

        main_layout.addLayout(header)
        main_layout.addWidget(self.task_label)
        main_layout.addWidget(self.progress_text)

    def _on_close(self):
        self.setVisible(False)
        self.closed.emit()

    def start_task(self, agent_name: str, task_desc: str):
        """开始新任务"""
        import time

        self._task_start_time = time.time()
        self.progress_text.clear()
        self.setVisible(True)

        self.agent_label.setText(f"[{agent_name}]")

        desc_preview = task_desc[:80] + "..." if len(task_desc) > 80 else task_desc
        self.task_label.setText(desc_preview)
        self._append_progress("⏳ 正在启动子智能体...")

    def _append_progress(self, text: str):
        """追加进度信息"""
        current = self.progress_text.toPlainText()
        if current:
            self.progress_text.setPlainText(current + "\n" + text)
        else:
            self.progress_text.setPlainText(text)
        self.progress_text.verticalScrollBar().setValue(
            self.progress_text.verticalScrollBar().maximum()
        )

    def update_progress(self, message: str):
        """更新进度"""
        import time

        elapsed = time.time() - self._task_start_time if self._task_start_time else 0

        if elapsed > 3:
            self.setVisible(True)

        self._append_progress(f"⏳ {message}")

    def add_tool_call(self, tool_name: str, args: dict = None):
        """添加工具调用"""
        import time

        elapsed = time.time() - self._task_start_time if self._task_start_time else 0

        if elapsed > 3:
            self.setVisible(True)

        tool_info = f"🔧 调用工具: {tool_name}"
        if args:
            import json

            args_str = json.dumps(args, ensure_ascii=False, indent=2)[:100]
            tool_info += f"\n   参数: {args_str}"
        self._append_progress(tool_info)

    def add_tool_result(self, tool_name: str, result: str, success: bool = True):
        """添加工具结果"""
        import time

        elapsed = time.time() - self._task_start_time if self._task_start_time else 0

        if elapsed > 3:
            self.setVisible(True)

        status = "✅" if success else "❌"
        result_preview = str(result)[:200] if result else ""
        if len(str(result)) > 200:
            result_preview += "..."
        self._append_progress(f"{status} {tool_name} 结果: {result_preview}")

    def finish_task(self, result: str = None, success: bool = True):
        """完成任务"""
        if success:
            self._append_progress("\n✅ 执行完成")
        else:
            error_msg = result if result else "执行失败"
            self._append_progress(f"\n❌ {error_msg[:100]}")

        QTimer.singleShot(3000, self.hide)

    def clear(self):
        """清空显示"""
        self._task_start_time = None
        self.progress_text.clear()
        self.setVisible(False)
