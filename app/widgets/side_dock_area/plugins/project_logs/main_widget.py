# -*- coding: utf-8 -*-
import os
import re
from pathlib import Path
from PyQt5.QtCore import Qt, QFileSystemWatcher, QTimer
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from qfluentwidgets import (
    StrongBodyLabel, setFont, SmoothScrollArea, SimpleCardWidget
)
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
        from PyQt5.QtWidgets import QTextEdit
        from PyQt5.QtGui import QFont
        self.log_text = QTextEdit()
        font = QFont("Consolas", 10)
        self.log_text.setFont(font)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QTextEdit.WidgetWidth)
        layout.addWidget(self.log_text)

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


class ProjectLogTool(ToolWindow):
    name = "项目日志"
    icon = get_icon("日志")
    default_position = DockPosition.BOTTOM
    project_path = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ProjectLogTool")
        self._setup_watcher()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(16)

        # 分割左右
        splitter = QHBoxLayout()
        splitter.setSpacing(20)

        # 左侧：微服务日志
        self.service_log_card = LogCardForTool("微服务日志 (service.log)")
        splitter.addWidget(self.service_log_card)

        # 右侧：运行日志
        self.run_log_card = LogCardForTool("运行日志 (run.log)")
        splitter.addWidget(self.run_log_card)

        main_layout.addLayout(splitter)

        # 初始提示
        self.service_log_card.set_content("微服务未启动，无日志")
        self.run_log_card.set_content("尚未运行项目")

    def _setup_watcher(self):
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self._on_dir_changed)

    def _load_log_file(self, path):
        if not path or not os.path.exists(path):
            return ""
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        except Exception:
            return ""

    def _on_dir_changed(self, dir_path):
        if not self.project_path or dir_path != self.project_path:
            return
        # 检查两个日志文件
        service_content = self._load_log_file(os.path.join(self.project_path, "service.log"))
        run_content = self._load_log_file(os.path.join(self.project_path, "run.log"))
        self.service_log_card.set_content(service_content or "微服务未启动，无日志")
        self.run_log_card.set_content(run_content or "尚未运行项目")

    def refresh(self, project_path):
        """切换项目并开始监听"""
        self.project_path = project_path
        project_dir = Path(project_path)

        # 移除旧监听
        watched = self.watcher.directories()
        if watched:
            self.watcher.removePaths(watched)

        # 监听新目录
        if project_dir.exists():
            self.watcher.addPath(str(project_dir))

        # 立即加载日志
        service_content = self._load_log_file(str(project_dir / "service.log"))
        run_content = self._load_log_file(str(project_dir / "run.log"))

        self.service_log_card.set_content(service_content or "微服务未启动，无日志")
        self.run_log_card.set_content(run_content or "尚未运行项目")