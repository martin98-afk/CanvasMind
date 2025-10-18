# -*- coding: utf-8 -*-
import os
import sys

import jedi
from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtGui import QFont, QTextCursor, QColor
from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QStyledItemDelegate, QStyle
from spyder.plugins.editor.widgets.codeeditor import CodeEditor

jedi.settings.use_subprocess = False


class CompletionItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor("#2A3B4D"))
            painter.setPen(QColor("#FFFFFF"))
        else:
            painter.fillRect(option.rect, QColor("#19232D"))
            painter.setPen(QColor("#FFFFFF"))
        painter.drawText(option.rect, Qt.AlignLeft | Qt.AlignVCenter, index.data())


class JediCodeEditor(CodeEditor):

    def __init__(self, parent=None, python_exe_path=None, popup_offset=10):
        super().__init__()
        self.popup_offset = popup_offset
        self.parent_widget = parent
        self._jedi_environment = None
        self.custom_completions = set()
        self.completion_usage = {}
        self.max_completions = 80
        self._completing = False
        self.set_jedi_environment(str(python_exe_path))

        # --- 自定义补全弹窗 ---
        self.popup = QListWidget()
        self.popup.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.popup.setFocusPolicy(Qt.NoFocus)
        self.popup.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.popup.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.popup.setStyleSheet("""
            QListWidget {
                background-color: #19232D;
                color: #FFFFFF;
                border: 1px solid #32414B;
                outline: 0;
                padding: 4px;
            }
        """)
        self.popup.setItemDelegate(CompletionItemDelegate())
        self.popup.itemClicked.connect(self._on_completion_selected)
        self.popup.setUniformItemSizes(True)
        self.popup.setMaximumWidth(600)
        self.popup.hide()

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

        # --- 快捷键 ---
        from PyQt5.QtGui import QKeySequence
        from PyQt5.QtWidgets import QShortcut
        self.shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self.shortcut.activated.connect(self._request_completions)

        # 自动补全延迟
        self._auto_complete_timer = QTimer()
        self._auto_complete_timer.setSingleShot(True)
        self._auto_complete_timer.timeout.connect(self._trigger_auto_completion)

        # 注意：不再连接 textChanged！改为在 keyPressEvent 中智能触发
        # self.textChanged.connect(self._on_text_changed)  # 移除！

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
        if python_exe_path:
            python_dir = os.path.dirname(os.path.abspath(python_exe_path))
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
        if isinstance(words, str):
            words = [words]
        self.custom_completions.update(words)

    def keyPressEvent(self, event):
        modifiers = event.modifiers()
        key = event.key()

        if modifiers == Qt.ShiftModifier and key in (Qt.Key_Return, Qt.Key_Enter):
            cursor = self.textCursor()
            if self.parent_widget and hasattr(self.parent_widget, '_handle_shift_enter'):
                self.parent_widget._handle_shift_enter(cursor)
            event.accept()
            return

        if self.popup.isVisible():
            if key == Qt.Key_Escape:
                self.popup.hide()
                return
            elif key in (Qt.Key_Return, Qt.Key_Tab):
                self._apply_selected_completion()
                return
            elif key == Qt.Key_Up:
                current = self.popup.currentRow()
                self.popup.setCurrentRow(max(0, current - 1))
                return
            elif key == Qt.Key_Down:
                current = self.popup.currentRow()
                self.popup.setCurrentRow(min(self.popup.count() - 1, current + 1))
                return

        super().keyPressEvent(event)

        text = event.text()
        should_trigger = False

        # 仅在以下情况触发补全：
        # 1. 输入 '.'
        # 2. 输入字母/数字/下划线，且光标前是标识符（可能继续输入）
        if text == '.':
            should_trigger = True
        elif text.isalnum() or text == '_':
            # 检查是否处于标识符中间（避免在字符串/注释中触发）
            prefix = self._get_completion_prefix()
            if len(prefix) >= 1:  # 至少已有1个字符，说明在继续输入变量名
                should_trigger = True

        if should_trigger:
            self._auto_complete_timer.start(100)  # 延迟稍长，减少误触

    def _trigger_auto_completion(self):
        self._request_completions()

    def _request_completions(self):
        if self._completing:
            return

        cursor = self.textCursor()
        text = self.toPlainText()
        line = cursor.blockNumber() + 1
        column = cursor.columnNumber()

        added = False
        if hasattr(self, '_target_site_packages') and self._target_site_packages:
            if self._target_site_packages not in sys.path:
                sys.path.insert(0, self._target_site_packages)
                added = True

        completions = []
        try:
            script = jedi.Script(code=text, path='<inline>', environment=self._jedi_environment)
            jedi_comps = script.complete(line=line, column=column)
            seen = set()
            for comp in jedi_comps:
                name = comp.name
                if name.startswith('_') or name in seen:
                    continue
                seen.add(name)
                completions.append((name, comp))
                if len(completions) >= self.max_completions * 2:
                    break
        except Exception as e:
            print("[Jedi] Error during completion:", e)
        finally:
            if added:
                try:
                    sys.path.remove(self._target_site_packages)
                except ValueError:
                    pass

        current_prefix = self._get_completion_prefix()
        for word in self.custom_completions:
            if word.lower().startswith(current_prefix.lower()) and word not in seen:
                completions.append((word, None))
                seen.add(word)

        # 关键：如果 Jedi 没返回任何结果，说明当前上下文不可补全（如字符串内）
        if not completions:
            self.popup.hide()
            return

        def sort_key(item):
            name, _ = item
            return (-self.completion_usage.get(name, 0), name.lower())
        completions.sort(key=sort_key)
        completions = completions[:self.max_completions]

        self.popup.clear()
        for name, _ in completions:
            item = QListWidgetItem(name)
            self.popup.addItem(item)

        self._show_popup()
        self.popup.setCurrentRow(0)

    def _show_popup(self):
        # 精准定位：使用 viewport 坐标系
        rect = self.cursorRect()
        point = rect.bottomLeft()
        point.setY(point.y() + self.popup_offset)

        # 转换为全局坐标
        global_point = self.viewport().mapToGlobal(point)

        self.popup.move(global_point)
        item_height = self.popup.sizeHintForRow(0) if self.popup.count() > 0 else 24
        height = min(item_height * min(self.popup.count(), 10) + 10, 400)
        self.popup.setFixedHeight(height)
        self.popup.show()
        self.popup.setFocus()

    def _get_completion_prefix(self):
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

    def _apply_selected_completion(self):
        if not self.popup.currentItem() or self._completing:
            self.popup.hide()
            return

        self._completing = True
        try:
            completion = self.popup.currentItem().text()
            self.completion_usage[completion] = self.completion_usage.get(completion, 0) + 1

            cursor = self.textCursor()
            prefix = self._get_completion_prefix()
            if prefix:
                cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(prefix))
            cursor.insertText(completion)
            self.setTextCursor(cursor)
        finally:
            self._completing = False
            self.popup.hide()

    def _on_completion_selected(self, item):
        self._apply_selected_completion()

    def focusOutEvent(self, event):
        self.popup.hide()
        super().focusOutEvent(event)

    # 移除 _on_text_changed 方法，避免递归和频繁触发