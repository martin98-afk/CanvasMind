# -*- coding: utf-8 -*-
import os
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, Future
from typing import List, Tuple, Optional

import jedi
from PyQt5.QtCore import Qt, QTimer, QSize, pyqtSignal, QObject, QRect
from PyQt5.QtGui import QFont, QTextCursor, QColor, QPainter
from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QStyledItemDelegate, QStyle
from qfluentwidgets import TransparentToolButton, MessageBoxBase
from spyder.plugins.editor.widgets.codeeditor import CodeEditor

from app.utils.utils import get_icon

# 禁用jedi子进程，避免在GUI应用中出现子进程问题
jedi.settings.use_subprocess = False
# 限制jedi缓存大小，防止内存占用过高
jedi.settings.cache_directory = os.path.expanduser("~/.jedi_cache")
jedi.settings.call_signatures_validity = 300  # 缓存5分钟

# 线程池用于异步处理补全请求
completion_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="JediCompletion")


class CompletionItemDelegate(QStyledItemDelegate):
    """自定义补全项绘制器，解决重叠、颜色和间距问题"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # 定义类型颜色，模仿PyCharm风格
        self.type_colors = {
            'function': QColor("#FFB86C"),  # 橙色
            'method': QColor("#FFB86C"),  # 橙色
            'class': QColor("#82AAFF"),  # 蓝色
            'module': QColor("#B267E6"),  # 紫色
            'instance': QColor("#F07178"),  # 红色
            'keyword': QColor("#C792EA"),  # 紫色
            'property': QColor("#FFCB6B"),  # 黄色
            'param': QColor("#F78C6C"),  # 橙红色
            'variable': QColor("#E0E0E0"),  # 灰白色
            'custom': QColor("#89DDFF"),  # 青色
            'unknown': QColor("#CCCCCC"),  # 浅灰色
        }

        # 定义类型字符（单个字母，简洁明了）
        self.type_chars = {
            'function': 'F',
            'method': 'M',
            'class': 'C',
            'module': 'M',
            'instance': 'I',
            'keyword': 'K',
            'property': 'P',
            'param': 'P',
            'variable': 'V',
            'custom': '★',  # 自定义补全使用星号
        }

    def paint(self, painter: QPainter, option, index):
        """
        绘制补全项，确保只绘制一次，使用不同颜色区分类型
        """
        # 1. 绘制背景
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor("#2A3B4D"))
            painter.setPen(QColor("#FFFFFF"))
        else:
            painter.fillRect(option.rect, QColor("#19232D"))
            painter.setPen(QColor("#FFFFFF"))

        # 2. 获取数据 (使用 UserRole 存储的完整信息)
        item_data = index.data(Qt.UserRole)
        if item_data:
            name, type_name, description = item_data
        else:
            # 兼容旧数据格式
            name = index.data(Qt.DisplayRole) or index.data()
            type_name = ""
            description = ""

        # 3. 计算区域
        padding = 6
        char_width = 20  # 增大字符宽度
        char_spacing = 6  # 字符和文字之间的间距
        rect = option.rect.adjusted(padding, 0, -padding, 0)

        # 类型字符区域
        char_rect = QRect(rect.left(), rect.top(), char_width, rect.height())
        # 名称区域（从字符右边开始）
        name_start_x = rect.left() + char_width + char_spacing
        name_rect = QRect(
            name_start_x,
            rect.top(),
            rect.width() - char_width - char_spacing - 10,  # 减去右边内边距
            rect.height()
        )

        # 4. 绘制类型字符（单个字母，使用类型颜色）
        type_char = self.type_chars.get(type_name, '?')
        type_color = self.type_colors.get(type_name, self.type_colors['unknown'])
        painter.setPen(type_color)
        char_font = painter.font()
        char_font.setPointSize(char_font.pointSize() + 2)  # 比主文字大2号
        char_font.setBold(True)  # 加粗显示
        painter.setFont(char_font)
        painter.drawText(
            char_rect,
            Qt.AlignCenter,  # 居中显示
            type_char
        )
        # 恢复原字体
        painter.setFont(option.font)

        # 5. 绘制主名称（白色）
        painter.setPen(QColor("#FFFFFF"))  # 使用白色绘制名称
        name_font = painter.font()
        name_font.setPointSize(name_font.pointSize() + 1)  # 稍大一点
        painter.setFont(name_font)

        # 如果有描述，和名称放在同一行，名称左对齐，描述右对齐
        if description and name_rect.width() > 150:
            # 计算描述区域（右侧）
            desc_font = painter.font()
            desc_font.setPointSize(desc_font.pointSize() - 1)
            desc_font.setItalic(True)
            painter.setFont(desc_font)
            painter.setPen(QColor("#AAAAAA"))

            # 描述文本宽度
            fm = painter.fontMetrics()
            desc_width = fm.width(description)
            # 描述区域矩形
            desc_rect = QRect(
                name_rect.right() - desc_width - 5,  # 右侧留5px间距
                name_rect.top(),
                desc_width,
                name_rect.height()
            )

            # 绘制描述
            painter.drawText(
                desc_rect,
                Qt.AlignRight | Qt.AlignVCenter,
                description
            )

            # 绘制名称（左侧，不覆盖描述）
            name_only_rect = QRect(
                name_rect.left(),
                name_rect.top(),
                name_rect.width() - desc_width - 10,  # 留出空间给描述和间距
                name_rect.height()
            )
            painter.setFont(name_font)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(
                name_only_rect,
                Qt.AlignLeft | Qt.AlignVCenter,
                name
            )

            # 恢复原字体
            painter.setFont(option.font)
        else:
            # 没有描述，直接绘制名称
            painter.drawText(
                name_rect,
                Qt.AlignLeft | Qt.AlignVCenter,
                name
            )
            # 恢复原字体
            painter.setFont(option.font)

    def sizeHint(self, option, index):
        """返回补全项的推荐尺寸"""
        size = super().sizeHint(option, index)
        return QSize(size.width(), 40)  # 增加高度到40px，更舒适


class CompletionWorker(QObject):
    """异步补全工作线程"""
    completion_ready = pyqtSignal(list)  # 发送补全结果
    error_occurred = pyqtSignal(str)  # 发送错误信息

    def __init__(self):
        super().__init__()
        self.running = True

    def request_completions(self, code: str, line: int, column: int,
                            environment: Optional[jedi.api.environment.Environment] = None):
        """请求补全"""
        if not self.running:
            return

        try:
            start_time = time.time()
            script = jedi.Script(code=code, path='<inline>', environment=environment)
            jedi_comps = script.complete(line=line, column=column)

            completions = []
            seen = set()
            for comp in jedi_comps:
                name = comp.name
                if name.startswith('_') or name in seen:
                    continue
                seen.add(name)

                # 提取类型和描述
                type_name = getattr(comp, 'type', 'unknown')
                description = getattr(comp, 'description', '')

                completions.append((name, type_name, description))

                if len(completions) >= 100:
                    break

            elapsed = time.time() - start_time
            print(f"[Jedi] Completion took {elapsed:.3f}s for {len(completions)} items")

            self.completion_ready.emit(completions)
        except Exception as e:
            self.error_occurred.emit(str(e))


class JediCodeEditor(CodeEditor):
    """增强的代码编辑器，支持Jedi补全"""

    def __init__(self, parent=None, code_parent=None, python_exe_path=None, popup_offset=2, dialog=None):
        super().__init__()
        self.popup_offset = popup_offset
        self.parent_widget = parent
        self.parent = code_parent
        self._jedi_environment = None
        self.custom_completions = set()
        self.completion_usage = OrderedDict()
        self.max_completions = 80
        self._completing = False
        self.dialog = dialog
        self.set_jedi_environment(str(python_exe_path) if python_exe_path else None)

        # --- 高性能补全相关 ---
        self.completion_worker = CompletionWorker()
        self.completion_future: Optional[Future] = None
        self.pending_completion_request = None
        self._input_delay_timer = QTimer()
        self._input_delay_timer.setSingleShot(True)
        self._input_delay_timer.timeout.connect(self._on_input_delay_timeout)
        self._input_delay_ms = 10

        # --- 补全弹窗 ---
        self.popup = QListWidget()
        self.popup.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.popup.setFocusPolicy(Qt.NoFocus)
        self.popup.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.popup.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        popup_font = QFont('Consolas', 12)  # 增大字体
        self.popup.setFont(popup_font)
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
        self.popup.setMaximumWidth(1200)  # 大幅增加最大宽度
        self.popup.setMinimumWidth(500)  # 增加最小宽度
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
            automatic_completions=False,
            completions_hint=True,
            highlight_current_line=True,
        )

        # --- 快捷键 ---
        from PyQt5.QtGui import QKeySequence
        from PyQt5.QtWidgets import QShortcut
        self.shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self.shortcut.activated.connect(self._request_completions)

        # --- 定时器 ---
        self._auto_complete_timer = QTimer()
        self._auto_complete_timer.setSingleShot(True)
        self._auto_complete_timer.timeout.connect(self._trigger_auto_completion)

        # --- 添加放大按钮 ---
        self._create_fullscreen_button("放大" if dialog is None else "缩小")

        # --- 连接补全工作线程信号 ---
        self.completion_worker.completion_ready.connect(self._on_completions_ready)
        self.completion_worker.error_occurred.connect(self._on_completion_error)

        # --- 定义类型字符字典，供 _show_popup 方法使用 ---
        self.type_chars = {
            'function': 'F',
            'method': 'M',
            'class': 'C',
            'module': 'M',
            'instance': 'I',
            'keyword': 'K',
            'property': 'P',
            'param': 'P',
            'variable': 'V',
            'custom': '★',  # 自定义补全使用星号
        }

    def _create_fullscreen_button(self, type="放大"):
        """创建全屏按钮"""
        self.fullscreen_button = TransparentToolButton(get_icon(type), parent=self)
        self.fullscreen_button.setIconSize(QSize(28, 28))
        self.fullscreen_button.setFixedSize(28, 28)
        self.fullscreen_button.setToolTip("放大编辑器")
        if type == "放大":
            self.fullscreen_button.clicked.connect(self._open_fullscreen_editor)
        else:
            self.fullscreen_button.clicked.connect(self.dialog.accept)

        self._update_button_position()

    def resizeEvent(self, event):
        """重写调整大小事件以更新按钮位置"""
        super().resizeEvent(event)
        self._update_button_position()

    def _update_button_position(self):
        """更新按钮位置到右上角"""
        button_width = self.fullscreen_button.width()
        button_height = self.fullscreen_button.height()
        x = self.width() - button_width - 30
        y = 6
        self.fullscreen_button.move(x, y)

    def _open_fullscreen_editor(self):
        """打开全屏编辑器"""
        current_code = self.toPlainText()
        dialog = FullscreenCodeDialog(initial_code=current_code, parent=self.parent_widget, code_parent=self.parent)
        if dialog.exec_() == 1:
            new_code = dialog.get_code()
            self.setPlainText(new_code)

    def wheelEvent(self, event):
        """处理鼠标滚轮事件以缩放字体"""
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
        """增加字体大小"""
        if self._current_font_size < 30:
            self._current_font_size += 1
            self._apply_font()

    def _decrease_font_size(self):
        """减少字体大小"""
        if self._current_font_size > 8:
            self._current_font_size -= 1
            self._apply_font()

    def _apply_font(self):
        """应用当前字体设置"""
        font = QFont(self._font_family, self._current_font_size)
        self.set_font(font)

    def set_jedi_environment(self, python_exe_path):
        """设置Jedi环境"""
        if python_exe_path and os.path.exists(python_exe_path):
            try:
                self._jedi_environment = jedi.api.environment.Environment.create_environment(python_exe_path)
                python_dir = os.path.dirname(os.path.abspath(python_exe_path))
                site_packages = os.path.join(python_dir, "Lib", "site-packages")
                if os.path.isdir(site_packages):
                    self._target_site_packages = site_packages
                    print(f"[Jedi] Target site-packages: {site_packages}")
                else:
                    self._target_site_packages = None
            except Exception as e:
                print(f"[Jedi] Error creating environment: {e}")
                self._jedi_environment = None
        else:
            self._target_site_packages = None

    def add_custom_completions(self, words):
        """添加自定义补全"""
        if isinstance(words, str):
            words = [words]
        self.custom_completions.update(words)

    def keyPressEvent(self, event):
        """处理按键事件"""
        modifiers = event.modifiers()
        key = event.key()

        # 处理Shift+Enter
        if modifiers == Qt.ShiftModifier and key in (Qt.Key_Return, Qt.Key_Enter):
            cursor = self.textCursor()
            if self.parent_widget and hasattr(self.parent_widget, '_handle_shift_enter'):
                self.parent_widget._handle_shift_enter(cursor)
            event.accept()
            return

        # 处理补全弹窗导航
        if self.popup.isVisible():
            if key == Qt.Key_Escape:
                self.popup.hide()
                event.accept()
                return
            elif key == Qt.Key_Tab or key == Qt.Key_Return:
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

        # 隐藏弹窗
        if event.text() in '()[]{}.,;:!? ' and self.popup.isVisible():
            self.popup.hide()

        # 处理Enter/Return的缩进逻辑
        if key in (Qt.Key_Return, Qt.Key_Enter):
            cursor = self.textCursor()
            block = cursor.block()
            text = block.text()
            cursor_pos = cursor.positionInBlock()

            line_before_cursor = text[:cursor_pos]
            line_after_cursor = text[cursor_pos:]

            open_count = line_before_cursor.count('[') + line_before_cursor.count('(') + line_before_cursor.count('{')
            close_count = line_before_cursor.count(']') + line_before_cursor.count(')') + line_before_cursor.count('}')

            if open_count > close_count:
                leading_spaces = len(text) - len(text.lstrip())
                new_indent = ' ' * (leading_spaces + 4)
                cursor.insertText('\n' + new_indent)
                if line_after_cursor.strip().startswith(']') or line_after_cursor.strip().startswith(
                        ')') or line_after_cursor.strip().startswith('}'):
                    cursor.insertText('\n' + ' ' * leading_spaces)
                    cursor.movePosition(QTextCursor.PreviousBlock)
                    cursor.movePosition(QTextCursor.EndOfBlock)
                    self.setTextCursor(cursor)
                event.accept()
                return

        # 关键改进：记录光标位置和文本状态，以便在删除时也能触发补全
        cursor = self.textCursor()
        old_pos = cursor.position()
        old_text = self.toPlainText()

        # 执行默认的 keyPressEvent
        super().keyPressEvent(event)

        # 判断是否为删除操作（Backspace 或 Delete）
        is_delete = (key == Qt.Key_Backspace) or (key == Qt.Key_Delete)

        # 根据输入内容决定是否触发补全
        text = event.text()
        should_trigger = False

        if text == '.':
            should_trigger = True
        elif text.isalnum() or text == '_':
            prefix = self._get_completion_prefix()
            if len(prefix) >= 1:  # 更灵敏
                should_trigger = True
        elif is_delete:  # 删除操作
            # 在删除后，检查是否应该显示补全
            if self._should_show_completion_on_delete():
                should_trigger = True

        if should_trigger:
            self._input_delay_timer.start(self._input_delay_ms)

    def _should_show_completion_on_delete(self) -> bool:
        """判断删除字符时是否应该显示补全"""
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()

        # 如果光标在开头，可能不需要补全
        if pos <= 0:
            return False

        # 检查光标前一个字符是否是字母、数字或下划线（即还在标识符内）
        prev_char = text[pos - 1] if pos > 0 else ''
        if prev_char.isalnum() or prev_char == '_':
            return True

        # 如果光标在点号前，也需要补全
        if pos > 0 and text[pos - 1] == '.':
            return True

        return False

    def _on_input_delay_timeout(self):
        """输入延迟超时回调"""
        self._request_completions()

    def _trigger_auto_completion(self):
        """触发自动补全"""
        self._request_completions()

    def _request_completions(self):
        """请求补全"""
        if self._completing:
            return

        if self.completion_future and not self.completion_future.done():
            cursor = self.textCursor()
            text = self.toPlainText()
            line = cursor.blockNumber() + 1
            column = cursor.columnNumber()
            self.pending_completion_request = (text, line, column, self._jedi_environment)
            return

        cursor = self.textCursor()
        text = self.toPlainText()
        line = cursor.blockNumber() + 1
        column = cursor.columnNumber()
        self.completion_future = completion_pool.submit(
            self.completion_worker.request_completions,
            text, line, column, self._jedi_environment
        )

    def _on_completions_ready(self, completions: List[Tuple[str, str, str]]):
        """收到补全结果"""
        if self.pending_completion_request:
            text, line, column, env = self.pending_completion_request
            self.pending_completion_request = None
            self._on_completions_ready_callback(text, line, column, env)
            return

        current_prefix = self._get_completion_prefix()
        self._filter_and_show_completions(completions, current_prefix)

    def _on_completions_ready_callback(self, text, line, column, env):
        """处理等待的补全请求"""
        try:
            script = jedi.Script(code=text, path='<inline>', environment=env)
            jedi_comps = script.complete(line=line, column=column)

            completions = []
            seen = set()
            for comp in jedi_comps:
                name = comp.name
                if name.startswith('_') or name in seen:
                    continue
                seen.add(name)
                type_name = getattr(comp, 'type', 'unknown')
                description = getattr(comp, 'description', '')
                completions.append((name, type_name, description))
                if len(completions) >= 100:
                    break

            current_prefix = self._get_completion_prefix_from_text(text, line, column)
            self._filter_and_show_completions(completions, current_prefix)
        except Exception as e:
            print(f"[Jedi] Error in delayed completion: {e}")

    def _get_completion_prefix_from_text(self, text: str, line: int, column: int):
        """从指定文本位置获取补全前缀"""
        lines = text.split('\n')
        if 0 <= line - 1 < len(lines):
            line_text = lines[line - 1]
            start = column
            while start > 0:
                ch = line_text[start - 1]
                if ch.isalnum() or ch == '_':
                    start -= 1
                else:
                    break
            return line_text[start:column]
        return ""

    def _filter_and_show_completions(self, completions: List[Tuple[str, str, str]], current_prefix: str):
        """过滤并显示补全项"""
        seen = {name for name, _, _ in completions}
        for word in self.custom_completions:
            if word.lower().startswith(current_prefix.lower()) and word not in seen and len(word) >= 2:
                completions.append((word, 'custom', ''))
                seen.add(word)

        if not completions:
            self.popup.hide()
            return

        def sort_key(item):
            name, _, _ = item
            usage_count = self.completion_usage.get(name, 0)
            starts_with_prefix = -1 if name.lower().startswith(current_prefix.lower()) else 0
            return (starts_with_prefix, -usage_count, name.lower())

        completions.sort(key=sort_key)
        completions = completions[:self.max_completions]

        self.popup.clear()
        for name, type_name, description in completions:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, (name, type_name, description))
            item.setData(Qt.DisplayRole, name)  # 确保兼容性
            self.popup.addItem(item)

        if self.popup.count() > 0:
            self._show_popup()
            self.popup.setCurrentRow(0)
        else:
            self.popup.hide()

    def _on_completion_error(self, error_msg: str):
        """处理补全错误"""
        print(f"[Jedi] Completion error: {error_msg}")
        self.popup.hide()

    def _show_popup(self):
        """显示补全弹窗，确保位置跟随光标，并动态调整宽度"""
        rect = self.cursorRect()
        point = rect.bottomLeft()
        point.setY(point.y() + self.popup_offset)
        global_point = self.viewport().mapToGlobal(point)

        # 动态计算最佳宽度
        max_width = 0
        for i in range(self.popup.count()):
            item = self.popup.item(i)
            item_data = item.data(Qt.UserRole)
            if item_data:
                name, type_name, description = item_data
            else:
                name = item.text()
                type_name = ""
                description = ""

            # 计算该项所需宽度
            fm = self.popup.fontMetrics()
            # 类型字符宽度
            char_width = fm.width(self.type_chars.get(type_name, '?')) + 20  # 加上间距
            # 名称宽度
            name_width = fm.width(name) + 20
            # 描述宽度（如果存在）
            desc_width = fm.width(description) + 20 if description else 0
            # 总宽度
            total_width = char_width + name_width + desc_width + 40  # 额外边距
            max_width = max(max_width, total_width)

        # 设置弹窗宽度（限制在屏幕范围内）
        screen_width = self.screen().geometry().width()
        popup_width = min(max_width, screen_width - 100)  # 留出边距
        popup_width = max(popup_width, 500)  # 最小宽度500

        self.popup.setFixedWidth(popup_width)
        self.popup.move(global_point)
        item_height = self.popup.sizeHintForRow(0) if self.popup.count() > 0 else 40  # 使用新的高度
        visible_items = min(self.popup.count(), 15)
        height = item_height * visible_items + 10
        self.popup.setFixedHeight(height)
        self.popup.show()
        self.popup.setFocus()

    def _get_completion_prefix(self):
        """获取补全前缀"""
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
        """应用选中的补全"""
        if not self.popup.currentItem() or self._completing:
            self.popup.hide()
            return

        self._completing = True
        try:
            item = self.popup.currentItem()
            completion_data = item.data(Qt.UserRole)
            if completion_data:
                completion, _, _ = completion_data
            else:
                completion = item.text()

            self.completion_usage[completion] = self.completion_usage.get(completion, 0) + 1
            if len(self.completion_usage) > 500:
                oldest = next(iter(self.completion_usage))
                del self.completion_usage[oldest]

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
        """处理补全选择"""
        self._apply_selected_completion()

    def focusOutEvent(self, event):
        """处理焦点丢失事件"""
        self.popup.hide()
        super().focusOutEvent(event)

    def __del__(self):
        """清理资源"""
        if hasattr(self, 'completion_worker'):
            self.completion_worker.running = False


class FullscreenCodeDialog(MessageBoxBase):
    """全屏代码对话框"""

    def __init__(self, initial_code="", parent=None, code_parent=None):
        super().__init__(parent)
        self.setWindowTitle("代码编辑器")

        self.code_editor = JediCodeEditor(parent=parent, code_parent=code_parent, dialog=self)
        self.code_editor.setPlainText(initial_code)
        self.code_editor.setMinimumSize(1000, 600)

        self.viewLayout.addWidget(self.code_editor)
        self.buttonGroup.hide()

    def get_code(self):
        return self.code_editor.toPlainText()