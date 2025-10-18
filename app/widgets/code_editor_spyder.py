# -*- coding: utf-8 -*-
import os
import sys

import jedi
from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtGui import QFont, QTextCursor, QColor, QIcon
from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QStyledItemDelegate, QStyle, QPushButton, QDialog, QVBoxLayout
from qfluentwidgets import TransparentToolButton, MessageBoxBase, TextEdit
from spyder.plugins.editor.widgets.codeeditor import CodeEditor

from app.utils.utils import get_icon

jedi.settings.use_subprocess = False


class CompletionItemDelegate(QStyledItemDelegate):
    """Delegate for custom painting of completion items."""

    def paint(self, painter, option, index):
        """
        Paint the completion item with custom colors.

        Args:
            painter: QPainter object
            option: QStyleOptionViewItem object
            index: QModelIndex object
        """
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor("#2A3B4D"))
            painter.setPen(QColor("#FFFFFF"))
        else:
            painter.fillRect(option.rect, QColor("#19232D"))
            painter.setPen(QColor("#FFFFFF"))
        painter.drawText(option.rect, Qt.AlignLeft | Qt.AlignVCenter, index.data())


class FullscreenCodeDialog(MessageBoxBase):
    """Fullscreen code dialog using FluentUI MessageBoxBase."""

    def __init__(self, initial_code="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("代码编辑器")

        # 创建代码编辑器
        self.code_editor = JediCodeEditor(parent=parent)
        self.code_editor.setPlainText(initial_code)
        self.code_editor.setMinimumSize(800, 600)  # 设置最小尺寸

        # 将编辑器添加到布局中
        self.viewLayout.addWidget(self.code_editor)

        # 设置按钮
        self.yesButton.setText('确定')
        self.cancelButton.hide()

    def get_code(self):
        return self.code_editor.toPlainText()


class JediCodeEditor(CodeEditor):
    """Enhanced CodeEditor with Jedi-powered Python completions."""

    def __init__(self, parent=None, python_exe_path=None, popup_offset=2):
        """
        Initialize the JediCodeEditor.

        Args:
            parent: Parent widget
            python_exe_path: Path to Python executable for Jedi environment
            popup_offset: Offset for completion popup positioning
        """
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
            indent_guides=True,
            folding=True,
            intelligent_backspace=True,
            automatic_completions=True,
            completions_hint=True,
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

        # 智能补全触发延迟
        self._smart_complete_timer = QTimer()
        self._smart_complete_timer.setSingleShot(True)
        self._smart_complete_timer.timeout.connect(self._request_completions)

        # --- 添加放大按钮 ---
        self._create_fullscreen_button()

    def _create_fullscreen_button(self):
        """Create the fullscreen button in the top-right corner."""
        self.fullscreen_button = TransparentToolButton(get_icon("缩放"), parent=self)
        self.fullscreen_button.setFixedSize(28, 28)
        self.fullscreen_button.setToolTip("放大编辑器")
        self.fullscreen_button.clicked.connect(self._open_fullscreen_editor)

        # 初始位置
        self._update_button_position()

    def resizeEvent(self, event):
        """Override resize event to update button position."""
        super().resizeEvent(event)
        self._update_button_position()

    def _update_button_position(self):
        """Update the button position to the top-right corner."""
        button_width = self.fullscreen_button.width()
        button_height = self.fullscreen_button.height()

        # 计算按钮位置（右上角，距离边缘8px）
        x = self.width() - button_width - 30
        y = 6

        self.fullscreen_button.move(x, y)

    def _open_fullscreen_editor(self):
        """Open the code in a fullscreen dialog."""
        current_code = self.toPlainText()

        # 创建对话框
        dialog = FullscreenCodeDialog(initial_code=current_code, parent=self.parent_widget)

        # 显示对话框
        if dialog.exec_() == 1:  # 1 表示点击了确定按钮
            # 更新当前编辑器的内容
            new_code = dialog.get_code()
            self.setPlainText(new_code)

    def wheelEvent(self, event):
        """
        Handle mouse wheel events for zooming font size.

        Args:
            event: QWheelEvent object
        """
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
        """Increase the font size up to a maximum."""
        if self._current_font_size < 30:
            self._current_font_size += 1
            self._apply_font()

    def _decrease_font_size(self):
        """Decrease the font size down to a minimum."""
        if self._current_font_size > 8:
            self._current_font_size -= 1
            self._apply_font()

    def _apply_font(self):
        """Apply the current font settings to the editor."""
        font = QFont(self._font_family, self._current_font_size)
        self.set_font(font)

    def set_jedi_environment(self, python_exe_path):
        """
        Set the Jedi environment for the specified Python executable.

        Args:
            python_exe_path: Path to Python executable
        """
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
        """
        Add custom completion words to the editor.

        Args:
            words: String or list of strings to add as completions
        """
        if isinstance(words, str):
            words = [words]
        self.custom_completions.update(words)

    def keyPressEvent(self, event):
        """
        Handle key press events for custom behaviors.

        Args:
            event: QKeyEvent object
        """
        modifiers = event.modifiers()
        key = event.key()

        # Handle Shift+Enter for parent widget
        if modifiers == Qt.ShiftModifier and key in (Qt.Key_Return, Qt.Key_Enter):
            cursor = self.textCursor()
            if self.parent_widget and hasattr(self.parent_widget, '_handle_shift_enter'):
                self.parent_widget._handle_shift_enter(cursor)
            event.accept()
            return

        # Handle completion popup navigation
        if self.popup.isVisible():
            if key == Qt.Key_Escape:
                self.popup.hide()
                event.accept()
                return
            elif key == Qt.Key_Tab:
                self._apply_selected_completion()
                event.accept()
                return
            elif key == Qt.Key_Up:
                current = self.popup.currentRow()
                self.popup.setCurrentRow(max(0, current - 1))
                event.accept()
                return
            elif key == Qt.Key_Down:
                current = self.popup.currentRow()
                self.popup.setCurrentRow(min(self.popup.count() - 1, current + 1))
                event.accept()
                return

        # Hide popup when typing characters that should close it
        if event.text() in '()[]{}.,;:!? ' and self.popup.isVisible():
            self.popup.hide()

        # Handle Enter/Return for PEP8-compliant indentation in lists/dicts
        if key in (Qt.Key_Return, Qt.Key_Enter):
            cursor = self.textCursor()
            block = cursor.block()
            text = block.text()
            cursor_pos = cursor.positionInBlock()

            # Check if we're inside brackets/parentheses
            line_before_cursor = text[:cursor_pos]
            line_after_cursor = text[cursor_pos:]

            # Count open/close brackets
            open_count = line_before_cursor.count('[') + line_before_cursor.count('(') + line_before_cursor.count('{')
            close_count = line_before_cursor.count(']') + line_before_cursor.count(')') + line_before_cursor.count('}')

            # If we have more opening than closing brackets, add proper indentation
            if open_count > close_count:
                # Get current indentation
                leading_spaces = len(text) - len(text.lstrip())
                new_indent = ' ' * (leading_spaces + 4)

                # Insert newline with proper indentation
                cursor.insertText('\n' + new_indent)

                # If the line after cursor ends with closing brackets, add another newline
                if line_after_cursor.strip().startswith(']') or line_after_cursor.strip().startswith(
                        ')') or line_after_cursor.strip().startswith('}'):
                    cursor.insertText('\n' + ' ' * leading_spaces)
                    # Move cursor back to the indented line
                    cursor.movePosition(QTextCursor.PreviousBlock)
                    cursor.movePosition(QTextCursor.EndOfBlock)
                    self.setTextCursor(cursor)

                event.accept()
                return

        # Process the key press normally
        super().keyPressEvent(event)

        text = event.text()
        should_trigger = False

        # Only trigger completion for specific conditions:
        # 1. Inputting '.'
        # 2. Inputting alphanumeric characters or underscore that continue an identifier
        if text == '.':
            should_trigger = True
        elif text.isalnum() or text == '_':
            # Check if we're continuing an identifier (avoid triggering in strings/comments)
            prefix = self._get_completion_prefix()
            if len(prefix) >= 2:  # At least 3 characters, indicating identifier continuation
                should_trigger = True

        if should_trigger:
            # Use a shorter delay for more responsive completion
            self._smart_complete_timer.start(50)

    def _trigger_auto_completion(self):
        """Trigger the auto-completion process."""
        self._request_completions()

    def _request_completions(self):
        """Request completions from Jedi and display them in the popup."""
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
                # Skip private attributes (starting with underscore) and duplicates
                # Also skip very short names (less than 3 characters)
                if name.startswith('_') or name in seen or len(name) < 2:
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
            if word.lower().startswith(current_prefix.lower()) and word not in seen and len(word) >= 2:
                completions.append((word, None))
                seen.add(word)

        # Key: If Jedi returns no results, it means the context is not completable (e.g., inside strings)
        if not completions:
            self.popup.hide()
            return

        # Sort completions by usage frequency and then alphabetically
        def sort_key(item):
            name, _ = item
            return (-self.completion_usage.get(name, 0), name.lower())

        completions.sort(key=sort_key)
        completions = completions[:self.max_completions]

        # Populate the completion popup
        self.popup.clear()
        for name, _ in completions:
            item = QListWidgetItem(name)
            self.popup.addItem(item)

        if self.popup.count() > 0:
            self._show_popup()
            self.popup.setCurrentRow(0)
        else:
            self.popup.hide()

    def _show_popup(self):
        """Show the completion popup at the correct position."""
        # Precise positioning: use viewport coordinate system
        rect = self.cursorRect()
        point = rect.bottomLeft()
        point.setY(point.y() + self.popup_offset)

        # Convert to global coordinates
        global_point = self.viewport().mapToGlobal(point)

        self.popup.move(global_point)
        item_height = self.popup.sizeHintForRow(0) if self.popup.count() > 0 else 24
        height = min(item_height * min(self.popup.count(), 10) + 10, 400)
        self.popup.setFixedHeight(height)
        self.popup.show()
        self.popup.setFocus()

    def _get_completion_prefix(self):
        """
        Get the prefix for the current completion.

        Returns:
            str: The prefix string before the cursor
        """
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
        """Apply the selected completion to the editor."""
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
        """
        Handle completion selection event.

        Args:
            item: Selected QListWidgetItem
        """
        self._apply_selected_completion()

    def focusOutEvent(self, event):
        """
        Handle focus out event to hide the popup.

        Args:
            event: QFocusEvent object
        """
        self.popup.hide()
        super().focusOutEvent(event)