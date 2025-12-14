# -*- coding: utf-8 -*-
import os
import re
import threading
from pathlib import Path

from PyQt5.QtCore import Qt, QFileSystemWatcher, QThread, pyqtSignal, QTimer
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, QTextEdit
from qfluentwidgets import (
    StrongBodyLabel, setFont, TextEdit
)
from watchfiles import watch, Change

from app.utils.utils import ansi_to_html, get_icon
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class LogCardForTool(QWidget):
    """简化版 CollapsibleLogCard，用于日志工具，固定展开"""
    LEVEL_COLORS = {
        'DEBUG': '#808080',
        'INFO': '#9cdcfe',
        'WARNING': '#ffcb6b',
        'WARN': '#ffcb6b',
        'ERROR': '#f44747',
        'Error': '#f44747',
        'CRITICAL': '#f44747',
        'SUCCESS': '#32cd32',
    }

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title = title
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 标题
        title_label = StrongBodyLabel(self.title)
        setFont(title_label, 12)
        layout.addWidget(title_label)

        # 日志内容
        self.log_text = TextEdit(self)
        font = self.log_text.font()
        font.setFamily("Consolas")  # 或 "Courier New", "Fira Code", "JetBrains Mono"
        font.setPointSize(10)
        self.log_text.setFont(font)
        self.log_text.setStyleSheet("border: none; color: #d4d4d4; background-color: #1e1e1e; border-radius: 4px; padding: 8px;")
        self.log_text.setReadOnly(True)
        self.log_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.log_text.setSizeAdjustPolicy(TextEdit.AdjustToContents)
        self.log_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.log_text.setLineWrapMode(QTextEdit.WidgetWidth)
        layout.addWidget(self.log_text, 1)

    def set_content(self, content: str):
        """设置日志内容，支持 ANSI 转 HTML + 级别着色"""
        if not content.strip():
            self.log_text.setHtml("<pre style='color:#666;'>（无内容）</pre>")
            return

        # 先用 ansi_to_html 处理（保留颜色）
        html_lines = []
        for line in content.splitlines():
            # 先转 ANSI → HTML
            line_html = ansi_to_html(line)
            # 再检测日志级别，覆盖颜色（优先级更高）
            color = "#d4d4d4"
            for level, col in self.LEVEL_COLORS.items():
                if re.search(rf'\b{level}\b', line, re.IGNORECASE):
                    color = col
                    break
            # 提取纯文本用于显示（但保留 HTML 标签）
            html_lines.append(f'<pre style="color:{color}; margin:0; padding:0;">{line_html}</pre>')

        full_html = "\n".join(html_lines)
        self.log_text.setHtml(full_html)
        # 滚动到底部
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())


class LogWatcherThread(QThread):
    """后台线程，使用 watchfiles 监听日志文件变化"""
    file_changed = pyqtSignal(str)  # 发出变更的文件路径

    def __init__(self, service_log_path: str, run_log_path: str, parent=None):
        super().__init__(parent)
        self.service_log = service_log_path
        self.run_log = run_log_path
        self._stop_event = threading.Event()

    def run(self):
        # 构建要监听的文件列表（必须存在才能监听，不存在则跳过）
        watch_files = [self.service_log, self.run_log]

        if not watch_files:
            return

        try:
            for changes in watch(*watch_files, stop_event=self._stop_event):
                for change_type, path in changes:
                    # watchfiles 会报告任何变更（modified/added等），我们只关心内容变化
                    if change_type in (Change.modified, Change.added):
                        self.file_changed.emit(path)
        except Exception:
            pass  # 线程退出时可能抛异常，忽略

    def stop(self):
        self._stop_event.set()
        self.wait(2000)  # 等待最多2秒


class ProjectLogTool(ToolWindow):
    name = "项目日志"
    icon = get_icon("日志")
    default_position = DockPosition.BOTTOM
    project_path = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ProjectLogTool")
        self._watcher_thread = None  # 用于管理后台线程

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(16)

        splitter = QHBoxLayout()
        splitter.setSpacing(24)

        self.service_log_card = LogCardForTool("微服务日志 (service.log)")
        self.run_log_card = LogCardForTool("运行日志 (run.log)")

        splitter.addWidget(self.service_log_card)
        splitter.addWidget(self.run_log_card)

        main_layout.addLayout(splitter)

        self.service_log_card.set_content("微服务未启动，无日志")
        self.run_log_card.set_content("尚未运行项目")

    def _load_log_file(self, path):
        if not path or not os.path.exists(path):
            return ""
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        except Exception:
            return ""

    def _on_log_file_changed(self, file_path: str):
        """槽函数：响应文件变更，延迟读取避免竞态"""
        if not self.project_path:
            return

        service_log = os.path.join(self.project_path, "service.log")
        run_log = os.path.join(self.project_path, "run.log")
        if file_path == service_log:
            content = self._load_log_file(service_log)
            self.service_log_card.set_content(content or "微服务未启动，无日志")
        elif file_path == run_log:
            content = self._load_log_file(run_log)
            self.run_log_card.set_content(content or "尚未运行项目")

    def refresh(self, project_path):
        # 停止旧线程
        if self._watcher_thread and self._watcher_thread.isRunning():
            self._watcher_thread.stop()
            self._watcher_thread.file_changed.disconnect()

        self.project_path = os.path.abspath(os.path.normpath(project_path))
        project_dir = Path(self.project_path)

        service_log = os.path.abspath(os.path.normpath(project_dir / "service.log"))
        run_log = os.path.abspath(os.path.normpath(project_dir / "run.log"))

        # 启动新监听线程（传入绝对路径）
        self._watcher_thread = LogWatcherThread(service_log, run_log)
        self._watcher_thread.file_changed.connect(self._on_log_file_changed)
        self._watcher_thread.start()

        # 加载初始内容（也用绝对路径）
        self._load_log_file(service_log)
        self._load_log_file(run_log)

    def closeEvent(self, event):
        """确保窗口关闭时线程退出"""
        if self._watcher_thread:
            self._watcher_thread.stop()
        super().closeEvent(event)