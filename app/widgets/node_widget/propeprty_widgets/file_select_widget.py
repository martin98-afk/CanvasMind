# -*- coding: utf-8 -*-
import os
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from Qt import QtWidgets, QtCore
# 引入 FluentIcon 用于显示标准的关闭图标
from qfluentwidgets import LineEdit, TransparentToolButton, FluentIcon

from app.utils.utils import get_icon
from app.widgets.node_widget.base import CustomNodeBaseWidget


class FileSelectWidget(QtWidgets.QWidget):
    """文件/文件夹选择控件：左侧路径显示(不可编辑) + 中间清空按钮 + 右侧浏览按钮"""
    valueChanged = QtCore.Signal(str)
    fixed_height = True

    def __init__(self, parent=None, default_ext=""):
        super().__init__(parent)
        self.parent = parent
        self._path = ""

        # 判断是否为文件夹模式 (约定传入 "folder" 为选择文件夹)
        self._is_folder_mode = default_ext.lower() == "folder"

        # 解析文件过滤器 (仅在文件模式下有效)
        self._file_filter = "All Files (*)"
        if not self._is_folder_mode and default_ext:
            ext = default_ext if default_ext.startswith('.') else f".{default_ext}"
            clean_ext = ext.replace('.', '')
            self._file_filter = f"{clean_ext.upper()} Files (*{ext});;All Files (*)"

        # 布局
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)  # 稍微增加一点间距

        # 1. 路径显示框
        self.path_edit = LineEdit(parent=self)
        self.path_edit.setReadOnly(True)
        self.path_edit.setMinimumWidth(150)
        # 根据模式设置不同的提示语
        placeholder = "选择文件夹..." if self._is_folder_mode else "选择文件..."
        self.path_edit.setPlaceholderText(placeholder)

        # 2. 清空按钮 (新增)
        # 使用 FluentIcon.CLOSE 作为图标，如果想用自定义图标可替换为 get_icon("xxx")
        self.btn_clear = TransparentToolButton(get_icon("清空参数"), self)
        self.btn_clear.setToolTip("清空路径")
        self.btn_clear.setFixedSize(30, 30)
        self.btn_clear.clicked.connect(self._on_clear)
        self.btn_clear.setVisible(False)  # 默认隐藏，有值时才显示

        # 3. 浏览按钮 (根据模式选择图标或 ToolTip)
        self.btn_browse = TransparentToolButton(get_icon("文件选择"))
        self.btn_browse.setIconSize(QtCore.QSize(30, 30))
        self.btn_browse.setToolTip(placeholder)
        self.btn_browse.clicked.connect(self._on_browse)

        layout.addWidget(self.path_edit)
        layout.addWidget(self.btn_clear)  # 添加到布局中间
        layout.addWidget(self.btn_browse)

    def _on_browse(self):
        """弹出对话框"""
        # 确定起始目录
        if self._path:
            # 如果是路径且存在，取其目录或本身
            start_dir = self._path if os.path.isdir(self._path) else os.path.dirname(self._path)
        else:
            start_dir = os.getcwd()

        if self._is_folder_mode:
            # --- 文件夹选择模式 ---
            dir_path = QtWidgets.QFileDialog.getExistingDirectory(
                self.parent,
                "Select Directory",
                start_dir,
                QtWidgets.QFileDialog.ShowDirsOnly | QtWidgets.QFileDialog.DontResolveSymlinks
            )
            if dir_path:
                self.set_value(dir_path)
                self.valueChanged.emit(dir_path)
        else:
            # --- 文件选择模式 ---
            file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self.parent,
                "Select File",
                start_dir,
                self._file_filter
            )
            if file_path:
                self.set_value(file_path)
                self.valueChanged.emit(file_path)

    def _on_clear(self):
        """清空当前路径"""
        self.set_value("")
        self.valueChanged.emit("")

    def get_value(self):
        return self._path

    def set_value(self, value):
        self._path = value or ""
        self.path_edit.setText(self._path)

        # 如果有路径，将光标移到最后以便看到文件名
        if self._path:
            self.path_edit.setCursorPosition(len(self._path))

        # 根据是否有值，控制清空按钮的显示/隐藏
        self.btn_clear.setVisible(bool(self._path))

    def sizeHint(self):
        return QtCore.QSize(240, 30)


class FileSelectWrapper(CustomNodeBaseWidget):
    """文件选择控件封装类"""

    def __init__(self, parent=None, name="", label="", default="", window=None):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET)
        self.set_name(name)
        self.set_label(f"{label}({name})")

        # 逻辑：
        # 1. 如果输入 default="folder"，则点击按钮选择文件夹
        # 2. 如果输入 default=".txt"，则点击按钮选择txt文件
        # 3. 如果输入 default=""，则选择任意文件
        widget = FileSelectWidget(
            parent=window,
            default_ext=default,
        )
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)