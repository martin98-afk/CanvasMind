# -*- coding: utf-8 -*-
import os

from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from Qt import QtWidgets, QtCore
from qfluentwidgets import LineEdit, TransparentToolButton

from app.utils.utils import get_icon
from app.widgets.basic_widget.variable_complete_widget import VariableCompletionLineEdit
from app.widgets.dialog_widget.ssh_remote_file_dialog import SSHRemoteFileDialog
from app.widgets.node_widget.base import CustomNodeBaseWidget


# --- 修改后的 FileSelectWidget ---
class FileSelectWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(str)
    fixed_height = True

    def __init__(self, parent=None, default_ext="", get_port_func=None):
        super().__init__(parent)
        self.main_window = parent
        self._path = ""
        self._is_folder_mode = default_ext.lower() == "folder"

        self._file_filter = "All Files (*)"
        if not self._is_folder_mode and default_ext:
            ext = default_ext if default_ext.startswith('.') else f".{default_ext}"
            clean_ext = ext.replace('.', '')
            self._file_filter = f"{clean_ext.upper()} Files (*{ext});;All Files (*)"

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        gv = getattr(parent, 'global_variables', None)
        self.path_edit = VariableCompletionLineEdit(
            get_variable_list_func=lambda func=get_port_func: gv.get_vars(func()) if gv else [],
            use_qcursor=False, parent=parent
        )
        self.path_edit.textChanged.connect(self._on_text_changed)
        self.path_edit.setMinimumWidth(180)
        placeholder = "选择文件夹..." if self._is_folder_mode else "选择文件..."
        self.path_edit.setPlaceholderText(placeholder)

        self.btn_clear = TransparentToolButton(get_icon("清空参数"), self)
        self.btn_clear.setToolTip("清空路径")
        self.btn_clear.setFixedSize(30, 30)
        self.btn_clear.clicked.connect(self._on_clear)
        self.btn_clear.setVisible(False)

        self.btn_browse = TransparentToolButton(get_icon("文件选择"))
        self.btn_browse.setIconSize(QtCore.QSize(30, 30))
        self.btn_browse.setToolTip(placeholder)
        self.btn_browse.clicked.connect(self._on_browse)

        layout.addWidget(self.path_edit)
        layout.addWidget(self.btn_clear)
        layout.addWidget(self.btn_browse)

    def _on_browse(self):
        """核心逻辑修改：判断是本地还是远程"""
        # 获取 main_window 的环境数据
        env_data = getattr(self.main_window, "env_data", {})
        is_ssh = env_data.get("type") == "ssh"

        if is_ssh:
            # 使用 PyCharm 级别的远程浏览器
            dialog = SSHRemoteFileDialog(
                env_data=env_data,
                selection_mode="folder" if self._is_folder_mode else "file",
                file_filter=self._file_filter,
                parent=self.main_window
            )
            # 应用深色主题到整个对话框
            # setDarkTheme(dialog) # 如果你有全局主题控制函数

            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                path = dialog.get_selected_result()
                if path:
                    self.set_value(path)
                    self.valueChanged.emit(path)
        else:
            # --- 本地模式 (原有逻辑) ---
            if self._path:
                start_dir = self._path if os.path.isdir(self._path) else os.path.dirname(self._path)
            else:
                start_dir = os.getcwd()

            if self._is_folder_mode:
                dir_path = QtWidgets.QFileDialog.getExistingDirectory(
                    self.main_window, "Select Directory", start_dir,
                    QtWidgets.QFileDialog.ShowDirsOnly | QtWidgets.QFileDialog.DontResolveSymlinks
                )
                if dir_path:
                    self.set_value(dir_path)
                    self.valueChanged.emit(dir_path)
            else:
                file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                    self.main_window, "Select File", start_dir, self._file_filter
                )
                if file_path:
                    self.set_value(file_path)
                    self.valueChanged.emit(file_path)

    def _on_clear(self):
        self.set_value("")
        self.valueChanged.emit("")

    def _on_text_changed(self, text):
        self._path = text
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
        return QtCore.QSize(240, 30)


class FileSelectWrapper(CustomNodeBaseWidget):
    """保持不变"""

    def __init__(self, parent=None, name="", label="", default="", window=None, z_value=1):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET + z_value)
        self.set_name(name)
        self.set_label(f"{label}({name})")

        widget = FileSelectWidget(
            parent=window,
            default_ext=default,
            get_port_func=self.get_port_func
        )
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)