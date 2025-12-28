# -*- coding: utf-8 -*-
import re
import sys
from typing import List, Tuple
from urllib.parse import quote

from PyQt5.QtCore import Qt, QTimer, QSize, QRect, QEvent, QPoint, pyqtSignal
from PyQt5.QtGui import QFont, QTextCursor, QColor, QPainter, QCursor, QTextCharFormat, QKeySequence
from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QStyledItemDelegate, QStyle, QVBoxLayout, QShortcut, \
    QMainWindow, QWidget, QApplication as QApp, QApplication, QToolTip
from intervaltree import IntervalTree
from loguru import logger
from qfluentwidgets import TransparentToolButton
from qtpy import QtCore
from spyder.plugins.editor.panels.utils import FoldingRegion
from spyder.plugins.editor.widgets.codeeditor import CodeEditor
from spyder.widgets.findreplace import FindReplace

from app.server_manager.lsp_server.lsp_manager import LspClientManager
from app.utils.utils import get_icon


class CompletionItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.type_colors = {
            'function': QColor("#FFB86C"),
            'method': QColor("#FFB86C"),
            'class': QColor("#82AAFF"),
            'module': QColor("#B267E6"),
            'instance': QColor("#F07178"),
            'keyword': QColor("#C792EA"),
            'property': QColor("#FFCB6B"),
            'param': QColor("#F78C6C"),
            'variable': QColor("#E0E0E0"),
            'custom': QColor("#89DDFF"),
            'builtin': QColor("#FFB86C"),
            'enum': QColor("#82AAFF"),
            'attribute': QColor("#E0E0E0"),
            'unknown': QColor("#CCCCCC"),
        }
        self.type_chars = {
            'function': 'Ƒ',
            'method': 'ℳ',
            'class': '𝒞',
            'module': 'ℳ',
            'instance': 'ℐ',
            'keyword': '𝕂',
            'property': '𝒫',
            'param': '𝒫',
            'variable': '𝒱',
            'custom': '★',
            'builtin': 'ℬ',
            'enum': 'ℰ',
            'attribute': '𝒜',
        }
        self.max_description_length = 60
        self.truncation_suffix = "..."
        self.max_detail_length = 40

    def _truncate_description(self, description: str) -> str:
        if len(description) > self.max_description_length:
            return description[:self.max_description_length - len(self.truncation_suffix)] + self.truncation_suffix
        return description

    def _truncate_detail(self, detail: str) -> str:
        if len(detail) > self.max_detail_length:
            return detail[:self.max_detail_length - len(self.truncation_suffix)] + self.truncation_suffix
        return detail

    def paint(self, painter: QPainter, option, index):
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor("#2A3B4D"))
            painter.setPen(QColor("#FFFFFF"))
        else:
            painter.fillRect(option.rect, QColor("#19232D"))
            painter.setPen(QColor("#FFFFFF"))
        item_data = index.data(Qt.UserRole)
        if item_data and isinstance(item_data, dict):
            name = item_data.get('label', '')
            kind = item_data.get('kind', 0)
            description = item_data.get('documentation', '')
            if isinstance(description, dict):
                description = description.get('value', '')
            detail = item_data.get('detail', '')
            type_name = self.parent()._kind_to_string(kind)
            description = self._truncate_description(str(description))
            detail = self._truncate_detail(str(detail)) if detail else ""
        else:
            name = str(index.data(Qt.DisplayRole) or "")
            type_name = "unknown"
            description = ""
            detail = ""
        padding = 10
        char_width = 20
        char_spacing = 10
        rect = option.rect.adjusted(padding, 0, -padding, 0)
        char_rect = QRect(rect.left(), rect.top(), char_width, rect.height())
        available_width = rect.width() - char_width - char_spacing
        painter.setFont(option.font)
        fm = painter.fontMetrics()
        combined_info = ""
        if description or detail:
            parts = []
            if description:
                parts.append(description)
            if detail:
                parts.append(detail)
            combined_info = "; ".join(parts)
            combined_info = self._truncate_detail(combined_info)
            info_width = fm.width(combined_info)
            max_info_width = int(available_width * 0.6)
            if info_width > max_info_width:
                extra = info_width - max_info_width
                cut_len = len(combined_info) - (extra // (fm.averageCharWidth() or 1)) - len(self.truncation_suffix)
                if cut_len > 0:
                    combined_info = combined_info[:max(0, cut_len)] + self.truncation_suffix
                    info_width = fm.width(combined_info)
        else:
            info_width = 0
            combined_info = ""
        name_max_width = available_width - info_width - (10 if info_width > 0 else 0)
        if name_max_width < 0:
            name_max_width = available_width
            info_width = 0
            combined_info = ""
        name_width = fm.width(name)
        if name_width > name_max_width:
            name = fm.elidedText(name, Qt.ElideRight, name_max_width)
        name_x = rect.left() + char_width + char_spacing
        name_rect = QRect(name_x, rect.top(), name_max_width, rect.height())
        type_char = self.type_chars.get(type_name, '?')
        type_color = self.type_colors.get(type_name, self.type_colors['unknown'])
        painter.setPen(type_color)
        char_font = painter.font()
        char_font.setPointSize(char_font.pointSize() + 1)
        char_font.setBold(True)
        painter.setFont(char_font)
        painter.drawText(char_rect, Qt.AlignCenter, type_char)
        painter.setFont(option.font)
        painter.setPen(QColor("#FFFFFF"))
        name_font = painter.font()
        name_font.setPointSize(name_font.pointSize() + 1)
        painter.setFont(name_font)
        painter.drawText(name_rect, Qt.AlignLeft | Qt.AlignVCenter, name)
        painter.setFont(option.font)
        if combined_info:
            info_x = name_x + available_width - info_width
            info_rect = QRect(info_x, rect.top(), info_width, rect.height())
            desc_font = painter.font()
            desc_font.setPointSize(desc_font.pointSize() - 1)
            desc_font.setItalic(True)
            painter.setFont(desc_font)
            painter.setPen(QColor("#AAAAAA"))
            painter.drawText(info_rect, Qt.AlignLeft | Qt.AlignVCenter, combined_info)
            painter.setFont(option.font)

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 40)


class JediCodeEditor(CodeEditor):
    lsp_manager = None

    def __init__(self, parent=None, code_parent=None, python_exe_path=None, popup_offset=2, dialog=None):
        super().__init__()
        self.python_exe_path = python_exe_path or sys.executable
        self.popup_offset = popup_offset
        self.parent_widget = parent
        self.code_parent = code_parent
        self._lsp_ready = False
        self._completing = False
        self._document_version = 0
        self._lsp_document_opened = False

        # --- 自定义补全词 ---
        self.custom_completions = {
            'True', 'False', 'None', 'Exception', 'OSError', 'ValueError', 'TypeError',
            'print', 'input', 'open', 'range', 'enumerate', 'len', 'str', 'int', 'float',
            'list', 'dict', 'set', 'tuple', '__init__', '__name__', '__file__',
        }
        self.set_completion_environment(python_exe_path)

        # --- 补全弹窗 ---
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
            QListWidget::item:selected {
                background-color: #2A3B4D;
            }
            QScrollBar:vertical {
                width: 8px;
                background-color: #2A3B4D;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #32414B;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #4A5C6D;
            }
        """)
        self.popup.setFont(QFont('Consolas', 12))
        self.popup.setItemDelegate(CompletionItemDelegate(self))
        self.popup.itemClicked.connect(self._on_completion_selected)
        self.popup.itemEntered.connect(self._on_item_hovered)
        self.popup.setUniformItemSizes(True)
        self.popup.setMaximumWidth(1200)
        self.popup.setMinimumWidth(500)
        self.popup.hide()
        self.popup.installEventFilter(self)

        # --- 超时自动关闭 ---
        self._popup_timeout_timer = QTimer()
        self._popup_timeout_timer.setSingleShot(True)
        self._popup_timeout_timer.timeout.connect(self._on_popup_timeout)
        self._popup_timeout_duration = 10000

        # --- 补全防抖与去重 ---
        self._completion_request_timer = QTimer()
        self._completion_request_timer.setSingleShot(True)
        self._completion_request_timer.timeout.connect(self._do_request_completions)
        self._last_completion_request = ("", -1, -1)  # (prefix, line, col)

        # --- 编辑器设置 ---
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
            underline_errors=True,
            completions_hint=False,
            highlight_current_line=True,
        )

        # --- 快捷键 ---
        self.shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self.shortcut.activated.connect(self._request_completions)

        # --- 按钮 ---
        btn_text = "缩小" if dialog else "放大"
        self.fullscreen_button = TransparentToolButton(get_icon(btn_text), parent=self)
        self.fullscreen_button.setIconSize(QSize(28, 28))
        self.fullscreen_button.setFixedSize(28, 28)
        self.fullscreen_button.setToolTip("放大编辑器")

        self.spyder_button = TransparentToolButton(get_icon("spyder"), parent=self)
        self.spyder_button.setIconSize(QSize(28, 28))
        self.spyder_button.setFixedSize(28, 28)
        self.spyder_button.setToolTip("在 Spyder 中打开当前代码")
        self.spyder_button.clicked.connect(self._open_in_spyder)

        self._update_button_position()

        # --- Parso 语法检查 ---
        self._parso_timer = QTimer()
        self._parso_timer.setSingleShot(True)
        self._parso_timer.timeout.connect(self._run_parso_analysis)
        self.textChanged.connect(self._on_text_changed_for_parso)

        # --- LSP 同步 ---
        self._lsp_sync_timer = QTimer()
        self._lsp_sync_timer.setSingleShot(True)
        self._lsp_sync_timer.timeout.connect(self._sync_to_lsp)
        self.textChanged.connect(self._on_text_changed_for_lsp)

        # --- LSP 折叠 ---
        self._folding_timer = QTimer()
        self._folding_timer.setSingleShot(True)
        self._folding_timer.timeout.connect(self._request_folding)
        self.textChanged.connect(self._on_text_changed_for_folding)

        # Initialize folding_status
        if hasattr(self, 'folding_panel') and self.folding_panel:
            self.folding_panel.folding_status = {}

    def set_completion_environment(self, python_exe: str):
        if self.lsp_manager:
            self.lsp_manager.shutdown()
            self.lsp_manager = None
        self.lsp_manager = LspClientManager(python_path=python_exe)
        self.lsp_manager.initialized.connect(self._on_lsp_initialized)
        self.lsp_manager.completion_ready.connect(self._on_lsp_completions_ready)
        self.lsp_manager.diagnostics_ready.connect(self._on_lsp_diagnostics_ready)
        self.lsp_manager.folding_ready.connect(self._on_lsp_folding_ready)
        self.lsp_manager.start()

    # ========== LSP 集成 ==========
    def _document_uri(self) -> str:
        return "file://" + quote("/tmp/editor.py")

    def _on_lsp_initialized(self):
        self._lsp_ready = True
        code = self.toPlainText()
        if code.strip():
            self._sync_to_lsp()

    def _on_text_changed_for_lsp(self):
        if self._lsp_ready:
            self._lsp_sync_timer.start(300)

    def _on_text_changed_for_folding(self):
        if self._lsp_ready:
            self._folding_timer.start(800)

    def _sync_to_lsp(self):
        if not self._lsp_ready:
            return
        code = self.toPlainText()
        self._document_version += 1
        if not self._lsp_document_opened:
            self.lsp_manager.open_document(code)
            self._lsp_document_opened = True
        else:
            self.lsp_manager.change_document(code)
        self._request_folding()

    def _request_folding(self):
        if self._lsp_ready:
            self.lsp_manager.request_folding_ranges(self._document_uri())

    def _kind_to_string(self, kind: int) -> str:
        KIND_MAP = {
            2: 'method', 3: 'function', 4: 'constructor',
            5: 'field', 6: 'variable', 7: 'class', 8: 'interface',
            9: 'module', 10: 'property', 13: 'enum',
            12: 'value', 14: 'keyword', 25: 'typeparameter'
        }
        return KIND_MAP.get(kind, 'unknown')

    def _on_lsp_completions_ready(self, completion_items: List[dict]):
        current_prefix = self._get_completion_prefix().lower()
        displayed_items = []

        for item in completion_items:
            label = item.get('label', '')
            kind = item.get('kind', 0)
            if kind in (1, 15, 16, 17, 18):  # text, snippet, color, file, reference
                continue

            # ✅ 使用 LSP 的 filterText 进行精准过滤
            filter_text = item.get('filterText', label)
            if not filter_text.lower().startswith(current_prefix):
                continue

            displayed_items.append(item)

        # ✅ 使用 LSP 的 sortText 进行排序
        def sort_key(item):
            sort_text = item.get('sortText', '')
            label = item.get('label', '')
            return (sort_text, label.lower())

        displayed_items.sort(key=sort_key)
        displayed_items = displayed_items[:20]  # 限制数量防卡
        self._show_completions(displayed_items)

    def _show_completions(self, items: List[dict]):
        if not items:
            self.popup.hide()
            self._popup_timeout_timer.stop()
            return

        self.popup.clear()
        for item in items:
            label = item['label']
            list_item = QListWidgetItem(label)
            list_item.setData(Qt.UserRole, item)
            self.popup.addItem(list_item)

        # ✅ 延迟显示，避免空闪
        QTimer.singleShot(10, self._show_popup_safe)

    def _show_popup_safe(self):
        if self.popup.count() > 0:
            self._show_popup()
            self.popup.setCurrentRow(0)

    def _on_lsp_diagnostics_ready(self, diagnostics: List[dict]):
        self.clear_extra_selections('lsp_underline')
        block = self.document().firstBlock()
        while block.isValid():
            data = block.userData()
            if data and hasattr(data, 'code_analysis'):
                data.code_analysis = [x for x in data.code_analysis if x[0] != 'lsp']
                if not data.code_analysis:
                    data.color = None
            block = block.next()

        has_error = False
        for diag in diagnostics:
            try:
                line = diag['range']['start']['line']
                severity = diag.get('severity', 1)
                message = diag.get('message', '').strip()
                if not message:
                    continue
                block = self.document().findBlockByNumber(line)
                if not block.isValid():
                    continue
                data = block.userData()
                if not data:
                    from spyder.plugins.editor.utils.editor import BlockUserData
                    data = BlockUserData(self)
                    block.setUserData(data)
                data.code_analysis.append(('lsp', '', severity, message))
                data.color = self.error_color if severity == 1 else self.warning_color
                has_error = True

                start_char = diag['range']['start']['character']
                end_char = diag['range']['end']['character']
                start_pos = block.position() + start_char
                end_pos = block.position() + end_char
                cursor = QTextCursor(self.document())
                cursor.setPosition(start_pos)
                cursor.setPosition(end_pos, QTextCursor.KeepAnchor)
                self.highlight_selection(
                    'lsp_underline',
                    cursor,
                    underline_color=QColor(data.color),
                    underline_style=QTextCharFormat.WaveUnderline
                )
            except Exception as e:
                logger.error(f"[LSP] Error processing diagnostic: {e}")

        if has_error:
            self.sig_flags_changed.emit()
        if hasattr(self, 'linenumberarea'):
            self.linenumberarea.update()

    def _on_lsp_folding_ready(self, folding_ranges: List[dict]):
        if not hasattr(self, 'folding_panel') or not self.folding_panel:
            return

        current_tree = IntervalTree()
        folding_regions = {}
        folding_nesting = {}
        folding_levels = {}
        folding_status = {}

        for fr in folding_ranges:
            start = fr['startLine'] + 1
            end = fr['endLine'] + 1
            if end > start:
                folding_regions[start] = end
                folding_status[start] = False  # 默认展开
                current_tree[start:end + 1] = (start, end)
                folding_levels[start] = 1
                folding_nesting[start] = []

        root = FoldingRegion(None, None)
        self.folding_panel.update_folding(
            (current_tree, root, folding_regions, folding_nesting, folding_levels, folding_status)
        )

        # ✅ 保存 folding_status 到 panel
        self.folding_panel.folding_regions = folding_regions
        self.folding_panel.folding_status = folding_status

    # ========== 补全核心 ==========
    def _request_completions(self):
        """防抖触发补全"""
        if self._completing or not self._lsp_ready:
            return
        if not self._is_in_code_context():
            return
        cursor = self.textCursor()
        if cursor.position() > 0:
            text = self.toPlainText()
            if text[cursor.position() - 1] == '.':
                self._do_request_completions()
                return
        self._completion_request_timer.start(100)

    def _do_request_completions(self):
        cursor = self.textCursor()
        line = cursor.blockNumber()
        col = cursor.columnNumber()
        prefix = self._get_completion_prefix()

        # ✅ 请求去重：相同位置不重复请求
        if (prefix, line, col) == self._last_completion_request:
            return
        self._last_completion_request = (prefix, line, col)

        self.lsp_manager.request_completion(line, col)

    def _is_in_code_context(self) -> bool:
        """使用 parso 判断是否在字符串/注释中"""
        try:
            import parso
            code = self.toPlainText()
            cursor_pos = self.textCursor().position()
            line, col = self._pos_to_line_col(code, cursor_pos)
            module = parso.parse(code, error_recovery=False)
            leaf = module.get_leaf_for_position((line, col), include_implicit=False)
            if leaf and leaf.type in ('string', 'fstring', 'fstring_string', 'comment'):
                return False
            return True
        except:
            cursor = self.textCursor()
            block = cursor.block()
            text = block.text()
            col = cursor.columnNumber()
            before = text[:col]
            if before.count('"') % 2 == 1 or before.count("'") % 2 == 1:
                return False
            if '#' in before:
                return False
            return True

    def _pos_to_line_col(self, text: str, pos: int) -> Tuple[int, int]:
        lines = text.splitlines(True)
        current_pos = 0
        for line_idx, line in enumerate(lines):
            if current_pos + len(line) >= pos:
                return line_idx, pos - current_pos
            current_pos += len(line)
        return len(lines) - 1, max(0, len(lines[-1]) - 1) if lines else 0

    def _get_completion_prefix(self) -> str:
        cursor = self.textCursor()
        pos = cursor.position()
        if pos <= 0:
            return ""
        text = self.toPlainText()
        start = pos
        while start > 0:
            ch = text[start - 1]
            if ch.isalnum() or ch == '_':
                start -= 1
            else:
                break
        return text[start:pos]

    def _show_popup(self):
        """✅ PyCharm 级智能补全框：优先向下，动态数量，绝不越界"""
        if self.popup.isVisible():
            return

        cursor_rect = self.cursorRect()
        if cursor_rect.isNull():
            return

        editor_global_pos = self.mapToGlobal(QPoint(0, 0))
        screen_cursor_pos = QPoint(
            editor_global_pos.x() + cursor_rect.left(),
            editor_global_pos.y() + cursor_rect.bottom()
        )

        screen = QApplication.screenAt(editor_global_pos) or QApplication.primaryScreen()
        available = screen.availableGeometry()  # ✅ 使用 availableGeometry（避开任务栏）

        # === 宽度计算 ===
        max_width = 500
        for i in range(self.popup.count()):
            item = self.popup.item(i)
            fm = self.popup.fontMetrics()
            text_width = fm.boundingRect(item.text()).width() + 120
            max_width = max(max_width, text_width)
        popup_width = min(max(500, max_width), available.width() - 100)
        x = max(available.left(), min(screen_cursor_pos.x(), available.right() - popup_width))

        # === 高度与方向决策 ===
        item_height = 40
        total_items = self.popup.count()

        # 向下可用空间
        space_down = available.bottom() - screen_cursor_pos.y()
        # 向上可用空间
        space_up = screen_cursor_pos.y() - cursor_rect.height() - available.top()

        # ✅ 优先向下，但至少显示 2 项才有意义
        if space_down >= item_height * 2 + 10:
            # 向下显示：最多 8 项（避免遮挡代码）
            max_visible = min(total_items, 8)
            popup_height = max(46, item_height * max_visible + 6)
            y = screen_cursor_pos.y()
            # 确保不超出屏幕底部
            if y + popup_height > available.bottom():
                popup_height = available.bottom() - y
                max_visible = max(1, (popup_height - 6) // item_height)
                popup_height = item_height * max_visible + 6
        else:
            # 向上显示：最多 15 项（上方通常空间更大）
            max_visible = min(total_items, 15)
            popup_height = max(46, item_height * max_visible + 6)
            y = screen_cursor_pos.y() - cursor_rect.height() - popup_height
            # 确保不超出屏幕顶部
            if y < available.top():
                y = available.top()
                popup_height = screen_cursor_pos.y() - cursor_rect.height() - y
                max_visible = max(1, (popup_height - 6) // item_height)
                popup_height = item_height * max_visible + 6

        # ✅ 重新设置弹窗项数（只显示 max_visible 项）
        if max_visible < total_items:
            # 临时裁剪（仅用于显示，不丢失数据）
            old_items = []
            for i in range(self.popup.count()):
                old_items.append((
                    self.popup.item(i).text(),
                    self.popup.item(i).data(Qt.UserRole)
                ))
            self.popup.clear()
            for i in range(max_visible):
                text, data = old_items[i]
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, data)
                self.popup.addItem(item)

        self.popup.setFixedSize(popup_width, popup_height)
        self.popup.move(x, y)
        self.popup.show()
        self._popup_timeout_timer.start(self._popup_timeout_duration)

    def _apply_selected_completion(self):
        if not self.popup.currentItem() or self._completing:
            self.popup.hide()
            self._popup_timeout_timer.stop()
            return

        self._completing = True
        try:
            item = self.popup.currentItem()
            completion_item = item.data(Qt.UserRole)
            if not completion_item:
                return

            cursor = self.textCursor()
            prefix = self._get_completion_prefix()
            if prefix:
                cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(prefix))

            # ✅ 智能插入：处理括号和光标位置
            new_text = None
            if 'textEdit' in completion_item and completion_item['textEdit']:
                new_text = completion_item['textEdit'].get('newText', completion_item['label'])
            elif 'insertText' in completion_item:
                new_text = completion_item['insertText']
            else:
                new_text = completion_item['label']

            kind = completion_item.get('kind', 0)
            is_function_like = kind in (2, 3, 4)  # method, function, constructor

            if is_function_like and new_text == completion_item['label']:
                has_params = False
                try:
                    detail = completion_item.get('detail', '')
                    if '(' in detail and ')' in detail:
                        # 简单判断是否有参数（如 "func(x, y)"）
                        content = detail.split('(', 1)[1].split(')', 1)[0].strip()
                        has_params = len(content) > 0 and content != 'self'
                except:
                    pass

                new_text += "()"
                cursor.insertText(new_text)
                if has_params:
                    cursor.movePosition(QTextCursor.PreviousCharacter)  # 光标在括号内
            else:
                cursor.insertText(new_text)

            self.setTextCursor(cursor)
        finally:
            self._completing = False
            self.popup.hide()
            self._popup_timeout_timer.stop()

    def _on_completion_selected(self, item):
        self._apply_selected_completion()

    def _on_item_hovered(self, item):
        data = item.data(Qt.UserRole)
        if data and isinstance(data, dict):
            doc = data.get('documentation', '')
            if isinstance(doc, dict):
                doc = doc.get('value', '')
            if doc:
                QToolTip.showText(QCursor.pos(), str(doc))

    def _on_popup_timeout(self):
        if self.popup.isVisible():
            self.popup.hide()

    def _pep8_bracket_newline(self, opening_bracket: str):
        """在 opening bracket 后按 Enter，实现 PEP8 换行"""
        cursor = self.textCursor()

        # 获取当前行缩进
        block = cursor.block()
        current_line = block.text()
        indent = len(current_line) - len(current_line.lstrip(' '))

        # 计算新缩进（+4）
        new_indent = ' ' * (indent + 4)

        # 插入新行
        cursor.movePosition(QTextCursor.EndOfLine)
        cursor.insertText('\n' + new_indent)

        # 移动光标到新行
        self.setTextCursor(cursor)

    def _smart_newline(self):
        cursor = self.textCursor()
        current_line = cursor.block().text()
        leading_spaces = len(current_line) - len(current_line.lstrip(' '))
        indent = ' ' * leading_spaces
        cursor.movePosition(QTextCursor.EndOfLine)
        cursor.insertText('\n' + indent)
        self.setTextCursor(cursor)

    def _toggle_comment(self):
        cursor = self.textCursor()
        doc = self.document()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        c1 = QTextCursor(doc)
        c1.setPosition(start)
        c1.movePosition(QTextCursor.StartOfLine)
        start_line_pos = c1.position()

        c2 = QTextCursor(doc)
        c2.setPosition(end)
        if c2.atBlockStart() and end > start:
            c2.movePosition(QTextCursor.Left)
        c2.movePosition(QTextCursor.EndOfLine)
        end_line_pos = c2.position()

        c1.setPosition(start_line_pos)
        c1.setPosition(end_line_pos, QTextCursor.KeepAnchor)
        lines = c1.selectedText().split('\u2029')

        def is_commented(s):
            return s.strip().startswith('#')

        all_commented = all(not t.strip() or is_commented(t) for t in lines)

        new_lines = []
        if all_commented:
            for t in lines:
                if not t.strip():
                    new_lines.append(t)
                else:
                    new_lines.append(re.sub(r'^(\s*)#\s?', r'\1', t))
        else:
            for t in lines:
                if not t.strip():
                    new_lines.append(t)
                else:
                    m = re.match(r'^(\s*)', t)
                    indent = m.group(1) if m else ''
                    new_lines.append(f"{indent}# {t[len(indent):]}")

        cursor.beginEditBlock()
        c1.insertText('\n'.join(new_lines))
        cursor.endEditBlock()

    # ========== 事件处理 ==========
    def eventFilter(self, obj, event):
        if obj == self.popup:
            if event.type() == QEvent.MouseButtonPress:
                pos = event.globalPos()
                if not self.popup.geometry().contains(pos):
                    self.popup.hide()
                    self._popup_timeout_timer.stop()
                    return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        key = event.key()
        if self.popup.isVisible():
            if key == Qt.Key_Tab:
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
            elif key in (Qt.Key_Return, Qt.Key_Enter):
                # ✅ Enter 仅换行，不确认补全
                self.popup.hide()
                self._popup_timeout_timer.stop()
                super().keyPressEvent(event)
                return
            elif event.text() in '()[]{}.,;:!? =+-*/%&|<>^~':
                self.popup.hide()
                self._popup_timeout_timer.stop()

        # 处理 Ctrl+C
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_C:
            self._copy_with_folding()
            event.accept()
            return

        if key in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers():
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

        # 自定义快捷键
        if event.modifiers() == Qt.ShiftModifier and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._smart_newline()
            event.accept()
            return
        elif event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Slash:
            self._toggle_comment()
            event.accept()
            return

        trigger_complete = False
        if event.text() == '.':
            trigger_complete = True
        elif event.text().isalnum() or event.text() == '_':
            trigger_complete = True

        super().keyPressEvent(event)

        if trigger_complete and self._is_in_code_context():
            self._request_completions()

    def wheelEvent(self, event):
        if self.popup.isVisible():
            self.popup.hide()
            self._popup_timeout_timer.stop()
        super().wheelEvent(event)

    def focusOutEvent(self, event):
        self.popup.hide()
        self._popup_timeout_timer.stop()
        QToolTip.hideText()
        super().focusOutEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_button_position()

    def _update_button_position(self):
        if not hasattr(self, 'fullscreen_button'):
            return
        button_width = 28
        button_spacing = 8
        x = self.width() - button_width - 30
        y_top = 6
        y_bottom = y_top + button_width + button_spacing
        self.fullscreen_button.move(x, y_top)
        self.spyder_button.move(x, y_bottom)

    def _open_in_spyder(self):
        pass

    def close_lsp(self):
        if self.lsp_manager:
            self.lsp_manager.shutdown()
            QtCore.QTimer.singleShot(100, self.lsp_manager.wait)

    def textForBlock(self, block):
        """
        重写折叠行的显示文本
        - 普通折叠：显示 "..."
        - 括号折叠：显示 "[...]", "(...)", "{...}"
        """
        if not block.isValid():
            return ""

        # 检查该块是否是折叠头
        if hasattr(self, 'folding_panel') and self.folding_panel:
            line_number = block.blockNumber() + 1  # 1-based
            if (hasattr(self.folding_panel, 'folding_status') and
                    line_number in self.folding_panel.folding_status):
                if self.folding_panel.folding_status[line_number]:
                    # 当前是折叠状态
                    text = block.text()
                    stripped = text.strip()

                    # 检查是否以 opening bracket 开头，closing bracket 结尾
                    if stripped.startswith('[') and stripped.endswith(']'):
                        return "[...]"
                    elif stripped.startswith('(') and stripped.endswith(')'):
                        return "(...)"
                    elif stripped.startswith('{') and stripped.endswith('}'):
                        return "{...}"
                    else:
                        return "..."

        return block.text()

    def _copy_with_folding(self):
        """复制时，如果选中折叠行，复制整个折叠内容"""
        cursor = self.textCursor()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        if start == end:
            # 没有选中，复制当前行（考虑折叠）
            block = cursor.block()
            line_number = block.blockNumber() + 1

            # 检查是否是折叠头
            if (hasattr(self.folding_panel, 'folding_status') and
                    line_number in self.folding_panel.folding_status and
                    self.folding_panel.folding_status[line_number]):
                # 获取折叠范围
                if (hasattr(self.folding_panel, 'folding_regions') and
                        line_number in self.folding_panel.folding_regions):
                    end_line = self.folding_panel.folding_regions[line_number]
                    # 选中整个折叠区域
                    start_pos = self.document().findBlockByNumber(line_number - 1).position()
                    end_block = self.document().findBlockByNumber(end_line - 1)
                    end_pos = end_block.position() + end_block.length() - 1  # 包括换行符

                    copy_cursor = QTextCursor(self.document())
                    copy_cursor.setPosition(start_pos)
                    copy_cursor.setPosition(end_pos, QTextCursor.KeepAnchor)
                    clipboard = QApplication.clipboard()
                    clipboard.setText(copy_cursor.selectedText())
                    return

        # 默认复制行为
        super().copy()

    # ========== Parso 语法检查 ==========
    def _on_text_changed_for_parso(self):
        self._parso_timer.stop()
        self._parso_timer.start(800)

    def _run_parso_analysis(self):
        code = self.toPlainText()
        if not code.strip():
            self._clear_parso_results()
            return

        try:
            import parso
            grammar = parso.load_grammar()
            module = grammar.parse(code, error_recovery=True)
            errors = list(grammar.iter_errors(module))
        except Exception as e:
            logger.error(f"[Parso] Parse error: {e}")
            errors = []

        self._clear_parso_results()
        self.clear_extra_selections('parso_underline')

        # ✅ 确保是 QColor
        error_color = QColor(self.error_color) if self.error_color else QColor("#ff0000")
        warning_color = QColor(self.warning_color) if self.warning_color else QColor("#ffaa00")

        for error in errors:
            try:
                line_number = error.start_pos[0]  # 1-based
                column_number = error.start_pos[1]
                message = error.message
                block = self.document().findBlockByNumber(line_number - 1)
                if not block.isValid():
                    continue
                data = block.userData()
                if not data:
                    from spyder.plugins.editor.utils.editor import BlockUserData
                    data = BlockUserData(self)
                    block.setUserData(data)
                data.code_analysis.append(('parso', '', 2, message))
                data.color = error_color  # ✅ QColor

                start_pos = block.position() + column_number
                end_pos = start_pos + 1
                cursor = QTextCursor(self.document())
                cursor.setPosition(start_pos)
                cursor.setPosition(end_pos, QTextCursor.KeepAnchor)
                self.highlight_selection(
                    'parso_underline',
                    cursor,
                    underline_color=error_color,  # ✅ QColor
                    underline_style=QTextCharFormat.WaveUnderline
                )
            except Exception as e:
                logger.error(f"[Parso] Highlight error: {e}")

        self.sig_flags_changed.emit()
        if hasattr(self, 'linenumberarea'):
            self.linenumberarea.update()

    def _clear_parso_results(self):
        self.clear_extra_selections('parso_underline')
        block = self.document().firstBlock()
        while block.isValid():
            data = block.userData()
            if data and hasattr(data, 'code_analysis'):
                data.code_analysis = [x for x in data.code_analysis if x[0] != 'parso']
                if not data.code_analysis:
                    data.color = None
            block = block.next()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Professional LSP Code Editor")
        self.setStyleSheet("background-color: #333; color: white;")
        self.resize(800, 600)
        self.find_replace = FindReplace(self, True)
        self.editor = JediCodeEditor(python_exe_path=r"D:\work\CanvasMind\.venv\Scripts\python.exe")
        example_code = """import numpy as np
a = np.array([1, 2, 3])
# Try: a. then Ctrl+Space
def hello(x, y):
    z = x + y
    return z

result = hello(1, 2)"""
        self.editor.set_text(example_code)
        self.find_replace.set_editor(self.editor)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.find_replace)
        layout.addWidget(self.editor)
        self.setCentralWidget(central)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    win.editor.setFocus()
    sys.exit(app.exec_())