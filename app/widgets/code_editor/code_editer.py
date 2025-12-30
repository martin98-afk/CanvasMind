# -*- coding: utf-8 -*-
import ast

from PyQt5.QtCore import pyqtSignal, QTimer, Qt, QEvent
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QShortcut, QLabel, QInputDialog, QHBoxLayout
from qfluentwidgets import TransparentToolButton
from spyder.widgets.findreplace import FindReplace

from app.templates.component_templates.base import DEFAULT_NODE_TEMPLATE
from app.utils.utils import get_icon  # 假设您有这个工具函数
from app.widgets.basic_widget.style_sheet import StyleSheet
from app.widgets.code_editor.code_editor_lsp import LSPCodeEditor  # 确保导入路径正确
from app.widgets.code_editor.code_editor_jedi import JediCodeEditor


# ---------------- 主部件 ----------------
class CodeEditorWidget(QWidget):
    """

    """
    code_changed = pyqtSignal()
    parsed_component = pyqtSignal(dict)

    def __init__(self, parent=None, python_exe=None, popup_offset=0, editor_type="lsp", default_code=DEFAULT_NODE_TEMPLATE):
        super().__init__(parent)  # 确保父类初始化
        self.default_code = default_code
        self.editor_type = editor_type
        self._suspend_sync_depth = 0  # 初始化，避免在_setup_ui前访问
        self.original_parent = parent  # 保存原始父对象，用于全屏后恢复
        self.fullscreen_mode = False  # 标记是否处于全屏模式
        self.overlay_widget = None  # 用于覆盖全屏的透明层
        self._setup_ui(python_exe, popup_offset)  # 将初始化UI的逻辑移到一个方法中
        self._setup_auto_sync()
        StyleSheet.CODE_EDITOR.apply(self)
        self._setup_shortcuts()

    def _setup_ui(self, python_exe, popup_offset):
        # 5. 创建主要的编辑器视图（包含查找替换面板和编辑器）
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        # 查找替换面板
        self.find_replace = FindReplace(self, True)
        self.find_replace.hide()
        StyleSheet.FIND_REPLACE.apply(self.find_replace)
        self.main_layout.addWidget(self.find_replace)

        # 代码编辑器
        if self.editor_type == "lsp":
            self.code_editor = LSPCodeEditor(self, self.original_parent, python_exe_path=python_exe)
        elif self.editor_type == "jedi":
            self.code_editor = JediCodeEditor(
                self, self.original_parent, python_exe_path=python_exe, popup_offset=popup_offset
            )
        self.code_editor.textChanged.connect(self.code_changed)
        # --- 关键修改：连接内部按钮的点击信号到本类的切换方法 ---
        self.code_editor.fullscreen_button.clicked.connect(self._toggle_fullscreen)
        self.main_layout.addWidget(self.code_editor)
        self.find_replace.set_editor(self.code_editor)
        # 状态栏
        self.status_label = QLabel("Ln 1, Col 1", self)
        self.status_label.setStyleSheet("color:#9aa0a6; padding:2px 6px; background:transparent;")
        self.code_editor.cursorPositionChanged.connect(self._update_status_label)

        # ------- 新增：LSP 服务状态区域（仅在 lsp 模式下） -------
        if self.editor_type == "lsp":
            self.lsp_status_layout = QHBoxLayout()
            self.lsp_status_layout.setContentsMargins(0, 0, 0, 0)
            self.lsp_status_layout.setSpacing(2)

            self.lsp_status_indicator = QLabel("LSP: offline", self)
            self.lsp_status_indicator.setStyleSheet(
                "color:#9aa0a6; padding:2px 6px; background:transparent; font-size:12px; font-weight:bold")

            self.lsp_restart_button = TransparentToolButton(get_icon("更新"), self)
            self.lsp_restart_button.setFixedSize(25, 25)
            self.lsp_restart_button.setToolTip("重启 LSP 服务")
            self.lsp_restart_button.clicked.connect(
                lambda: self.code_editor.set_completion_environment(
                    self.original_parent.package_manager.get_current_python_exe()
                )
            )

            self.lsp_status_layout.addWidget(self.status_label)
            self.lsp_status_layout.addStretch()
            self.lsp_status_layout.addWidget(self.lsp_status_indicator)
            self.lsp_status_layout.addWidget(self.lsp_restart_button)

            # 将 LSP 状态布局放入一个容器 widget，便于添加到主布局
            self.lsp_status_widget = QWidget(self)
            self.lsp_status_widget.setLayout(self.lsp_status_layout)
            self.lsp_status_widget.setStyleSheet("background: transparent;")
            self.main_layout.addWidget(self.lsp_status_widget)
            self.code_editor.lsp_signal.connect(self._update_lsp_status)
            self.code_editor.set_completion_environment(python_exe)
        else:
            self.lsp_status_widget = None
            self.lsp_status_indicator = None
            self.lsp_restart_button = None
            self.main_layout.addWidget(self.status_label)

        self.code_editor.cursorPositionChanged.connect(self._update_status_label)
        # 7. 设置初始代码
        self.replace_text_preserving_view(self.default_code)

    def _update_lsp_status(self, status: str):
        """更新 LSP 状态显示"""
        if not self.lsp_status_indicator:
            return
        if status == "ready":
            self.lsp_status_indicator.setText("LSP: ready")
            self.lsp_status_indicator.setStyleSheet(
                "color:#4caf50; padding:2px 6px; background:transparent; font-size:12px;")
        elif status == "starting":
            self.lsp_status_indicator.setText("LSP: starting...")
            self.lsp_status_indicator.setStyleSheet(
                "color:#ff9800; padding:2px 6px; background:transparent; font-size:12px;")
        elif status == "restarting...":
            self.lsp_status_indicator.setText("LSP: restarting...")
            self.lsp_status_indicator.setStyleSheet(
                "color:#ff9800; padding:2px 6px; background:transparent; font-size:12px;")
        else:  # offline / error
            self.lsp_status_indicator.setText("LSP: offline")
            self.lsp_status_indicator.setStyleSheet(
                "color:#f44336; padding:2px 6px; background:transparent; font-size:12px;")

    def _setup_auto_sync(self):
        self._sync_timer = QTimer()
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._parse_and_sync)

    def _setup_shortcuts(self):
        QShortcut(Qt.Key_F3, self.code_editor, activated=lambda: self._find_next(backward=False))
        QShortcut(Qt.SHIFT + Qt.Key_F3, self.code_editor, activated=lambda: self._find_next(backward=True))
        QShortcut(Qt.CTRL + Qt.Key_G, self.code_editor, activated=self._goto_line)
        QShortcut(Qt.CTRL + Qt.Key_D, self.code_editor, activated=self._duplicate_line)

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
        old_text = self.get_code()
        if new_text == old_text:
            return

        # ✅ 1. 保存滚动位置和光标位置（仅用 selection）
        scrollbar = self.code_editor.verticalScrollBar()
        scroll_pos = scrollbar.value()

        cursor = self.code_editor.textCursor()
        sel_start = cursor.selectionStart()
        sel_end = cursor.selectionEnd()
        is_selection = sel_start != sel_end

        # ✅ 2. 阻断信号，替换全文
        self.code_editor.blockSignals(True)
        try:
            # 使用 setPlainText（最可靠的方式替换全文）
            self.code_editor.setPlainText(new_text.replace('\r\n', '\n').replace('\r', '\n'))
        finally:
            self.code_editor.blockSignals(False)

        # ✅ 3. 严格限制位置在新文本范围内
        new_len = len(new_text)
        new_start = max(0, min(sel_start, new_len))
        new_end = max(0, min(sel_end, new_len))

        # ✅ 4. 设置新光标
        new_cursor = self.code_editor.textCursor()
        if is_selection:
            new_cursor.setPosition(new_start)
            new_cursor.setPosition(new_end, QTextCursor.KeepAnchor)
        else:
            new_cursor.setPosition(new_start)  # 单点光标
        self.code_editor.setTextCursor(new_cursor)

        # ✅ 5. 恢复滚动
        scrollbar.setValue(scroll_pos)

        # lsp 文档同步
        if hasattr(self.code_editor, '_lsp_ready') and self.code_editor._lsp_ready:
            # 构造带 CODE_PREFIX 的新内容
            code_for_lsp = self.code_editor._get_code_with_prefix()
            # 重置 LSP 文档：先关闭再打开（最可靠）
            self.code_editor.lsp_session.close_document()
            self.code_editor.lsp_session.open_document(code_for_lsp)  # ← 使用全量替换
            # 更新本地记录，确保下次增量更新正确
            self.code_editor._last_lsp_content = code_for_lsp
            self.code_editor._lsp_document_opened = True
            # 重新请求折叠（可选）
            self.code_editor._request_folding()

        # ✅ 6. 手动触发 textChanged（如果需要）
        self.code_editor.textChanged.emit()

    def _toggle_find_panel(self, focus_replace=False):
        """切换查找替换面板的可见性"""
        visible = self.find_replace.isVisible()
        if visible:
            self.find_replace.setVisible(False)
        else:
            self.find_replace.setVisible(True)
            if focus_replace:
                self.find_replace.replace_widget.setFocus()
            else:
                self.find_replace.search_widget.setFocus()

    # ===== 修改：全屏/缩小功能 (基于覆盖层) =====
    def _toggle_fullscreen(self):
        """切换全屏模式"""
        if not self.fullscreen_mode:
            self._enter_fullscreen()
        else:
            self._exit_fullscreen()

    def _create_fullscreen_container(self):
        """创建全屏容器，包含查找替换面板、代码编辑器和状态栏"""
        container = QWidget()
        layout = QVBoxLayout(container)
        # 深色半透明背景
        container.setStyleSheet("background-color: rgba(0, 0, 0, 200);")
        layout.setContentsMargins(0, 0, 0, 0)

        # 添加查找替换面板
        layout.addWidget(self.find_replace)
        # 添加代码编辑器
        layout.addWidget(self.code_editor)
        # 添加状态栏
        layout.addWidget(self.status_label)

        return container

    def _enter_fullscreen(self):
        """进入全屏模式 (覆盖层方式)"""
        if self.fullscreen_mode:
            return  # 已经是全屏状态

        # 保存当前的大小信息，用于退出全屏后恢复
        self._original_size = self.size()
        self._original_main_view_size = self.size()

        # 保存当前的可见性状态
        self._find_replace_visible = self.find_replace.isVisible()
        self._status_label_visible = self.status_label.isVisible()

        # 1. 获取 FluentWindow 的顶层容器 (通常是 centralwidget 或直接是 window)
        window_parent = self.original_parent
        if not window_parent:
            print("Error: Cannot enter fullscreen, no original parent window found.")
            return

        # 2. 创建或获取覆盖层
        if self.overlay_widget is None:
            self.overlay_widget = QWidget(window_parent)
            # 确保覆盖层在最顶层
            self.overlay_widget.raise_()
            # 为覆盖层添加 ESC 退出事件
            self.overlay_widget.installEventFilter(self)

        # 3. 调整覆盖层大小以匹配窗口内容区域
        self.overlay_widget.resize(window_parent.size())
        self.overlay_widget.move(0, 0)  # 相对于其父窗口 (FluentWindow)
        self.overlay_widget.show()

        # 4. 创建全屏容器（包含查找替换面板、代码编辑器和状态栏）
        fullscreen_container = self._create_fullscreen_container()

        # 5. 将全屏容器设置为覆盖层的子控件
        fullscreen_container.setParent(self.overlay_widget)

        # 6. 调整全屏容器大小以填满覆盖层
        fullscreen_container.resize(self.overlay_widget.size())
        fullscreen_container.move(0, 0)  # 相对于其父控件 (overlay_widget)

        # 7. 确保全屏容器显示
        fullscreen_container.show()

        # 8. 更新按钮图标和状态 (通过修改JediCodeEditor内部的按钮)
        # 假设 get_icon("缩小") 返回缩小图标的QIcon
        if hasattr(self.code_editor, 'fullscreen_button') and self.code_editor.fullscreen_button:
            self.code_editor.fullscreen_button.setIcon(get_icon("缩小"))
            self.code_editor.fullscreen_button.setToolTip("缩小编辑器")

        self.fullscreen_mode = True
        # 保存全屏容器的引用，用于退出全屏时使用
        self._current_fullscreen_container = fullscreen_container

    def _exit_fullscreen(self):
        """退出全屏模式 (覆盖层方式)"""
        if not self.fullscreen_mode:
            return  # 不是全屏状态

        # 1. 停止监听覆盖层事件
        if self.overlay_widget:
            self.overlay_widget.removeEventFilter(self)

        # 2. 获取当前全屏容器
        fullscreen_container = getattr(self, '_current_fullscreen_container', None)
        if fullscreen_container:
            # 从覆盖层移除，但不删除，因为要重新添加到原布局
            fullscreen_container.setParent(None)
            fullscreen_container.hide()

        # 3. 重新将组件添加到原布局
        main_layout = self.layout()

        # 清空原布局中的内容
        for i in reversed(range(main_layout.count())):
            item = main_layout.itemAt(i)
            if item and item.widget():
                # 不实际移除组件，只是清理布局项
                pass

        # 重新添加组件到原布局
        main_layout.addWidget(self.find_replace)
        main_layout.addWidget(self.code_editor)
        main_layout.addWidget(self.status_label)

        # 恢复可见性状态
        self.find_replace.setVisible(getattr(self, '_find_replace_visible', True))
        self.status_label.setVisible(getattr(self, '_status_label_visible', True))

        # 4. 隐藏覆盖层
        if self.overlay_widget:
            self.overlay_widget.hide()

        # 5. 清除全屏容器引用
        if hasattr(self, '_current_fullscreen_container'):
            delattr(self, '_current_fullscreen_container')

        # 6. 恢复原来的大小（如果保存了的话）
        if hasattr(self, '_original_size'):
            self.resize(self._original_size)
        if hasattr(self, '_original_main_view_size'):
            self.resize(self._original_main_view_size)

        # 7. 重新设置编辑器的查找替换组件
        self.find_replace.set_editor(self.code_editor)

        # 8. 更新按钮图标和状态 (通过修改JediCodeEditor内部的按钮)
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
                    return True  # 拦截事件
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
                self.overlay_widget.move(0, 0)

                # --- 关键修改：同步调整全屏容器大小 ---
                fullscreen_container = getattr(self, '_current_fullscreen_container', None)
                if fullscreen_container:
                    fullscreen_container.resize(self.overlay_widget.size())
                    fullscreen_container.move(0, 0)  # 确保全屏容器位置正确