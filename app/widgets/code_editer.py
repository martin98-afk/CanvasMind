# -*- coding: utf-8 -*-
import ast
import re

from PyQt5.QtCore import pyqtSignal, QTimer, Qt, QEvent
from PyQt5.QtGui import QTextCursor, QColor, QTextCharFormat
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QShortcut, QHBoxLayout, \
    QLineEdit, QPushButton, QCheckBox, QLabel, QInputDialog
from app.utils.utils import get_icon # 假设您有这个工具函数

from app.widgets.code_editor_spyder import JediCodeEditor # 确保导入路径正确

DEFAULT_CODE_TEMPLATE = '''class Component(BaseComponent):
    name = ""
    category = ""
    description = ""
    requirements = ""
    inputs = [
    ]
    outputs = [
    ]
    properties = {
    }
    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        # 在这里编写你的组件逻辑
        input_data = inputs.get("input_data") if inputs else None
        param1 = params.get("param1", "default_value")
        # 处理逻辑
        result = f"处理结果: {input_data} + {param1}"
        return {
            "output_data": result
        }
        

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.run(
        params={"param1": "test"},
        inputs={"input_data": "output"}
    )
    print(result)
'''


# ---------------- 主部件 ----------------
class CodeEditorWidget(QWidget):
    code_changed = pyqtSignal()
    parsed_component = pyqtSignal(dict)

    def __init__(self, parent=None, python_exe=None, popup_offset=0, default_code=DEFAULT_CODE_TEMPLATE):
        super().__init__(parent) # 确保父类初始化
        self.default_code = default_code
        self._suspend_sync_depth = 0 # 初始化，避免在_setup_ui前访问
        self.original_parent = parent # 保存原始父对象，用于全屏后恢复
        self.fullscreen_mode = False # 标记是否处于全屏模式
        self.overlay_widget = None # 用于覆盖全屏的透明层
        self._setup_ui(python_exe, popup_offset) # 将初始化UI的逻辑移到一个方法中
        self._setup_auto_sync()
        # self._setup_syntax_highlighting()
        self._setup_shortcuts()

    def _setup_ui(self, python_exe, popup_offset):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 5. 创建主要的编辑器视图（包含查找替换面板和编辑器）
        self.main_view = QWidget()
        main_layout = QVBoxLayout(self.main_view)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 查找替换面板
        self.find_panel = self._create_find_replace_panel()
        self.find_panel.setVisible(False)
        main_layout.addWidget(self.find_panel)

        # 代码编辑器
        self.code_editor = JediCodeEditor(self, self, python_exe_path=python_exe, popup_offset=popup_offset)
        self.code_editor.textChanged.connect(self.code_changed)
        # --- 关键修改：连接内部按钮的点击信号到本类的切换方法 ---
        self.code_editor.fullscreen_button.clicked.connect(self._toggle_fullscreen)
        main_layout.addWidget(self.code_editor)

        # 状态栏
        self.status_label = QLabel("Ln 1, Col 1", self.main_view)
        self.status_label.setStyleSheet("color:#9aa0a6; padding:3px 6px; background:transparent;")
        main_layout.addWidget(self.status_label)
        self.code_editor.cursorPositionChanged.connect(self._update_status_label)

        # 6. 将主视图添加到主布局
        layout.addWidget(self.main_view)

        # 7. 设置初始代码
        self.replace_text_preserving_view(self.default_code)

    def _setup_auto_sync(self):
        self._sync_timer = QTimer()
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._parse_and_sync)

    def _setup_shortcuts(self):
        QShortcut(Qt.CTRL + Qt.Key_F, self.code_editor, activated=self._toggle_find_panel)
        QShortcut(Qt.Key_F3, self.code_editor, activated=lambda: self._find_next(backward=False))
        QShortcut(Qt.SHIFT + Qt.Key_F3, self.code_editor, activated=lambda: self._find_next(backward=True))
        QShortcut(Qt.CTRL + Qt.Key_H, self.code_editor, activated=lambda: self._toggle_find_panel(focus_replace=True))
        QShortcut(Qt.CTRL + Qt.Key_G, self.code_editor, activated=self._goto_line)
        QShortcut(Qt.CTRL + Qt.Key_Slash, self.code_editor, activated=self._toggle_comment)
        QShortcut(Qt.CTRL + Qt.Key_D, self.code_editor, activated=self._duplicate_line)

    def _create_find_replace_panel(self):
        panel = QWidget(self)
        h = QHBoxLayout(panel)
        h.setContentsMargins(6, 6, 6, 6)
        self.find_input = QLineEdit(panel)
        self.find_input.setPlaceholderText("Find")
        self.chk_regex = QCheckBox("Regex", panel)
        self.chk_case = QCheckBox("Aa", panel)
        btn_prev = QPushButton("Prev", panel)
        btn_next = QPushButton("Next", panel)
        self.replace_input = QLineEdit(panel)
        self.replace_input.setPlaceholderText("Replace")
        btn_replace = QPushButton("Replace", panel)
        btn_replace_all = QPushButton("All", panel)
        self.lbl_hits = QLabel("", panel)
        h.addWidget(self.find_input)
        h.addWidget(self.chk_regex)
        h.addWidget(self.chk_case)
        h.addWidget(btn_prev)
        h.addWidget(btn_next)
        h.addSpacing(12)
        h.addWidget(self.replace_input)
        h.addWidget(btn_replace)
        h.addWidget(btn_replace_all)
        h.addSpacing(12)
        h.addWidget(self.lbl_hits)
        btn_prev.clicked.connect(lambda: self._find_next(backward=True))
        btn_next.clicked.connect(lambda: self._find_next(backward=False))
        btn_replace.clicked.connect(self._replace_once)
        btn_replace_all.clicked.connect(self._replace_all)
        self.find_input.textChanged.connect(self._update_find_highlight)
        self.find_input.returnPressed.connect(lambda: self._find_next(backward=False))
        self.replace_input.returnPressed.connect(self._replace_once)
        panel.setStyleSheet("""
            QWidget { background: #202124; }
            QLineEdit { background:#2b2d30; color:#e8eaed; border:1px solid #3c4043; padding:3px 6px; }
            QLabel { color:#9aa06; }
            QCheckBox { color:#c0c4c9; }
            QPushButton { background:#303134; color:#e8eaed; border:1px solid #3c4043; padding:3px 6px; }
            QPushButton:hover { background:#3a3b3e; }
        """)
        return panel

    # ===== Find/Replace =====
    def _toggle_find_panel(self, focus_replace=False):
        self.find_panel.setVisible(not self.find_panel.isVisible())
        if self.find_panel.isVisible():
            sel = self.code_editor.textCursor().selectedText().replace('\u2029', '\n')
            if sel and '\n' not in sel:
                self.find_input.setText(sel)
            (self.replace_input if focus_replace else self.find_input).setFocus()

    def _find_next(self, backward=False):
        pat = self._pattern()
        if not pat:
            return
        doc_text = self.get_code()
        cursor = self.code_editor.textCursor()
        pos = cursor.position()
        self._highlight_all_matches(pat, doc_text)
        if backward:
            hay = doc_text[:pos]
            matches = list(pat.finditer(hay))
            if not matches:
                return
            m = matches[-1]
        else:
            m = pat.search(doc_text, pos)
            if not m:
                m = pat.search(doc_text, 0)
                if not m:
                    return
        start, end = m.start(), m.end()
        self._set_selection(start, end)
        self._update_hits_count(pat, doc_text)

    def _pattern(self):
        text = self.find_input.text()
        if not text:
            return None
        flags = 0 if self.chk_case.isChecked() else re.IGNORECASE
        try:
            if self.chk_regex.isChecked():
                return re.compile(text, flags)
            return re.compile(re.escape(text), flags)
        except re.error:
            return None

    def _replace_all_text(self, new_text):
        scrollbar = self.code_editor.verticalScrollBar()
        scroll_pos = scrollbar.value()
        tc = self.code_editor.textCursor()
        sel_start = tc.selectionStart()
        sel_end = tc.selectionEnd()
        tc.beginEditBlock()
        tc.select(QTextCursor.Document)
        tc.insertText(new_text)
        tc.endEditBlock()
        self.code_editor.setTextCursor(tc)
        if sel_start != sel_end:
            tc.setPosition(max(0, min(sel_start, len(new_text))))
            tc.setPosition(max(0, min(sel_end, len(new_text))), QTextCursor.KeepAnchor)
            self.code_editor.setTextCursor(tc)
        scrollbar.setValue(scroll_pos)

    def _highlight_all_matches(self, pat, text):
        try:
            extras = [e for e in self.code_editor.extraSelections() if getattr(e, 'searchHighlight', False) is False]
        except Exception:
            extras = []
        fmt = QTextCharFormat()
        fmt.setBackground(QColor('#3949ab'))
        fmt.setForeground(QColor('#ffffff'))
        for m in pat.finditer(text):
            cur = self.code_editor.textCursor()
            cur.setPosition(m.start())
            cur.setPosition(m.end(), QTextCursor.KeepAnchor)
            ex = QTextEdit.ExtraSelection()
            ex.format = fmt
            ex.cursor = cur
            ex.searchHighlight = True
            extras.append(ex)
        self.code_editor.setExtraSelections(extras)

    def _set_selection(self, start, end):
        cursor = self.code_editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        self.code_editor.setTextCursor(cursor)
        self.code_editor.centerCursor()

    def _update_hits_count(self, pat, text):
        try:
            count = len(list(pat.finditer(text)))
        except Exception:
            count = 0
        self.lbl_hits.setText(f"{count} hits")

    def _update_find_highlight(self):
        pat = self._pattern()
        if not pat:
            self.lbl_hits.setText("")
            return
        self._update_hits_count(pat, self.get_code())

    def _replace_once(self):
        sel = self.code_editor.textCursor().selectedText().replace('\u2029', '\n')
        pat = self._pattern()
        if not pat:
            return
        replacement = self.replace_input.text()
        if sel:
            try:
                new_text = pat.sub(replacement, sel, count=1)
            except Exception:
                return
            self.code_editor.textCursor().insertText(new_text)
            return
        self._find_next(backward=False)

    def _replace_all(self):
        pat = self._pattern()
        if not pat:
            return
        replacement = self.replace_input.text()
        text = self.get_code()
        try:
            new_text, n = pat.subn(replacement, text)
        except Exception:
            return
        if n > 0:
            self.replace_text_preserving_view(new_text)
            self.lbl_hits.setText(f"{n} replaced")

    def _toggle_comment(self):
        cursor = self.code_editor.textCursor()
        doc = self.code_editor.document()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        c = QTextCursor(doc)
        c.setPosition(start)
        c.movePosition(QTextCursor.StartOfLine)
        start_line_pos = c.position()
        c.setPosition(end)
        if c.atBlockStart() and end > start:
            c.movePosition(QTextCursor.Left)
        c.movePosition(QTextCursor.EndOfLine)
        end_line_pos = c.position()
        c.setPosition(start_line_pos)
        c.setPosition(end_line_pos, QTextCursor.KeepAnchor)
        lines = c.selectedText().split('\u2029')

        def is_commented(s):
            return bool(re.match(r"^\s*#", s))

        all_commented = all((t.strip() == '' or is_commented(t)) for t in lines)
        new_lines = []
        if all_commented:
            for t in lines:
                if not t.strip():
                    new_lines.append(t)
                    continue
                new_lines.append(re.sub(r"^(\s*)#\s?", r"\1", t))
        else:
            for t in lines:
                if not t.strip():
                    new_lines.append(t)
                else:
                    m = re.match(r"^(\s*)", t)
                    indent = m.group(1) if m else ''
                    new_lines.append(f"{indent}# " + t[len(indent):])
        cursor.beginEditBlock()
        c.insertText("\n".join(new_lines))
        cursor.endEditBlock()

    def _duplicate_line(self):
        cursor = self.code_editor.textCursor()
        cursor.select(QTextCursor.LineUnderCursor)
        line = cursor.selectedText().replace('\u2029', '')
        cursor.movePosition(QTextCursor.EndOfLine)
        cursor.insertText('\n' + line)

    def _on_text_changed(self):
        self.code_changed.emit()
        self._sync_timer.start(800)

    def _parse_and_sync(self):
        try:
            code = self.code_editor.toPlainText()
            if not code.strip():
                return
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == "Component":
                    self._parse_component_class(node, code)
                    break
        except SyntaxError:
            pass
        except Exception as e:
            print(f"解析代码失败: {e}")

    def _parse_component_class(self, class_node, code):
        component_info = {"name": "", "category": "", "description": ""}
        for stmt in class_node.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target = stmt.targets[0]
                if isinstance(target, ast.Name) and isinstance(stmt.value, ast.Str):
                    if target.id in component_info:
                        component_info[target.id] = stmt.value.s
        self.parsed_component.emit(component_info)

    def _update_status_label(self):
        cur = self.code_editor.textCursor()
        ln = cur.blockNumber() + 1
        col = cur.positionInBlock() + 1
        self.status_label.setText(f"Ln {ln}, Col {col}")

    def _goto_line(self):
        cur = self.code_editor.textCursor()
        ln = cur.blockNumber() + 1
        num, ok = QInputDialog.getInt(self, "Go to Line", "Line number:", ln, 1, 10 ** 9, 1)
        if not ok:
            return
        cursor = self.code_editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        if num > 1:
            cursor.movePosition(QTextCursor.Down, n=num - 1)
        self.code_editor.setTextCursor(cursor)
        self.code_editor.centerCursor()

    def get_code(self):
        return self.code_editor.toPlainText().replace('\r\n', '\n').replace('\r', '\n')

    def set_code(self, code):
        self.replace_text_preserving_view(code)

    def suspend_sync(self):
        self._suspend_sync_depth += 1

    def resume_sync(self):
        if self._suspend_sync_depth > 0:
            self._suspend_sync_depth -= 1

    def replace_text_preserving_view(self, new_text: str):
        doc_text = self.get_code()
        if new_text == doc_text:
            return
        scrollbar = self.code_editor.verticalScrollBar()
        scroll_pos = scrollbar.value()
        cursor = self.code_editor.textCursor()
        sel_start = cursor.selectionStart()
        sel_end = cursor.selectionEnd()
        self.code_editor.blockSignals(True)
        cursor.beginEditBlock()
        cursor.select(QTextCursor.Document)
        cursor.insertText(new_text.replace('\r\n', '\n').replace('\r', '\n'))
        cursor.endEditBlock()
        self.code_editor.blockSignals(False)
        c = self.code_editor.textCursor()
        if sel_start != sel_end:
            c.setPosition(max(0, min(sel_start, len(new_text))))
            c.setPosition(max(0, min(sel_end, len(new_text))), QTextCursor.KeepAnchor)
        else:
            c.setPosition(max(0, min(cursor.position(), len(new_text))))
        self.code_editor.setTextCursor(c)
        scrollbar.setValue(scroll_pos)

    # ===== 新增：全屏/缩小功能 (基于覆盖层) =====
    def _toggle_fullscreen(self):
        """切换全屏模式"""
        if not self.fullscreen_mode:
            self._enter_fullscreen()
        else:
            self._exit_fullscreen()

    def _enter_fullscreen(self):
        """进入全屏模式 (覆盖层方式)"""
        if self.fullscreen_mode:
            return # 已经是全屏状态

        # 1. 获取 FluentWindow 的顶层容器 (通常是 centralwidget 或直接是 window)
        #    这里假设 self.original_parent 是 FluentWindow 实例
        window_parent = self.original_parent
        if not window_parent:
            print("Error: Cannot enter fullscreen, no original parent window found.")
            return

        # 2. 创建或获取覆盖层
        if self.overlay_widget is None:
            self.overlay_widget = QWidget(window_parent)
            self.overlay_widget.setStyleSheet("background-color: rgba(0, 0, 0, 180);") # 半透明黑色背景
            # 确保覆盖层在最顶层
            self.overlay_widget.raise_()
            # 可选：为覆盖层添加 ESC 退出事件
            self.overlay_widget.installEventFilter(self)

        # 3. 调整覆盖层大小以匹配窗口内容区域
        self.overlay_widget.resize(window_parent.size())
        self.overlay_widget.move(0, 0) # 相对于其父窗口 (FluentWindow)
        self.overlay_widget.show()

        # 4. 将编辑器设置为覆盖层的子控件
        self.code_editor.setParent(self.overlay_widget)

        # 5. 调整编辑器大小以填满覆盖层
        self.code_editor.resize(self.overlay_widget.size())
        self.code_editor.move(0, 0) # 相对于其父控件 (overlay_widget)
        self.code_editor.show() # 确保显示

        # 6. 更新按钮图标和状态 (通过修改JediCodeEditor内部的按钮)
        # 假设 get_icon("缩小") 返回缩小图标的QIcon
        if hasattr(self.code_editor, 'fullscreen_button') and self.code_editor.fullscreen_button:
            self.code_editor.fullscreen_button.setIcon(get_icon("缩小"))
            self.code_editor.fullscreen_button.setToolTip("缩小编辑器")

        self.fullscreen_mode = True

    def _exit_fullscreen(self):
        """退出全屏模式 (覆盖层方式)"""
        if not self.fullscreen_mode:
            return # 不是全屏状态

        # 1. 停止监听覆盖层事件
        if self.overlay_widget:
            self.overlay_widget.removeEventFilter(self)

        # 2. 将编辑器移回主界面布局
        self.code_editor.setParent(self.main_view) # 重新设置父对象为 main_view
        # 重新布局（假设编辑器在 main_layout 的索引是 1，查找面板之后）
        main_layout = self.main_view.layout()
        if main_layout and self.code_editor not in [main_layout.itemAt(i).widget() for i in range(main_layout.count())]:
            main_layout.insertWidget(1, self.code_editor) # 插入到查找面板之后，状态栏之前

        # 3. 隐藏覆盖层
        if self.overlay_widget:
            self.overlay_widget.hide()

        # 4. 更新按钮图标和状态 (通过修改JediCodeEditor内部的按钮)
        if hasattr(self.code_editor, 'fullscreen_button') and self.code_editor.fullscreen_button:
            self.code_editor.fullscreen_button.setIcon(get_icon("放大"))
            self.code_editor.fullscreen_button.setToolTip("放大编辑器")

        self.fullscreen_mode = False

    def eventFilter(self, obj, event):
        """事件过滤器，用于处理覆盖层上的 ESC 键退出"""
        # 检查是否是覆盖层，并且处于全屏模式
        if obj == self.overlay_widget and self.fullscreen_mode:
            # 检查事件类型是否为键盘按下事件
            if event.type() == QEvent.KeyPress:
                # 检查是否是ESC键
                if event.key() == Qt.Key_Escape:
                    self._exit_fullscreen()
                    return True # 拦截事件
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        """重写调整大小事件，确保覆盖层跟随窗口大小变化"""
        super().resizeEvent(event)
        # 如果处于全屏模式，调整覆盖层大小
        if self.fullscreen_mode and self.overlay_widget:
            # 获取 FluentWindow 的顶层容器
            window_parent = self.original_parent
            if window_parent:
                self.overlay_widget.resize(window_parent.size())
                # 注意：如果 FluentWindow 有菜单栏、工具栏等，可能需要调整 y 坐标
                # 例如， self.overlay_widget.move(0, top_offset)
                # 但通常 resizeEvent 会跟随整个窗口，所以 move(0, 0) 通常是合适的
                self.overlay_widget.move(0, 0)

                # --- 关键修改：同步调整编辑器大小 ---
                # 当覆盖层大小改变时，确保编辑器也跟随调整
                self.code_editor.resize(self.overlay_widget.size())
                self.code_editor.move(0, 0) # 确保编辑器位置正确

