import re

from PyQt5.QtCore import QTimer, QMutex, QMutexLocker
from PyQt5.QtGui import QTextCursor, QTextCharFormat, QColor
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

    def __init__(self, log_content="", parent=None):
        super().__init__(parent)
        # --- 新增：去重缓存 ---
        self.dedupe_cache = []
        self.dedupe_cache_size = 50
        # ---
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
            min_height = int(0.6 * parent.window_height)
        else:
            try:
                min_height = int(0.6 * self.screen().availableGeometry().height())
            except:
                min_height = 500  # 默认高度

        self.logTextEdit.setMinimumHeight(min_height)
        self.logTextEdit.setMinimumWidth(1100)

        # --- 初始化 text_document 属性 ---
        self.text_document = self.logTextEdit.document()
        # ---

        # 设置初始日志内容（带颜色解析）
        self.set_log_content(log_content)

        # 将内容控件添加到布局
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.logTextEdit)

        # 创建按钮
        self.yesButton.hide()
        self.cancelButton.setText('关闭')

        # 延迟滚动到底部（确保内容渲染完成）
        QTimer.singleShot(50, self.scroll_to_bottom)

        # --- 实时更新相关 ---
        self.log_queue = []  # 日志队列
        self.log_queue_mutex = QMutex()  # 保护队列的互斥锁
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.process_log_queue)
        self.update_timer.start(100)  # 每100ms检查一次队列

        # --- 用于直接操作文档 ---
        self._last_cursor_position = 0  # 记录上次光标位置，用于优化滚动

    def set_log_content(self, log_content):
        """设置初始日志内容（带颜色解析）"""
        if log_content:
            # 直接操作 QTextDocument，更高效
            # 使用传入的 self.text_document
            cursor = QTextCursor(self.text_document)
            # cursor.movePosition(QTextCursor.End) # 移动到文档末尾 (对于初始内容，应该是开头)
            # 清空现有内容 (可选，因为这是初始化)
            cursor.select(QTextCursor.Document)
            cursor.removeSelectedText()

            lines = log_content.split('\n')
            for line in lines:
                # 为了匹配日志级别，临时将 &nbsp; 替换回空格
                line_for_level_check = line.replace('&nbsp;', ' ')

                format_found = False
                for level, color_hex in self.LEVEL_COLORS.items():
                    if re.search(rf'\b{level}\b', line_for_level_check, re.IGNORECASE):
                        char_format = QTextCharFormat()
                        char_format.setForeground(QColor(color_hex))
                        cursor.setCharFormat(char_format)
                        format_found = True
                        break

                if not format_found:
                    cursor.setCharFormat(QTextCharFormat())

                # 插入原始的、可能包含 &nbsp; 的行
                cursor.insertText(line)
                cursor.insertBlock()  # 插入一个新段落
        else:
            # 如果没有内容，可以清空文档或不操作
            # self.text_document.setPlainText('') # 或者 self.text_document.setHtml('')
            pass
        # --- 新增：将初始内容也加入去重缓存 ---
        # 注意：如果初始内容非常大，可能需要更智能的处理，例如只缓存最后几行
        # 这里简单地将所有初始行加入缓存
        if log_content:
            initial_lines = [line for line in log_content.split('\n') if line.strip()]
            # 保留最新的几行作为缓存
            self.dedupe_cache = initial_lines[-self.dedupe_cache_size:]

    def add_log_entry(self, log_line):
        """线程安全地添加单条日志到队列"""
        # 确保日志行以换行符结尾，以便正确处理
        if not log_line.endswith('\n'):
            log_line += '\n'
        with QMutexLocker(self.log_queue_mutex):
            self.log_queue.append(log_line)

    def _deduplicate_and_add(self, line):
        """检查并添加单行日志，避免重复"""
        # 检查当前行是否已经在缓存中
        if line.strip() in self.dedupe_cache:
            return  # 如果是重复的，直接返回，不添加

        # 如果不是重复的，添加到文档和缓存
        # 为了匹配日志级别，临时将 &nbsp; 替换回空格
        line_for_level_check = line.replace('&nbsp;', ' ')

        format_found = False
        for level, color_hex in self.LEVEL_COLORS.items():
            if re.search(rf'\b{level}\b', line_for_level_check, re.IGNORECASE):
                char_format = QTextCharFormat()
                char_format.setForeground(QColor(color_hex))
                self.logTextEdit.setCurrentCharFormat(char_format)
                format_found = True
                break

        if not format_found:
            # 清除之前的格式
            self.logTextEdit.setCurrentCharFormat(QTextCharFormat())

        # 插入原始的、可能包含 &nbsp; 的行
        self.logTextEdit.append(line.rstrip('\n'))  # append 会自动换行，所以先去掉行尾的 \n

        # 更新缓存
        self.dedupe_cache.append(line.strip())
        # 保持缓存大小
        if len(self.dedupe_cache) > self.dedupe_cache_size:
            self.dedupe_cache.pop(0)  # 移除最旧的条目

    def process_log_queue(self):
        """定时器槽函数，处理日志队列中的内容"""
        # 快速获取队列内容，减少锁持有时间
        entries_to_process = []
        with QMutexLocker(self.log_queue_mutex):
            if self.log_queue:
                entries_to_process = self.log_queue[:]
                self.log_queue.clear()  # 清空队列

        if not entries_to_process:
            return  # 队列为空，无需处理

        # 将队列中的日志合并为一个字符串进行处理
        combined_log = "".join(entries_to_process)

        # 分割行并逐行处理（去重）
        lines = combined_log.split('\n')
        for line in lines:
            # 可能需要过滤掉纯空行，取决于您的具体需求
            self._deduplicate_and_add(line)

        # 滚动到底部
        self.scroll_to_bottom()

    def scroll_to_bottom(self):
        """滚动到日志最底部"""
        # 优化：如果光标已经在底部，则不重复滚动
        cursor = self.logTextEdit.textCursor()
        if cursor.position() >= self._last_cursor_position:
            self.logTextEdit.moveCursor(QTextCursor.End)
            self.logTextEdit.ensureCursorVisible()
        else:
            # 如果用户滚动到了中间，则不自动滚动
            pass
        # 更新记录的位置为当前文档末尾
        temp_cursor = QTextCursor(self.text_document)
        temp_cursor.movePosition(QTextCursor.End)
        self._last_cursor_position = temp_cursor.position()

    def closeEvent(self, event):
        """窗口关闭时停止定时器"""
        self.update_timer.stop()
        super().closeEvent(event)