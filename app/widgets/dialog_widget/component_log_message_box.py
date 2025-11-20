import re
from PyQt5.QtCore import QTimer, QMutex, QMutexLocker, Qt
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

    def __init__(self, log_content="", parent=None, max_chars_per_line=120, max_display_lines=1000):
        super().__init__(parent)

        self.dedupe_cache = []
        self.dedupe_cache_size = 50
        self.max_chars_per_line = max_chars_per_line
        self.max_display_lines = max_display_lines  # 限制显示的最大行数

        # 用于延迟加载的标志
        self._initial_content = log_content
        self._content_loaded = False
        self._closed = False  # 标记窗口是否已关闭

        self.titleLabel = SubtitleLabel('模型日志', self)
        self._isDraggable = True
        self.setSizeGripEnabled(True)

        self.logTextEdit = TextEdit(self)
        self.logTextEdit.setReadOnly(True)
        self.logTextEdit.setLineWrapMode(TextEdit.WidgetWidth)  # 启用自动换行
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

        # 设置最小高度
        if parent and hasattr(parent, 'window_height'):
            min_height = int(0.6 * parent.window_height)
        else:
            try:
                min_height = int(0.6 * self.screen().availableGeometry().height())
            except:
                min_height = 500

        self.logTextEdit.setMinimumHeight(min_height)
        self.logTextEdit.setMinimumWidth(1100)

        self.text_document = self.logTextEdit.document()

        # 添加内容占位符
        self.logTextEdit.setPlainText("正在加载日志内容...")

        # 将内容控件添加到布局
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.logTextEdit)

        # 创建按钮
        self.yesButton.hide()
        self.cancelButton.setText('关闭')

        # 延迟加载日志内容，避免阻塞UI
        QTimer.singleShot(10, self._load_initial_content)

        # 实时更新相关
        self.log_queue = []
        self.log_queue_mutex = QMutex()
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.process_log_queue)
        self.update_timer.start(100)

        self._last_cursor_position = 0

    def _load_initial_content(self):
        """异步加载初始日志内容"""
        if self._initial_content and not self._content_loaded and not self._closed:
            # 限制初始内容的行数
            lines = self._initial_content.split('\n')
            if len(lines) > self.max_display_lines:
                # 只显示最新的行
                lines = lines[-self.max_display_lines:]
                # 添加提示信息
                lines = [f"... (省略了 {len(self._initial_content.split(chr(10))) - len(lines)} 行日志)"] + lines

            # 先设置纯文本
            self.logTextEdit.setPlainText('\n'.join(lines))

            # 然后应用格式化（只处理当前显示的内容）
            self._apply_formatting_to_current_content()

            self._content_loaded = True
            self.scroll_to_bottom()

    def _apply_formatting_to_current_content(self):
        """为当前文档内容应用格式化（只处理当前显示的内容）"""
        if self._closed:
            return

        # 获取文档内容
        content = self.text_document.toPlainText()
        lines = content.split('\n')

        # 重新构建带格式的内容
        cursor = QTextCursor(self.text_document)
        cursor.select(QTextCursor.Document)
        cursor.removeSelectedText()

        # 批量处理，减少格式化操作次数
        for line in lines:
            format_found = False
            for level, color_hex in self.LEVEL_COLORS.items():
                if re.search(rf'\b{level}\b', line, re.IGNORECASE):
                    char_format = QTextCharFormat()
                    char_format.setForeground(QColor(color_hex))
                    cursor.setCharFormat(char_format)
                    format_found = True
                    break

            if not format_found:
                cursor.setCharFormat(QTextCharFormat())

            cursor.insertText(line)
            cursor.insertBlock()

    def set_log_content(self, log_content):
        """设置初始日志内容（异步处理）"""
        if self._closed:
            return

        self._initial_content = log_content
        self._content_loaded = False
        self.logTextEdit.setPlainText("正在加载日志内容...")
        QTimer.singleShot(10, self._load_initial_content)

    def add_log_entry(self, log_line):
        """线程安全地添加单条日志到队列"""
        if self._closed:
            return  # 如果窗口已关闭，不再添加日志

        if not log_line.endswith('\n'):
            log_line += '\n'
        with QMutexLocker(self.log_queue_mutex):
            self.log_queue.append(log_line)

    def _deduplicate_and_add(self, line):
        """检查并添加单行日志，避免重复"""
        if self._closed:
            return

        if not line.strip():
            return  # 跳过空行

        # 检查是否超过最大显示行数
        block_count = self.text_document.blockCount()
        if block_count >= self.max_display_lines:
            # 删除最旧的行
            cursor = QTextCursor(self.text_document)
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.NextBlock, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()

        # 应用格式
        format_found = False
        line_for_level_check = line.replace('&nbsp;', ' ')

        for level, color_hex in self.LEVEL_COLORS.items():
            if re.search(rf'\b{level}\b', line_for_level_check, re.IGNORECASE):
                char_format = QTextCharFormat()
                char_format.setForeground(QColor(color_hex))
                self.logTextEdit.setCurrentCharFormat(char_format)
                format_found = True
                break

        if not format_found:
            self.logTextEdit.setCurrentCharFormat(QTextCharFormat())

        self.logTextEdit.append(line.rstrip('\n'))

        # 更新去重缓存
        self.dedupe_cache.append(line.strip())
        if len(self.dedupe_cache) > self.dedupe_cache_size:
            self.dedupe_cache.pop(0)

    def process_log_queue(self):
        """处理日志队列"""
        if self._closed:
            return

        entries_to_process = []
        with QMutexLocker(self.log_queue_mutex):
            if self.log_queue:
                entries_to_process = self.log_queue[:]
                self.log_queue.clear()

        if not entries_to_process:
            return

        combined_log = "".join(entries_to_process)
        lines = combined_log.split('\n')
        for line in lines:
            if line.strip():
                self._deduplicate_and_add(line)

        self.scroll_to_bottom()

    def scroll_to_bottom(self):
        """滚动到底部"""
        if self._closed:
            return

        scrollbar = self.logTextEdit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event):
        """窗口关闭时停止定时器并清理引用"""
        self._closed = True  # 标记窗口已关闭

        # 停止定时器
        if self.update_timer.isActive():
            self.update_timer.stop()

        # 清理队列
        with QMutexLocker(self.log_queue_mutex):
            self.log_queue.clear()

        # 清理缓存
        self.dedupe_cache.clear()

        super().closeEvent(event)

    def done(self, result):
        """处理窗口关闭"""
        self._closed = True

        # 停止定时器
        if self.update_timer.isActive():
            self.update_timer.stop()

        # 清理队列
        with QMutexLocker(self.log_queue_mutex):
            self.log_queue.clear()

        # 清理缓存
        self.dedupe_cache.clear()

        super().done(result)