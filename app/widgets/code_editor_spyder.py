# -*- coding: utf-8 -*-
import jedi
from PyQt5.QtCore import Qt, QStringListModel, QTimer
from PyQt5.QtGui import QFont, QTextCursor, QColor, QTextFormat
from PyQt5.QtWidgets import QCompleter, QTextEdit
from spyder.plugins.editor.widgets.codeeditor import CodeEditor


class JediCodeEditor(CodeEditor):
    def __init__(self, parent=None, python_exe_path=None, popup_offset=2):
        super().__init__()
        self.popup_offset = popup_offset
        self.parent_widget = parent
        self._jedi_environment = None  # 缓存 Jedi 环境，避免重复创建
        self.custom_completions = set()
        self.set_jedi_environment(python_exe_path)
        # --- 初始化 QCompleter ---
        self.completer_model = QStringListModel()
        self.completer = QCompleter(self.completer_model, self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchStartsWith)  # 改为前缀匹配，提升性能
        self.completer.setWidget(self)
        self.completer.activated.connect(self.insert_completion)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)

        # 配置弹窗样式
        popup = self.completer.popup()
        popup.setUniformItemSizes(True)
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
        self._font_family = 'Consolas'
        self._current_font_size = 13
        font = QFont('Consolas', 13)
        self.setup_editor(
            language='python',
            color_scheme='spyder/dark',
            font=font,
            show_blanks=False,
            edge_line=True,
            tab_mode=True,
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

    def wheelEvent(self, event):
        if event.modifiers() == Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self._increase_font_size()
            else:
                self._decrease_font_size()
            event.accept()
        else:
            super().wheelEvent(event)

    def _increase_font_size(self):
        if self._current_font_size < 30:
            self._current_font_size += 1
            self._apply_font()

    def _decrease_font_size(self):
        if self._current_font_size > 8:
            self._current_font_size -= 1
            self._apply_font()

    def _apply_font(self):
        font = QFont(self._font_family, self._current_font_size)
        self.set_font(font)

    def set_jedi_environment(self, python_exe_path):
        # --- 预加载 Jedi Environment（关键性能优化）---
        if python_exe_path:
            try:
                from jedi.api.environment import create_environment
                self._jedi_environment = create_environment(python_exe_path, safe=False)
                print(f"[Jedi] Loaded environment from: {python_exe_path}")
            except Exception as e:
                print(f"[Jedi] Failed to create environment: {e}")
                self._jedi_environment = None

    def add_custom_completions(self, words):
        """添加自定义补全项（如 API、关键字等）"""
        if isinstance(words, str):
            words = [words]
        self.custom_completions.update(words)

    def keyPressEvent(self, event):
        modifiers = event.modifiers()
        if modifiers == Qt.ShiftModifier and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            cursor = self.textCursor()
            if self.parent_widget and hasattr(self.parent_widget, '_handle_shift_enter'):
                self.parent_widget._handle_shift_enter(cursor)
            return

        if self.completer.popup().isVisible():
            if event.key() in (Qt.Key_Enter, Qt.Key_Return, Qt.Key_Tab, Qt.Key_Escape):
                self.completer.popup().hide()
                event.ignore()
                return
            elif event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
                super().keyPressEvent(event)
                return

        super().keyPressEvent(event)

        # 自动触发补全逻辑
        if event.text() == '.':
            self.request_completions()
        elif event.text().isalnum() or event.text() == '_':
            self._auto_complete_timer.start(50)  # 延迟 250ms

    def _trigger_auto_completion(self):
        """延迟触发自动补全"""
        prefix = self.get_word_under_cursor()
        if len(prefix) >= 2:  # 至少 2 个字符才触发
            self.request_completions()

    def request_completions(self):
        cursor = self.textCursor()
        text = self.toPlainText()
        line = cursor.blockNumber() + 1
        column = cursor.columnNumber()

        # === 新增：快速路径判断 ===
        prefix = self.get_word_under_cursor()

        # === Jedi 补全 ===
        jedi_names = set()
        try:
            if self._jedi_environment is not None:
                script = jedi.Script(code=text, path='<inline>', environment=self._jedi_environment)
            else:
                script = jedi.Script(code=text, path='<inline>')

            jedi_comps = script.complete(line=line, column=column)
            count = 0
            max_completions = 80  # 略微降低，减少处理量
            for comp in jedi_comps:
                name = comp.name
                if name.startswith('_') or count >= max_completions:
                    continue
                jedi_names.add(name)
                count += 1
        except Exception as e:
            print("[Jedi] Error during completion:", e)

        # === 自定义补全 ===
        custom_filtered = set()
        if prefix:
            custom_filtered = {w for w in self.custom_completions if w.lower().startswith(prefix.lower())}

        all_completions = jedi_names | custom_filtered

        # === 关键优化：避免无意义弹窗 ===
        completion_list = sorted(all_completions, key=lambda x: x.lower())

        # 情况1：没有补全项 → 隐藏
        if not completion_list:
            self.completer.popup().hide()
            return

        # 情况2：只有一个补全项，且它等于当前前缀 → 无意义，隐藏
        if len(completion_list) == 1 and completion_list[0] == prefix:
            self.completer.popup().hide()
            return

        # 情况3：有多个，或唯一项 ≠ prefix → 显示
        self.completer_model.setStringList(completion_list)
        self.show_completer()

    def show_completer(self):
        rect = self.cursorRect()
        content_offset = self.contentOffset()
        widget_pos = rect.bottomLeft() - content_offset
        widget_point = widget_pos.toPoint()
        widget_point.setY(widget_point.y() + self.popup_offset)
        global_point = self.mapToGlobal(widget_point)

        popup = self.completer.popup()
        popup.move(global_point)
        popup.setMaximumWidth(600)

        # 动态调整高度（最多显示 10 项）
        item_count = min(len(self.completer_model.stringList()), 10)
        item_height = popup.sizeHintForRow(0)
        if item_height <= 0:
            item_height = 24
        popup.setFixedHeight(item_count * item_height + 10)

        popup.show()

        prefix = self.get_word_under_cursor()
        self.completer.setCompletionPrefix(prefix)

        # 默认选中第一项
        if self.completer_model.rowCount() > 0:
            idx = self.completer_model.index(0, 0)
            popup.setCurrentIndex(idx)

    def get_word_under_cursor(self):
        """获取光标左侧的单词（用于补全前缀）"""
        cursor = self.textCursor()
        cursor.select(QTextCursor.WordUnderCursor)
        word = cursor.selectedText()
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