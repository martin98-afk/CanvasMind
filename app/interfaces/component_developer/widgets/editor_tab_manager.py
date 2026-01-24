# -*- coding: utf-8 -*-
import os
from pathlib import Path

from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QLabel, QScrollArea, QWidget, QHBoxLayout

# 引入 InfoBar 用于保存成功的提示
from qfluentwidgets import (FluentIcon, TabCloseButtonDisplayMode, TabWidget,
                            TransparentToolButton, TransparentDropDownToolButton,
                            RoundMenu, Action, InfoBar, InfoBarPosition)

from app.templates.component_templates import DEFAULT_NODE_TEMPLATE, default_templates
from app.utils.utils import get_icon
from app.widgets.code_editor.code_editer import CodeEditorWidget


class ComponentTabManager(TabWidget):
    """
    组件编辑器Tab管理
    """

    # 定义信号
    runSignal = pyqtSignal()
    saveSignal = pyqtSignal()  # 注意：只有在主Tab时才会触发此信号
    cancelSignal = pyqtSignal()
    templateChangedSignal = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabsClosable(True)
        self._parent_ref = parent
        self._opened_files = {}

        # ==================== 布局重构区域 ====================
        self.tabBar.setAddButtonVisible(False)
        self.vBoxLayout.removeWidget(self.tabBar)

        self.top_bar_container = QWidget()
        self.top_bar_layout = QHBoxLayout(self.top_bar_container)
        self.top_bar_layout.setContentsMargins(5, 0, 5, 0)
        self.top_bar_layout.setSpacing(4)

        self._init_left_corner()
        self.top_bar_layout.addWidget(self.template_btn)

        self.top_bar_layout.addWidget(self.tabBar, 1)

        self._init_right_corner()
        self.top_bar_layout.addWidget(self.right_container)

        self.vBoxLayout.insertWidget(0, self.top_bar_container)
        # ====================================================

        self.tabCloseRequested.connect(self._handle_close_request)

    def _init_left_corner(self):
        """左侧：模板选择按钮"""
        self.template_btn = TransparentDropDownToolButton(FluentIcon.ALIGNMENT, self)
        self.template_btn.setToolTip("选择代码模板")
        self.template_btn.setFixedSize(36, 36)
        self.template_btn.setIconSize(QSize(16, 16))

        menu = RoundMenu(parent=self)
        for template_name, code_content in default_templates.items():
            action = Action(template_name, parent=menu)
            action.triggered.connect(
                lambda checked=False, n=template_name, c=code_content:
                self.templateChangedSignal.emit(n, c)
            )
            menu.addAction(action)
        self.template_btn.setMenu(menu)

    def _init_right_corner(self):
        """右侧：功能按钮组"""
        self.right_container = QWidget()
        layout = QHBoxLayout(self.right_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 运行
        self.run_btn = TransparentToolButton(FluentIcon.PLAY, self)
        self.run_btn.setToolTip("运行 (Ctrl+R)")
        self.run_btn.setFixedSize(36, 36)
        self.run_btn.clicked.connect(self.runSignal.emit)

        # 保存 【优化点：绑定到内部处理函数，而不是直接emit】
        self.save_btn = TransparentToolButton(FluentIcon.SAVE, self)
        self.save_btn.setToolTip("保存 (Ctrl+S)")
        self.save_btn.setFixedSize(36, 36)
        self.save_btn.clicked.connect(self._on_save_clicked)

        # 关闭
        self.cancel_btn = TransparentToolButton(FluentIcon.CLOSE, self)
        self.cancel_btn.setToolTip("关闭编辑器")
        self.cancel_btn.setFixedSize(36, 36)
        self.cancel_btn.clicked.connect(self.cancelSignal.emit)

        layout.addWidget(self.run_btn)
        layout.addWidget(self.save_btn)
        layout.addWidget(self.cancel_btn)

    def _on_save_clicked(self):
        """处理保存按钮点击逻辑"""
        index = self.currentIndex()

        if index == 0:
            # === 情况1：主 Tab ===
            # 将事件交给上层处理（通常是保存整个组件结构）
            self.saveSignal.emit()
        else:
            # === 情况2：其他文件 Tab ===
            # 直接在内部保存文件
            self._save_current_file_tab()

    def _save_current_file_tab(self):
        """保存当前打开的文件Tab"""
        widget = self.currentWidget()

        # 1. 检查是否有文件路径属性
        if not hasattr(widget, 'property_file_path'):
            return

        file_path = widget.property_file_path

        # 2. 获取内容 (针对 CodeEditorWidget)
        content = None
        if hasattr(widget, 'get_code'):
            content = widget.get_code()
        # 如果未来支持文本编辑器等其他控件，可在此扩展 elif hasattr(widget, 'toPlainText'): ...

        if content is None:
            # 如果是图片预览(Image Viewer)等没有文本内容的控件，直接忽略
            return

        # 3. 写入文件
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            # 4. 弹出成功提示
            InfoBar.success(
                title='保存成功',
                content=f"已保存文件：{os.path.basename(file_path)}",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )
        except Exception as e:
            # 弹出错误提示
            InfoBar.error(
                title='保存失败',
                content=str(e),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

    def init_main_editor(self, widget, name):
        """初始化默认的、不可关闭的主代码编辑器"""
        self.insertTab(0, widget, "组件代码", get_icon("代码执行"), routeKey="main_entry_point")
        self.main_code_editor = widget  # 记录引用，方便后续操作

        if self.tabBar.count() > 0:
            item = self.tabBar.tabItem(0)
            if item:
                item.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.NEVER)

    def set_template_code(self, code):
        """外部调用或信号触发：修改主编辑器的代码"""
        if hasattr(self, 'main_code_editor') and self.main_code_editor:
            self.main_code_editor.set_code(code)

    def open_file(self, file_path, ui_setup=None):
        file_path = str(Path(file_path).resolve())

        if file_path in self._opened_files:
            route_key = self._opened_files[file_path]
            for i in range(self.count()):
                if self.tabBar.tabItem(i).routeKey() == route_key:
                    self.setCurrentIndex(i)
                    return

        file_name = os.path.basename(file_path)
        ext = os.path.splitext(file_name)[1].lower()

        if ext in ['.png', '.jpg', '.jpeg', '.bmp', '.svg', '.ico']:
            widget = self._create_image_viewer(file_path)
            icon = FluentIcon.PHOTO
        else:
            py_exe = "python"
            if ui_setup and hasattr(ui_setup.parent, 'package_manager'):
                py_exe = ui_setup.parent.package_manager.get_current_python_exe()
            widget = self._create_code_editor(file_path, py_exe)
            icon = FluentIcon.DOCUMENT

        route_key = file_path
        self.addTab(widget, file_name, icon, routeKey=route_key)
        self._opened_files[file_path] = route_key
        self.setCurrentWidget(widget)

    def _create_image_viewer(self, path):
        viewer = QScrollArea()
        label = QLabel()
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            if pixmap.width() > 1000:
                pixmap = pixmap.scaledToWidth(1000, Qt.SmoothTransformation)
            label.setPixmap(pixmap)
        label.setAlignment(Qt.AlignCenter)
        viewer.setWidget(label)
        viewer.setWidgetResizable(True)
        viewer.property_file_path = path
        return viewer

    def _create_code_editor(self, path, python_exe):
        editor = CodeEditorWidget(None, python_exe, editor_type="jedi")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                editor.set_code(f.read())
        except Exception as e:
            editor.set_code(f"# Error reading file: {e}")
        editor.property_file_path = path
        return editor

    def _handle_close_request(self, index):
        if index == 0: return
        item = self.tabBar.tabItem(index)
        key_to_remove = item.routeKey()
        path_to_del = None
        for path, r_key in self._opened_files.items():
            if r_key == key_to_remove:
                path_to_del = path
                break
        if path_to_del:
            del self._opened_files[path_to_del]
        self.removeTab(index)

    def close_all_non_main_tabs(self):
        for i in range(self.count() - 1, 0, -1):
            self.removeTab(i)
        self._opened_files.clear()
        self.setCurrentIndex(0)

    def get_current_editor_info(self):
        idx = self.currentIndex()
        widget = self.currentWidget()
        is_main = (idx == 0)
        return is_main, widget