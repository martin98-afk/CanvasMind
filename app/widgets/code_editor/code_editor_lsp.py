# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
import ast
import sys
from typing import List, Tuple, Dict

import parso
from PyQt5.QtCore import Qt, QTimer, QSize, QRect
from PyQt5.QtGui import QFont, QTextCursor, QColor, QPainter, QCursor, QTextCharFormat, QKeySequence
from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QStyledItemDelegate, QStyle, QVBoxLayout, QShortcut
from PyQt5.QtWidgets import QMainWindow, QWidget, QApplication, QToolTip
from intervaltree import IntervalTree
from loguru import logger
from qfluentwidgets import TransparentToolButton
from qtpy import QtCore
from spyder.plugins.editor.panels.utils import FoldingRegion
from spyder.plugins.editor.widgets.codeeditor import CodeEditor
from spyder.widgets.findreplace import FindReplace

from app.server_manager.lsp_server.lsp_manager import LspClientManager
from app.utils.utils import get_icon


# --- 新增：使用 AST 计算折叠区域（保持不变）---
def compute_folding_from_ast(code: str):
    try:
        tree = ast.parse(code)
        folding_regions: Dict[int, int] = {}
        folding_status: Dict[int, bool] = {}
        lines = code.splitlines(keepends=True)
        def visit_node(node):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                                 ast.If, ast.For, ast.AsyncFor, ast.While,
                                 ast.Try,
                                 ast.With, ast.AsyncWith,
                                 ast.ExceptHandler)):
                start_line = node.lineno
                end_line = -1
                if isinstance(node, ast.ExceptHandler):
                    if hasattr(node, 'end_lineno') and node.end_lineno is not None:
                        end_line = node.end_lineno
                    else:
                        if node.body:
                            last_stmt = node.body[-1]
                            end_line = getattr(last_stmt, 'end_lineno', last_stmt.lineno)
                            end_line = max(end_line, start_line)
                        else:
                            end_line = start_line
                else:
                    if hasattr(node, 'end_lineno') and node.end_lineno is not None:
                        end_line = node.end_lineno
                    else:
                        if node.body:
                            last_stmt = node.body[-1]
                            end_line = getattr(last_stmt, 'end_lineno', last_stmt.lineno)
                            end_line = max(end_line, start_line)
                        else:
                            end_line = start_line
                if end_line > start_line:
                    folding_regions[start_line] = end_line
                    folding_status[start_line] = False
            for child_node in ast.iter_child_nodes(node):
                visit_node(child_node)
        visit_node(tree)
        current_tree = IntervalTree()
        root = FoldingRegion(None, None)
        folding_nesting = {}
        folding_levels = {}
        for start, end in folding_regions.items():
            current_tree[start:end+1] = (start, end)
            folding_levels[start] = 1
            folding_nesting[start] = []
        logger.debug(f"[Folding] AST found {len(folding_regions)} regions.")
        return current_tree, root, folding_regions, folding_nesting, folding_levels, folding_status
    except SyntaxError as e:
        logger.warning(f"[Folding] Syntax error in code, cannot compute folding: {e}")
        return IntervalTree(), FoldingRegion(None, None), {}, {}, {}, {}
    except Exception as e:
        logger.error(f"[Folding] Unexpected error computing folding from AST: {e}")
        return IntervalTree(), FoldingRegion(None, None), {}, {}, {}, {}


class ParsoCodeAnalysis:
    """
    使用 parso 分析代码错误和警告。
    """
    @staticmethod
    def run_parso_analysis(code):
        """
        运行 parso 分析代码。
        返回一个包含错误和警告信息的列表。
        每个元素是一个字典，包含 'row', 'column', 'type' (error/warning), 'message'。
        parso.errors.Error 类包含 row, column, message, code 等属性。
        """
        try:
            # 解析代码，encoding 可以设为 None，parso 通常能处理
            grammar = parso.load_grammar()
            module = grammar.parse(code, error_recovery=True) # error_recovery=True 是关键
            errors = grammar.iter_errors(module)
            messages = []
            for error in errors:
                # Parso 的错误行号是 1-based
                line_number = error.start_pos[0]
                # Parso 的错误列号是 0-based，我们转换为 1-based 以保持一致性
                column_number = error.start_pos[1] + 1
                message_text = error.message
                # Parso 通常报告语法错误，可以视为 error
                msg_type = 'error'
                messages.append({
                    'row': line_number,
                    'column': column_number, # 提供列信息
                    'type': msg_type,
                    'message': message_text
                })
        except Exception as e:
            # 如果 parso 解析本身出错（虽然不太可能），记录下来
            logger.error(f"[Parso] Unexpected error during analysis: {e}")
            messages = []
        return messages


# --- 保留 CompletionItemDelegate（UI 不变）---
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
            'unknown': QColor("#CCCCCC"),
            'variable_str': QColor("#FFCB6B"),
            'variable_int': QColor("#F78C6C"),
            'variable_float': QColor("#F78C6C"),
            'variable_list': QColor("#E0E0E0"),
            'variable_dict': QColor("#E0E0E0"),
            'variable_bool': QColor("#FFB86C"),
            'variable_tuple': QColor("#E0E0E0"),
            'variable_set': QColor("#E0E0E0"),
            'builtin': QColor("#FFB86C"),
            'enum': QColor("#82AAFF"),
            'attribute': QColor("#E0E0E0"),
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
            'variable_str': '𝒱',
            'variable_int': '𝒱',
            'variable_float': '𝒱',
            'variable_list': '𝒱',
            'variable_dict': '𝒱',
            'variable_bool': '𝒱',
            'variable_tuple': '𝒱',
            'variable_set': '𝒱',
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
        if item_data:
            name, type_name, description, detail = item_data
            description = self._truncate_description(description)
            detail = self._truncate_detail(detail) if detail else ""
        else:
            name = str(index.data(Qt.DisplayRole) or "")
            type_name = ""
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
        size = super().sizeHint(option, index)
        return QSize(size.width(), 40)


# --- 新增：仅用 LSP 的补全请求 ---
class JediCodeEditor(CodeEditor):
    _BASE_CODE_CACHE = None
    def __init__(self, parent=None, code_parent=None, python_exe_path=None, popup_offset=2, dialog=None):
        super().__init__()
        self.python_exe_path = python_exe_path
        self.popup_offset = popup_offset
        self.parent_widget = parent
        self.parent = code_parent
        self.custom_completions = set()
        self.add_custom_completions([
            'True', 'False', 'None', 'Exception', 'OSError', 'ValueError', 'TypeError',
            'print', 'input', 'open', 'range', 'enumerate', 'len', 'str', 'int', 'float',
            'list', 'dict', 'set', 'tuple', '__init__', '__name__', '__file__',
        ])
        # --- LSP 初始化 ---
        self.lsp_manager = LspClientManager(python_path=self.python_exe_path or sys.executable)
        self.lsp_manager.initialized.connect(self._on_lsp_initialized)
        self.lsp_manager.completion_ready.connect(self._on_lsp_completions_ready)
        self.lsp_manager.diagnostics_ready.connect(self._on_lsp_diagnostics_ready)
        self.lsp_manager.start()
        self._lsp_ready = False
        self.textChanged.connect(self._on_text_changed_for_lsp)

        # --- 补全弹窗（复用原有 UI）---
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
        self.popup.setItemDelegate(CompletionItemDelegate())
        self.popup.itemClicked.connect(self._on_completion_selected)
        self.popup.itemEntered.connect(self._on_item_hovered)
        self.popup.setUniformItemSizes(True)
        self.popup.setMaximumWidth(1200)
        self.popup.setMinimumWidth(500)
        self.popup.hide()

        # --- 超时自动关闭 ---
        self._popup_timeout_timer = QTimer()
        self._popup_timeout_timer.setSingleShot(True)
        self._popup_timeout_timer.timeout.connect(self._on_popup_timeout)
        self._popup_timeout_duration = 10000

        # --- 编辑器设置 ---
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
            automatic_completions=False,  # 关闭内置补全
            underline_errors=True,
            completions_hint=False,
            highlight_current_line=True,
        )

        # --- 快捷键 ---
        self.shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self.shortcut.activated.connect(self._request_completions)

        # --- 按钮 ---
        self._create_fullscreen_button("放大" if dialog is None else "缩小")
        self.spyder_button = TransparentToolButton(get_icon("spyder"), parent=self)
        self.spyder_button.setIconSize(QSize(28, 28))
        self.spyder_button.setFixedSize(28, 28)
        self.spyder_button.setToolTip("在 Spyder 中打开当前代码")
        self.spyder_button.clicked.connect(self._open_in_spyder)
        self._update_button_position()

        # --- 类型字符映射（用于 delegate）---
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
            'variable_str': '𝒱',
            'variable_int': '𝒱',
            'variable_float': '𝒱',
            'variable_list': '𝒱',
            'variable_dict': '𝒱',
            'variable_bool': '𝒱',
            'variable_tuple': '𝒱',
            'variable_set': '𝒱',
            'builtin': 'ℬ',
            'enum': 'ℰ',
            'attribute': '𝒜',
        }

        # --- 保留 parso 语法检查 ---
        self._parso_timer = QTimer()
        self._parso_timer.setSingleShot(True)
        self._parso_timer.timeout.connect(self._run_parso_analysis)
        self.textChanged.connect(self._on_text_changed_for_parso)

        # --- 折叠更新 ---
        self.textChanged.connect(self._on_text_changed_for_folding)

        self._completing = False

    # ========== LSP 集成 ==========
    def _on_lsp_initialized(self):
        self._lsp_ready = True
        code = self.toPlainText()
        if code.strip():
            self.lsp_manager.open_document(code)

    def _on_text_changed_for_lsp(self):
        if not self._lsp_ready:
            return
        if not hasattr(self, '_lsp_sync_timer'):
            self._lsp_sync_timer = QTimer()
            self._lsp_sync_timer.setSingleShot(True)
            self._lsp_sync_timer.timeout.connect(self._sync_to_lsp)
        self._lsp_sync_timer.start(300)

    def _sync_to_lsp(self):
        code = self.toPlainText()
        if not hasattr(self, '_lsp_first_sync'):
            self.lsp_manager.open_document(code)
            self._lsp_first_sync = True
        else:
            self.lsp_manager.change_document(code)

    def _on_lsp_completions_ready(self, completions: List[Tuple[str, int, str, str]]):
        KIND_MAP = {
            1: 'text', 2: 'method', 3: 'function', 4: 'constructor',
            5: 'field', 6: 'variable', 7: 'class', 8: 'interface',
            9: 'module', 10: 'property', 11: 'unit', 12: 'value',
            13: 'enum', 14: 'keyword', 15: 'snippet', 16: 'color',
            17: 'file', 18: 'reference', 25: 'typeparameter'
        }
        filtered_completions = []
        for label, kind, detail, doc in completions:
            kind_name = KIND_MAP.get(kind, 'unknown')
            # 过滤掉无意义类型
            if kind_name in ('text', 'snippet', 'unit', 'value', 'color', 'file', 'reference'):
                continue
            # 统一变量类
            if kind_name in ('field', 'property', 'variable'):
                kind_name = 'variable'
            # 使用 insertText 或 label
            insert_text = label  # 可扩展为 item.get('insertText', label)
            filtered_completions.append((insert_text, kind_name, doc or '', detail or ''))
        current_prefix = self._get_completion_prefix()
        self._filter_and_show_completions(filtered_completions, current_prefix)

    def _on_lsp_diagnostics_ready(self, diagnostics: List[dict]):
        self._clear_lsp_results()
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
            except Exception as e:
                logger.error(f"[LSP] Error processing diagnostic: {e}")
        if has_error:
            self.sig_flags_changed.emit()  # 触发行号区重绘 + tooltip
        if hasattr(self, 'linenumberarea'):
            self.linenumberarea.update()

    def _clear_lsp_results(self):
        self.clear_extra_selections('lsp_underline')
        block = self.document().firstBlock()
        while block.isValid():
            data = block.userData()
            if data and hasattr(data, 'code_analysis'):
                data.code_analysis = [(s, c, sev, msg) for s, c, sev, msg in data.code_analysis if s != 'lsp']
                if not data.code_analysis:
                    data.color = None
            block = block.next()

    def add_custom_completions(self, words):
        """添加自定义补全"""
        if isinstance(words, str):
            words = [words]
        self.custom_completions.update(words)

    # ========== 补全核心 ==========
    def _request_completions(self):
        if self._completing or not self._lsp_ready:
            return
        cursor = self.textCursor()
        line = cursor.blockNumber()      # 0-based
        col = cursor.columnNumber()      # 0-based
        self.lsp_manager.request_completion(line, col)

    def _filter_and_show_completions(self, completions: List[Tuple[str, str, str, str]], current_prefix: str):
        seen = {name for name, _, _, _ in completions}
        for word in self.custom_completions:
            if word.lower().startswith(current_prefix.lower()) and word not in seen and len(word) >= 2:
                completions.append((word, 'custom', '', ''))
                seen.add(word)
        if not completions:
            self.popup.hide()
            self._popup_timeout_timer.stop()
            return
        # 排序（简化版，可复用原逻辑）
        def sort_key(item):
            name, type_name, _, _ = item
            exact = -1 if name.lower() == current_prefix.lower() else 0
            prefix = -1 if name.lower().startswith(current_prefix.lower()) else 0
            type_priority = {
                'keyword': 900, 'function': 700, 'method': 650, 'class': 600,
                'attribute': 550, 'variable': 500, 'property': 450, 'param': 400,
                'instance': 350, 'module': 300, 'custom': 250, 'builtin': 750,
                'enum': 620, 'unknown': 100
            }
            return (exact, prefix, -type_priority.get(type_name, 0), name.lower())
        completions.sort(key=sort_key)
        completions = completions[:80]
        self.popup.clear()
        for name, type_name, description, detail in completions:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, (name, type_name, description, detail))
            self.popup.addItem(item)
        if self.popup.count() > 0:
            self._show_popup()
            self.popup.setCurrentRow(0)
            self.popup.installEventFilter(self)
            self._popup_timeout_timer.start(self._popup_timeout_duration)
        else:
            self.popup.hide()
            self._popup_timeout_timer.stop()

    def _on_popup_timeout(self):
        """补全框超时回调"""
        if self.popup.isVisible():
            self.popup.hide()

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

    def _show_popup(self):
        cursor_rect = self.cursorRect()
        editor_global_pos = self.mapToGlobal(QtCore.QPoint(0, 0))
        screen_cursor_pos = QtCore.QPoint(
            editor_global_pos.x() + cursor_rect.left(),
            editor_global_pos.y() + cursor_rect.bottom()
        )
        max_width = 500
        for i in range(self.popup.count()):
            item = self.popup.item(i)
            fm = self.popup.fontMetrics()
            text_width = lambda s: fm.boundingRect(0, 0, 10000, 100, 0, s).width() if s else 0
            name = item.text()
            w = text_width(name) + 100
            max_width = max(max_width, w)
        popup_width = min(max_width, self.screen().geometry().width() - 100)
        popup_width = max(popup_width, 500)
        self.popup.setFixedWidth(popup_width)
        x = screen_cursor_pos.x()
        y = screen_cursor_pos.y()
        if x + popup_width > self.screen().geometry().width():
            x = self.screen().geometry().width() - popup_width - 10
        item_height = 40
        visible_items = min(self.popup.count(), 15)
        popup_height = item_height * visible_items + 10
        self.popup.move(x, y)
        self.popup.setFixedHeight(popup_height)
        self.popup.show()
        self.popup.setFocus()

    def _apply_selected_completion(self):
        if not self.popup.currentItem() or self._completing:
            self.popup.hide()
            self._popup_timeout_timer.stop()
            return
        self._completing = True
        try:
            item = self.popup.currentItem()
            data = item.data(Qt.UserRole)
            if data:
                completion, type_name, _, _ = data
            else:
                completion, type_name = item.text(), ""
            cursor = self.textCursor()
            prefix = self._get_completion_prefix()
            if prefix:
                cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(prefix))
            cursor.insertText(completion)
            if type_name in ['function', 'method', 'class', 'builtin']:
                cursor.insertText('()')
                cursor.movePosition(QTextCursor.PreviousCharacter)
            self.setTextCursor(cursor)
        finally:
            self._completing = False
            self.popup.hide()
            self._popup_timeout_timer.stop()

    def _on_completion_selected(self, item):
        self._apply_selected_completion()

    def _on_item_hovered(self, item):
        data = item.data(Qt.UserRole)
        if data:
            _, _, description, _ = data
            if description:
                QToolTip.showText(QCursor.pos(), description)

    # ========== 其他保留功能（parso、折叠、spyder等）==========
    def _on_text_changed_for_parso(self):
        self._parso_timer.stop()
        self._parso_timer.start(800)

    def _run_parso_analysis(self):
        code = self.toPlainText()
        if not code.strip():
            self._clear_parso_results()
            return
        messages = ParsoCodeAnalysis.run_parso_analysis(code)
        self._clear_parso_results()
        self.clear_extra_selections('code_analysis_underline')
        for msg in messages:
            line_number = msg['row']
            col_start = msg['column'] - 1
            message_text = msg['message']
            msg_type = msg['type']
            block = self.document().findBlockByNumber(line_number - 1)
            if block and block.isValid():
                data = block.userData()
                if not data:
                    from spyder.plugins.editor.utils.editor import BlockUserData
                    data = BlockUserData(self)
                    block.setUserData(data)
                severity = 2 if msg_type == 'error' else 1
                data.code_analysis.append(('parso', '', severity, message_text))
                data.color = self.error_color if msg_type == 'error' else self.warning_color
                start_pos = block.position() + col_start
                end_pos = start_pos + 1
                cursor = QTextCursor(self.document())
                cursor.setPosition(start_pos)
                cursor.setPosition(end_pos, QTextCursor.KeepAnchor)
                self.highlight_selection(
                    'code_analysis_underline',
                    cursor,
                    underline_color=QColor(data.color),
                    underline_style=QTextCharFormat.SingleUnderline
                )
        self.sig_flags_changed.emit()
        if hasattr(self, 'linenumberarea'):
            self.linenumberarea.update()

    def _clear_parso_results(self):
        block = self.document().firstBlock()
        while block.isValid():
            data = block.userData()
            if data and hasattr(data, 'code_analysis'):
                data.code_analysis = [(s, c, sev, msg) for s, c, sev, msg in data.code_analysis if s != 'parso']
                if not data.code_analysis:
                    data.color = None
            block = block.next()

    def _on_text_changed_for_folding(self):
        if hasattr(self, '_folding_update_timer'):
            self._folding_update_timer.stop()
        else:
            self._folding_update_timer = QTimer()
            self._folding_update_timer.setSingleShot(True)
            self._folding_update_timer.timeout.connect(self._update_folding_from_code)
        self._folding_update_timer.start(800)

    def _update_folding_from_code(self):
        code = self.toPlainText()
        folding_info = compute_folding_from_ast(code)
        if folding_info:
            self.folding_panel.update_folding(folding_info)
        else:
            self.folding_panel.update_folding(None)

    # --- 按钮、快捷键、事件等（保留原逻辑）---
    def _create_fullscreen_button(self, type="放大"):
        self.fullscreen_button = TransparentToolButton(get_icon(type), parent=self)
        self.fullscreen_button.setIconSize(QSize(28, 28))
        self.fullscreen_button.setFixedSize(28, 28)
        self.fullscreen_button.setToolTip("放大编辑器")

    def _update_button_position(self):
        button_width = 28
        button_spacing = 8
        x = self.width() - button_width - 30
        y_top = 6
        y_bottom = y_top + button_width + button_spacing
        self.fullscreen_button.move(x, y_top)
        self.spyder_button.move(x, y_bottom)

    def _open_in_spyder(self):
        # 保留原逻辑（略，太长）
        pass

    def keyPressEvent(self, event):
        # --- 新增：处理补全弹窗键盘事件 ---
        if self.popup.isVisible():
            key = event.key()
            if key == Qt.Key_Tab or key == Qt.Key_Return:
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
            elif event.text() in '()[]{}.,;:!? ':
                # 输入符号自动关闭
                self.popup.hide()
        # --- 原有逻辑 ---
        super().keyPressEvent(event)
        text = event.text()
        if text == '.' or (text.isalnum() or text == '_'):
            self._request_completions()
        elif event.key() in (Qt.Key_Backspace, Qt.Key_Delete):
            if self._should_show_completion_on_delete():
                self._request_completions()

    def _should_show_completion_on_delete(self):
        cursor = self.textCursor()
        pos = cursor.position()
        if pos <= 0:
            return False
        text = self.toPlainText()
        prev_char = text[pos - 1]
        return prev_char.isalnum() or prev_char == '_' or prev_char == '.'

    def focusOutEvent(self, event):
        self.popup.hide()
        self._popup_timeout_timer.stop()
        QToolTip.hideText()
        super().focusOutEvent(event)

    def __del__(self):
        if self.lsp_manager:
            self.lsp_manager.shutdown()
            self.lsp_manager.wait()

# --- 主窗口（保持不变）---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LSP Code Editor (Jedi Removed)")
        self.setStyleSheet("background-color: #333; color: white;")
        self.resize(800, 600)
        self.find_replace = FindReplace(self, True)
        self.editor = JediCodeEditor()
        example_code = """import os
print(os.getcwd())
def hello():
    x = 10
    return x + 1"""
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