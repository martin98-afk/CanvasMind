# -*- coding: utf-8 -*-
import jedi
from PyQt5.QtCore import Qt, QStringListModel, QTimer
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtWidgets import (
    QCompleter
)
from spyder.plugins.editor.widgets.codeeditor import CodeEditor


class JediCodeEditor(CodeEditor):
    def __init__(self, parent=None):
        super().__init__()
        self.parent_widget = parent
        # --- 自定义补全源（可扩展）---
        self.custom_completions = set()

        # --- 初始化 QCompleter ---
        self.completer_model = QStringListModel()
        self.completer = QCompleter(self.completer_model, self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)  # 支持包含匹配（模糊搜索）
        self.completer.setWidget(self)
        self.completer.activated.connect(self.insert_completion)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)

        # 配置弹窗样式和行为
        popup = self.completer.popup()
        popup.setUniformItemSizes(True)  # 优化滚动性能 + 高度一致
        popup.setStyleSheet("""
            QListView {
                background-color: #19232D;
                color: #FFFFFF;
                border: 1px solid #32414B;
                outline: 0;
                padding: 4px;
                
            }
            QListView::item {
                padding: 6px 12px;
                border-radius: 2px;
            }
            QListView::item:selected {
                background-color: #2A3B4D;
                color: #FFFFFF;
            }
        """)

        # --- 设置编辑器 ---
        font = QFont('Consolas', 13)
        self.setup_editor(
            language='python',
            color_scheme='spyder/dark',
            font=font,
            show_blanks=False,
            edge_line=True,
            tab_mode=False,
            intelligent_backspace=True,
            automatic_completions=False,
            completions_hint=False,
            highlight_current_line=True,
        )

        # --- 快捷键：手动触发补全 ---
        from PyQt5.QtGui import QKeySequence
        from PyQt5.QtWidgets import QShortcut
        self.shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self.shortcut.activated.connect(self.request_completions)

        # 自动补全延迟（避免频繁触发）
        self._auto_complete_timer = QTimer()
        self._auto_complete_timer.setSingleShot(True)
        self._auto_complete_timer.timeout.connect(self._trigger_auto_completion)

    def add_custom_completions(self, words):
        """添加自定义补全项（如 API、关键字等）"""
        if isinstance(words, str):
            words = [words]
        self.custom_completions.update(words)

    def keyPressEvent(self, event):
        # 如果补全弹窗打开，处理特殊按键
        modifiers = event.modifiers()
        if modifiers == Qt.ShiftModifier and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            cursor = self.textCursor()
            self.parent_widget._handle_shift_enter(cursor)
            return
        if self.completer.popup().isVisible():
            if event.key() in (Qt.Key_Enter, Qt.Key_Return, Qt.Key_Tab):
                self.completer.popup().hide()
                event.ignore()
                return
            elif event.key() == Qt.Key_Escape:
                self.completer.popup().hide()
                event.ignore()
                return
            elif event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
                # 交给 QCompleter 处理导航
                super().keyPressEvent(event)
                return

        super().keyPressEvent(event)

        # 自动触发补全逻辑
        if event.text() == '.':
            self.request_completions()
        elif event.text().isalnum() or event.text() == '_':
            # 延迟触发，避免每按一次都请求
            self._auto_complete_timer.start(150)

    def _trigger_auto_completion(self):
        """延迟触发自动补全（避免频繁调用）"""
        prefix = self.get_word_under_cursor()
        if len(prefix) >= 1:  # 至少1个字符才触发
            self.request_completions()

    def request_completions(self):
        """请求 Jedi + 自定义 补全列表"""
        cursor = self.textCursor()
        text = self.toPlainText()
        line = cursor.blockNumber() + 1
        column = cursor.columnNumber()

        all_completions = set()

        # --- Jedi 补全 ---
        try:
            script = jedi.Script(text, path='<inline>')
            jedi_comps = script.complete(line=line, column=column)
            all_completions.update(c.name for c in jedi_comps if not c.name.startswith('_'))
        except Exception as e:
            print("Jedi error:", e)

        # --- 自定义补全 ---
        prefix = self.get_word_under_cursor()
        if prefix:
            custom_filtered = {w for w in self.custom_completions if prefix.lower() in w.lower()}
            all_completions.update(custom_filtered)

        completion_list = sorted(all_completions, key=lambda x: x.lower())

        if completion_list:
            self.completer_model.setStringList(completion_list)
            self.show_completer()
        else:
            self.completer.popup().hide()

    def show_completer(self):
        rect = self.cursorRect()
        content_offset = self.contentOffset()
        widget_pos = rect.bottomLeft() - content_offset
        widget_point = widget_pos.toPoint()
        widget_point.setY(widget_point.y() + 2)  # 微调，避免遮挡光标
        global_point = self.mapToGlobal(widget_point)

        popup = self.completer.popup()
        popup.move(global_point)
        popup.setMaximumWidth(600)

        # 动态调整高度（最多显示10项）
        item_count = min(len(self.completer_model.stringList()), 10)
        item_height = popup.sizeHintForRow(0)
        if item_height <= 0:
            item_height = 24  # fallback
        popup.setFixedHeight(item_count * item_height + 10)  # + padding

        popup.show()

        prefix = self.get_word_under_cursor()
        self.completer.setCompletionPrefix(prefix)

        # ✅ 默认选中第一项
        popup.setCurrentIndex(self.completer_model.index(0, 0))
        self.completer.popup().setCurrentIndex(self.completer_model.index(0, 0))

    def get_word_under_cursor(self):
        """获取光标左侧的单词（用于补全前缀）"""
        cursor = self.textCursor()
        cursor.select(QTextCursor.WordUnderCursor)
        word = cursor.selectedText()
        # 如果光标在单词中间，也应返回从单词开头到光标的部分
        if not word:
            cursor.movePosition(QTextCursor.StartOfWord, QTextCursor.KeepAnchor)
            word = cursor.selectedText()
        return word

    def insert_completion(self, completion):
        """插入补全项"""
        cursor = self.textCursor()
        word = self.get_word_under_cursor()
        if word:
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(word))
        cursor.insertText(completion)
        self.setTextCursor(cursor)
        self.completer.popup().hide()

    def focusOutEvent(self, event):
        self.completer.popup().hide()
        super().focusOutEvent(event)