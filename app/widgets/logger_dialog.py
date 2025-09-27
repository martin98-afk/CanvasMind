from collections import deque
from PyQt5.QtGui import QTextCharFormat, QColor, QTextCursor
from PyQt5.QtCore import QObject, pyqtSignal, Qt
import logging


class QTextEditLogger(QObject):
    """线程安全的日志记录器，专为Qt应用设计（无空白行版）"""

    log_signal = pyqtSignal(str, str)  # (level, message)

    def __init__(self, text_edit, max_lines=1000):
        super().__init__()
        self.text_edit = text_edit
        self.buffer = deque(maxlen=max_lines)
        self.is_scrolling = True  # 跟踪用户是否手动滚动

        # 级别对应颜色
        self.colors = {
            "DEBUG": QColor("#00BFFF"),
            "INFO": QColor("#00FF7F"),
            "WARNING": QColor("#FFD700"),
            "ERROR": QColor("#FF4500"),
            "CRITICAL": QColor("#FF1493"),
        }

        # 连接信号到安全处理槽
        self.log_signal.connect(self._safe_append_line, Qt.QueuedConnection)

        # 连接滚动条信号
        self.text_edit.verticalScrollBar().valueChanged.connect(self._on_scroll_value_changed)

    def write(self, message):
        """安全写入日志（可被任何线程调用）"""
        text = message.strip()
        if not text:
            return

        # 提取日志级别
        level = "INFO"
        for lvl in self.colors:
            if f"| {lvl} |" in text:
                level = lvl
                break

        # 缓存到内存
        self.buffer.append((level, text))

        # 通过信号安全传递到主线程
        self.log_signal.emit(level, text)

    def _on_scroll_value_changed(self, value):
        """当用户滚动时更新状态"""
        max_value = self.text_edit.verticalScrollBar().maximum()
        self.is_scrolling = (value >= max_value - 2)

    def _safe_text_cursor(self) -> QTextCursor:
        """安全获取文本游标"""
        if not self._is_widget_valid():
            return None
        try:
            return self.text_edit.textCursor()
        except RuntimeError:
            return None

    def _safe_append_line(self, level: str, line: str):
        """主线程执行的日志追加（正确处理换行和空白）"""
        # 1. 检查UI对象是否有效
        if not self._is_widget_valid():
            return

        # 2. 检查日志级别有效性
        color = self.colors.get(level, QColor("#FFFFFF"))

        # 3. 创建格式化对象
        fmt = QTextCharFormat()
        fmt.setForeground(color)

        # 4. 安全获取文档
        doc = self.text_edit.document()
        if not doc:
            return

        # 5. 直接操作文档
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.End)

        # 关键修复：总是添加换行符（确保每条日志独占一行）
        # 注意：QPlainTextEdit需要显式换行符才能分行显示
        cursor.insertText(line + "\n", fmt)

        # 6. 清理底部空白（关键：在滚动前清理）
        self._clean_trailing_empty_lines()

        # 7. 滚动到底部（使用更可靠的方法）
        self._safe_scroll_to_bottom()

    def _clean_trailing_empty_lines(self):
        """清理文档末尾的额外空白行（只清理QPlainTextEdit自动添加的）"""
        if not self._is_widget_valid():
            return

        doc = self.text_edit.document()
        if not doc or doc.blockCount() <= 1:
            return

        # 保存当前滚动位置
        scroll_pos = self.text_edit.verticalScrollBar().value()
        max_scroll = self.text_edit.verticalScrollBar().maximum()

        # 如果当前在底部附近，标记为自动滚动
        at_bottom = (scroll_pos >= max_scroll - 2)

        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.End)

        # 检查最后一行是否为空（由QPlainTextEdit自动添加的）
        last_block = doc.lastBlock()
        if last_block.text().endswith("\n\n"):
            # 移除空行
            cursor.setPosition(last_block.position())
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            cursor.deleteChar()  # 删除段落结束符

        # 恢复滚动位置（如果之前在底部）
        if at_bottom:
            self.text_edit.verticalScrollBar().setValue(
                self.text_edit.verticalScrollBar().maximum()
            )

    def _safe_scroll_to_bottom(self):
        """安全滚动到底部（确保保留正常换行）"""
        if not self._is_widget_valid() or not self.is_scrolling:
            return

        try:
            # 方法1：直接滚动到文档末尾（最可靠）
            self.text_edit.verticalScrollBar().setValue(
                self.text_edit.verticalScrollBar().maximum()
            )
        except RuntimeError:
            pass

    def scroll_to_bottom(self, force=False):
        """
        滚动到底部（公共方法）
        :param force: 是否强制滚动（忽略 is_scrolling 状态）
        """
        if not self._is_widget_valid():
            return

        try:
            scroll_bar = self.text_edit.verticalScrollBar()
            if scroll_bar:
                if force:
                    # 强制滚动到底部
                    scroll_bar.setValue(scroll_bar.maximum())
                else:
                    # 只有在自动滚动模式下才滚动
                    if self.is_scrolling:
                        scroll_bar.setValue(scroll_bar.maximum())
        except RuntimeError:
            pass

    def _is_widget_valid(self) -> bool:
        """检查文本编辑控件是否有效"""
        if not hasattr(self, 'text_edit') or self.text_edit is None:
            return False
        try:
            self.text_edit.isVisible()
            return True
        except RuntimeError:
            return False

    def flush(self):
        """标准流接口"""
        pass

    def close(self):
        """安全关闭（清理资源）"""
        try:
            self.log_signal.disconnect()
            self.text_edit.verticalScrollBar().valueChanged.disconnect(self._on_scroll_value_changed)
        except:
            pass
        self.text_edit = None
        self.buffer.clear()