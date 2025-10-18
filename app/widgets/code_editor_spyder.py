# -*- coding: utf-8 -*-
import json
import os
import subprocess
import sys

import jedi
from PyQt5.QtCore import Qt, QStringListModel, QTimer
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtWidgets import QCompleter
from spyder.plugins.editor.widgets.codeeditor import CodeEditor

jedi.settings.use_subprocess = False  # 禁用子进程模式


class JediCodeEditor(CodeEditor):

    def __init__(self, parent=None, python_exe_path=None, popup_offset=2):
        super().__init__()
        self.popup_offset = popup_offset
        self.parent_widget = parent
        self._jedi_environment = None  # 缓存 Jedi 环境，避免重复创建
        self.custom_completions = set()
        self.set_jedi_environment(str(python_exe_path))
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
            auto_unindent=True,
            close_quotes=True,
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
        self.textChanged.connect(self._on_text_changed)

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
        """不再创建 Jedi Environment，而是记录目标环境的 site-packages 路径"""
        if python_exe_path:
            # 推导 site-packages 路径
            python_dir = os.path.dirname(os.path.abspath(python_exe_path))
            # Windows Conda 环境的 site-packages 通常在 Lib/site-packages
            site_packages = os.path.join(python_dir, "Lib", "site-packages")

            if os.path.isdir(site_packages):
                self._target_site_packages = site_packages
                print(f"[Jedi] Target site-packages: {site_packages}")
            else:
                self._target_site_packages = None
                print(f"[Jedi] Warning: site-packages not found at {site_packages}")
        else:
            self._target_site_packages = None

    def add_custom_completions(self, words):
        """添加自定义补全项（如 API、关键字等）"""
        if isinstance(words, str):
            words = [words]
        self.custom_completions.update(words)

    def keyPressEvent(self, event):
        modifiers = event.modifiers()
        key = event.key()

        # 处理 Shift+Enter
        if modifiers == Qt.ShiftModifier and key in (Qt.Key_Return, Qt.Key_Enter):
            cursor = self.textCursor()
            if self.parent_widget and hasattr(self.parent_widget, '_handle_shift_enter'):
                self.parent_widget._handle_shift_enter(cursor)

        # 补全弹窗逻辑
        if self.completer.popup().isVisible():
            if key in (Qt.Key_Return, Qt.Key_Tab, Qt.Key_Escape):
                self.completer.popup().hide()
                event.ignore()
                return
            elif key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
                super().keyPressEvent(event)
                return

        super().keyPressEvent(event)

        # 自动补全
        if event.text() == '.':
            self.request_completions()
        elif event.text().isalnum() or event.text() == '_':
            self._auto_complete_timer.start(50)

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
        # 临时加入目标环境的包路径
        added = False
        if hasattr(self, '_target_site_packages') and self._target_site_packages:
            if self._target_site_packages not in sys.path:
                sys.path.insert(0, self._target_site_packages)
                added = True
        # === Jedi 补全 ===
        jedi_names = set()
        try:
            if self._jedi_environment is not None:
                script = jedi.Script(code=text, path='<inline>', environment=self._jedi_environment)
            else:
                script = jedi.Script(code=text, path='<inline>')

            jedi_comps = script.complete(line=line, column=column)
            count = 0
            max_completions = 80
            for comp in jedi_comps:
                name = comp.name
                if name.startswith('_') or count >= max_completions:
                    continue
                jedi_names.add(name)
                count += 1
        except Exception as e:
            print("[Jedi] Error during completion:", e)
        finally:
            # 清理：避免污染后续分析
            if added:
                try:
                    sys.path.remove(self._target_site_packages)
                except ValueError:
                    pass  # 可能已被其他操作移除

        # === 自定义补全：使用正确的前缀 ===
        current_prefix = self.get_completion_prefix()
        custom_filtered = set()
        if current_prefix:
            custom_filtered = {w for w in self.custom_completions if w.lower().startswith(current_prefix.lower())}

        all_completions = jedi_names | custom_filtered
        completion_list = sorted(all_completions, key=lambda x: x.lower())

        # === 关键：只要 Jedi 或自定义有结果，就显示！不要因为 prefix 为空而隐藏 ===
        if not completion_list:
            self.completer.popup().hide()
            return

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

        item_count = min(len(self.completer_model.stringList()), 10)
        item_height = popup.sizeHintForRow(0)
        if item_height <= 0:
            item_height = 24
        popup.setFixedHeight(item_count * item_height + 10)

        popup.show()

        # 关键：设置当前前缀用于过滤
        prefix = self.get_completion_prefix()
        self.completer.setCompletionPrefix(prefix)

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
        cursor = self.textCursor()
        prefix = self.get_completion_prefix()
        if prefix:
            # 删除前缀
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(prefix))
        cursor.insertText(completion)
        self.setTextCursor(cursor)
        self.completer.popup().hide()

    def focusOutEvent(self, event):
        self.completer.popup().hide()
        super().focusOutEvent(event)

    def _on_text_changed(self):
        if not self.completer.popup().isVisible():
            return

        current_prefix = self.get_completion_prefix()
        original_prefix = self.completer.completionPrefix()

        if not current_prefix.lower().startswith(original_prefix.lower()):
            self.completer.popup().hide()

    def get_completion_prefix(self):
        """获取光标前的连续标识符字符（仅字母、数字、下划线）"""
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()

        start = pos
        while start > 0:
            ch = text[start - 1]
            if ch.isalnum() or ch == '_':
                start -= 1
            else:
                break
        return text[start:pos]
