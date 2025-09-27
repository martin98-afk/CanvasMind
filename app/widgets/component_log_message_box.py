"""
@author: mading
@license: (C) Copyright: LUCULENT Corporation Limited.
@contact: mading@luculent.net
@file: component_log_message_box.py
@time: 2025/8/1 09:56
@desc: 
"""
import html
import re

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QTextCursor
from qfluentwidgets import MessageBoxBase, SubtitleLabel, TextEdit


class LogMessageBox(MessageBoxBase):
    LEVEL_COLORS = {
        'DEBUG': '#808080',
        'INFO': '#9cdcfe',
        'WARNING': '#ffcb6b',
        'WARN': '#ffcb6b',
        'ERROR': '#f44747',
        'Error': '#f44747',
        'CRITICAL': '#f44747',
    }

    def __init__(self, log_content, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel('模型日志', self)
        self._isDraggable = True
        self.setSizeGripEnabled(True)  # 显示大小调整手柄（在右下角）
        # 使用支持富文本的TextEdit
        self.logTextEdit = TextEdit(self)
        self.logTextEdit.setReadOnly(True)
        self.logTextEdit.setLineWrapMode(TextEdit.NoWrap)  # 禁用自动换行
        self.logTextEdit.setStyleSheet("""
            TextEdit {
                background-color: #1e1e1e;
                border-radius: 4px;
                border: 1px solid #E1E1E1;
                padding: 8px;
                color: #d4d4d4;
                font-family: Consolas, Courier, monospace;
                font-size: 12pt;
            }
        """)

        # 设置最小高度（屏幕高度的70%）
        if parent and hasattr(parent, 'window_height'):
            min_height = int(0.7 * parent.window_height)
        else:
            try:
                min_height = int(0.7 * self.screen().availableGeometry().height())
            except:
                min_height = 500  # 默认高度

        self.logTextEdit.setMinimumHeight(min_height)
        self.logTextEdit.setMinimumWidth(900)

        # 设置日志内容（带颜色解析）
        self.set_log_content(log_content)

        # 将内容控件添加到布局
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.logTextEdit)

        # 创建按钮
        self.yesButton.hide()
        self.cancelButton.setText('关闭')

        # 延迟滚动到底部（确保内容渲染完成）
        QTimer.singleShot(50, self.scroll_to_bottom)

    def set_log_content(self, log_content):
        """设置带颜色的日志内容"""
        # 转义HTML特殊字符
        safe_content = html.escape(log_content)

        # 按行处理日志
        lines = safe_content.split('\n')
        colored_lines = []

        for line in lines:
            # 替换空格为&nbsp;保持缩进
            line = line.replace(' ', '&nbsp;')

            # 检查日志级别
            colored = False
            for level, color in self.LEVEL_COLORS.items():
                # 使用正则确保匹配完整的单词（避免部分匹配）
                if re.search(rf'\b{level}\b', line, re.IGNORECASE):
                    colored_lines.append(f'<span style="color:{color};">{line}</span>')
                    colored = True
                    break

            if not colored:
                colored_lines.append(line)

        # 组合成完整HTML
        html_content = '<pre style="line-height: 1.4;">' + '<br>'.join(colored_lines) + '</pre>'
        self.logTextEdit.setHtml(html_content)

    def scroll_to_bottom(self):
        """滚动到日志最底部"""
        cursor = self.logTextEdit.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.logTextEdit.setTextCursor(cursor)
        self.logTextEdit.ensureCursorVisible()