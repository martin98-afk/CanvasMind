# -*- coding: utf-8 -*-
import os

from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PyQt5 import QtWidgets, QtCore
from Qt import QtWidgets, QtCore
from qfluentwidgets import TransparentToolButton

from app.utils.utils import get_icon
from app.widgets.basic_widget.variable_complete_widget import VariableCompletionLineEdit
from app.widgets.dialog_widget.ssh_remote_file_dialog import SSHRemoteFileDialog
from app.widgets.node_widget.base import CustomNodeBaseWidget


class FileSelectWidget(QtWidgets.QFrame):  # 改为 QFrame 以支持边框样式
    valueChanged = QtCore.Signal(str)
    fixed_height = True

    def __init__(self, parent=None, default_ext="", get_port_func=None):
        super().__init__(parent)
        self.main_window = parent
        self._path = ""
        self._is_folder_mode = default_ext.lower() == "folder"

        # 1. 整体容器样式配置 (深色背景，亮色边框)
        self.setObjectName("FileSelectWidget")
        self.setStyleSheet("""
            #FileSelectWidget {
                border: 1px solid rgba(255, 255, 255, 40);
                border-radius: 6px;
                background-color: rgba(30, 30, 30, 150);
            }
            #FileSelectWidget:hover {
                border: 1px solid rgba(255, 255, 255, 80);
                background-color: rgba(45, 45, 45, 180);
            }
        """)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)  # 增加左边距
        layout.setSpacing(4)

        # 2. 获取全局变量支持
        gv = getattr(parent, "global_variables", None)

        # 3. 创建输入框并配置白色文字样式
        # 注意：这里继续使用你的 VariableCompletionLineEdit
        self.path_edit = VariableCompletionLineEdit(
            get_variable_list_func=lambda func=get_port_func: gv.get_vars(func())
            if gv
            else [],
            use_qcursor=False,
            parent=parent,
        )
        self.path_edit.textChanged.connect(self._on_text_changed)
        self.path_edit.setMinimumWidth(180)
        placeholder = "选择文件夹..." if self._is_folder_mode else "选择文件..."
        self.path_edit.setPlaceholderText(placeholder)

        # 4. 按钮配置
        self.btn_clear = TransparentToolButton(get_icon("清空参数"), self)
        self.btn_clear.setToolTip(self.tr("清空路径"))
        self.btn_clear.setFixedSize(28, 28)
        self.btn_clear.clicked.connect(self._on_clear)
        self.btn_clear.setVisible(False)

        # 根据模式选择图标
        self.btn_browse = TransparentToolButton(get_icon("文件选择"), self)
        self.btn_browse.setIconSize(QtCore.QSize(20, 20))  # 稍微调小一点适配紧凑布局
        self.btn_browse.setFixedSize(28, 28)
        self.btn_browse.setToolTip(self.tr(placeholder))
        self.btn_browse.clicked.connect(self._on_browse)

        layout.addWidget(self.path_edit)
        layout.addWidget(self.btn_clear)
        layout.addWidget(self.btn_browse)

        # 设置文件过滤器
        self._file_filter = "All Files (*)"
        if not self._is_folder_mode and default_ext:
            ext = default_ext if default_ext.startswith(".") else f".{default_ext}"
            clean_ext = ext.replace(".", "")
            self._file_filter = f"{clean_ext.upper()} Files (*{ext});;All Files (*)"

    def _on_browse(self):
        """保持原有逻辑不变"""
        env_data = getattr(self.main_window, "env_data", {})
        is_ssh = env_data.get("type") == "ssh"

        if is_ssh:
            # SSH 模式逻辑
            path = self._path if self._is_folder_mode else os.path.dirname(self._path)
            if SSHRemoteFileDialog:
                dialog = SSHRemoteFileDialog(
                    env_data=env_data,
                    selection_mode="folder" if self._is_folder_mode else "file",
                    file_filter=self._file_filter,
                    parent=self.main_window,
                    initial_path=path,
                )
                if dialog.exec_() == QtWidgets.QDialog.Accepted:
                    path = dialog.get_selected_result()
                    if path:
                        self.set_value(path)
                        self.valueChanged.emit(path)
        else:
            # 本地模式逻辑
            if self._path:
                start_dir = (
                    self._path
                    if os.path.isdir(self._path)
                    else os.path.dirname(self._path)
                )
            else:
                start_dir = os.getcwd()

            if self._is_folder_mode:
                dir_path = QtWidgets.QFileDialog.getExistingDirectory(
                    self.main_window,
                    "选择目录",
                    start_dir,
                    QtWidgets.QFileDialog.ShowDirsOnly
                    | QtWidgets.QFileDialog.DontResolveSymlinks,
                )
                if dir_path:
                    self.set_value(dir_path)
                    self.valueChanged.emit(dir_path)
            else:
                file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                    self.main_window, "选择文件", start_dir, self._file_filter
                )
                if file_path:
                    self.set_value(file_path)
                    self.valueChanged.emit(file_path)

    def _on_clear(self):
        self.set_value("")
        self.valueChanged.emit("")

    def _on_text_changed(self, text):
        self._path = text
        self.btn_clear.setVisible(bool(text))
        self.valueChanged.emit(text)

    def get_value(self):
        return self._path

    def set_value(self, value):
        self._path = value or ""
        self.path_edit.setText(self._path)
        if self._path:
            self.path_edit.setCursorPosition(len(self._path))
        self.btn_clear.setVisible(bool(self._path))

    def sizeHint(self):
        return QtCore.QSize(240, 32)


class FileSelectWrapper(CustomNodeBaseWidget):
    """保持不变"""

    def __init__(
        self, parent=None, name="", label="", default="", window=None, z_value=1
    ):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET + z_value)
        self.set_name(name)
        self.set_label(f"{label}({name})")

        widget = FileSelectWidget(
            parent=window, default_ext=default, get_port_func=self.get_port_func
        )
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def _get_local_value(self):
        return self.get_custom_widget().get_value()

    def _set_local_value(self, value):
        self.get_custom_widget().set_value(value)
