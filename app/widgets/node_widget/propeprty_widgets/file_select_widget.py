# -*- coding: utf-8 -*-
import os
import stat
from datetime import datetime

import paramiko
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from Qt import QtWidgets, QtCore
from Qt.QtWidgets import QHeaderView, QTableWidgetItem
from qfluentwidgets import LineEdit, TransparentToolButton, FluentIcon, ToolButton
from qfluentwidgets import (TableWidget, BodyLabel, PrimaryPushButton,
                            PushButton, ListWidget)

from app.utils.utils import get_icon
from app.widgets.node_widget.base import CustomNodeBaseWidget


class SSFTSession:
    """管理 SFTP 连接和数据获取"""
    def __init__(self, env_data):
        self.env_data = env_data
        self.ssh = None
        self.sftp = None

    def connect(self):
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(
            hostname=self.env_data.get('host'),
            port=int(self.env_data.get('port', 22)),
            username=self.env_data.get('user'),
            password=self.env_data.get('pwd'),
            timeout=10
        )
        self.sftp = self.ssh.open_sftp()

    def list_dir_info(self, path):
        """获取目录下所有文件的详细信息"""
        results = []
        for entry in self.sftp.listdir_attr(path):
            is_dir = stat.S_ISDIR(entry.st_mode)
            results.append({
                "name": entry.filename,
                "is_dir": is_dir,
                "size": entry.st_size,
                "mtime": datetime.fromtimestamp(entry.st_mtime).strftime('%Y-%m-%d %H:%M'),
                "path": os.path.join(path, entry.filename).replace('\\', '/')
            })
        # 排序：文件夹在前，名字排序
        results.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        return results

    def close(self):
        if self.sftp: self.sftp.close()
        if self.ssh: self.ssh.close()


class SSHRemoteFileDialog(QtWidgets.QDialog):
    def __init__(self, env_data, is_folder_mode=False, file_filter="*", parent=None):
        super().__init__(parent)
        self.env_data = env_data
        self.is_folder_mode = is_folder_mode
        self.session = SSFTSession(env_data)
        self.current_path = env_data.get('workdir', '/')

        self.setWindowTitle("远程文件浏览器 (SSH)")
        self.resize(1100, 700)

        # 强制深色背景样式
        self.setStyleSheet("""
            QDialog { background-color: #272727; }
            QWidget { background-color: #272727; color: #E0E0E0; font-family: 'Segoe UI', 'PingFang SC'; }
            QTableWidget { border: 1px solid #333; background-color: #2d2d2d; gridline-color: #333; }
            QHeaderView::section { background-color: #333; color: #AAA; padding: 5px; border: none; }
            QListWidget { background-color: #2d2d2d; border: none; border-right: 1px solid #333; }
        """)

        self._setup_ui()
        self._init_connection()

    def _setup_ui(self):
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- 1. 左侧侧边栏 (快捷路径) ---
        self.side_bar = ListWidget()
        self.side_bar.setFixedWidth(180)
        self._add_shortcut("工作目录", self.env_data.get('workdir', '/'), FluentIcon.HOME)
        self._add_shortcut("根目录", "/", FluentIcon.FOLDER)
        self.side_bar.itemClicked.connect(lambda it: self._load_path(it.data(QtCore.Qt.UserRole)))
        main_layout.addWidget(self.side_bar)

        # --- 2. 右侧主区域 ---
        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)
        right_layout.setContentsMargins(15, 15, 15, 15)
        right_layout.setSpacing(12)

        # 顶部栏：返回按钮 + 路径地址
        top_bar = QtWidgets.QHBoxLayout()
        self.btn_back = ToolButton(FluentIcon.UP)
        self.btn_back.clicked.connect(self._go_up)
        self.path_edit = LineEdit()
        self.path_edit.setPlaceholderText("远程路径...")
        self.path_edit.returnPressed.connect(lambda: self._load_path(self.path_edit.text()))
        top_bar.addWidget(self.btn_back)
        top_bar.addWidget(self.path_edit)
        right_layout.addLayout(top_bar)

        # 文件列表表格
        self.table = TableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["名称", "大小", "修改日期"])
        # 修复表头宽度和对齐问题
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)  # PyCharm 风格通常不显示网格线

        # 解决错位：不使用 Stretch 模式，而是手动分配初始比例
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(True)  # 让日期列（最后一列）拉伸，或者都不拉伸

        # 设置初始宽度
        self.table.setColumnWidth(0, 500)  # 名称给大一点
        self.table.setColumnWidth(1, 100)  # 大小固定
        self.table.setColumnWidth(2, 150)  # 日期固定
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # 将拉伸交给最后一列通常更稳定
        # 绑定点击信号
        self.table.itemClicked.connect(self._on_item_clicked)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)

        right_layout.addWidget(self.table)

        # 底部选择栏
        bottom_layout = QtWidgets.QHBoxLayout()
        self.line_selection = LineEdit()
        self.line_selection.setPlaceholderText("未选择任何项")

        self.btn_ok = PrimaryPushButton("确定选择")
        self.btn_cancel = PushButton("取消")

        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

        bottom_layout.addWidget(BodyLabel("当前选择: "))
        bottom_layout.addWidget(self.line_selection, 1)
        bottom_layout.addWidget(self.btn_ok)
        bottom_layout.addWidget(self.btn_cancel)
        right_layout.addLayout(bottom_layout)

        main_layout.addWidget(right_widget)

    def _add_shortcut(self, name, path, icon):
        item = QtWidgets.QListWidgetItem(icon.icon(), name)
        item.setData(QtCore.Qt.UserRole, path)
        self.side_bar.addItem(item)

    def _init_connection(self):
        try:
            self.session.connect()
            self._load_path(self.current_path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "SSH 连接失败", f"无法连接到服务器:\n{str(e)}")
            QtCore.QTimer.singleShot(0, self.reject)

    def _load_path(self, path):
        if not path: path = "/"
        path = path.replace('\\', '/')
        try:
            files = self.session.list_dir_info(path)
            self.current_path = path
            self.path_edit.setText(path)

            # 如果是文件夹模式，默认选择当前目录
            if self.is_folder_mode:
                self.line_selection.setText(self.current_path)

            self.table.setRowCount(0)
            for f in files:
                row = self.table.rowCount()
                self.table.insertRow(row)

                # 名称列
                icon = FluentIcon.FOLDER if f['is_dir'] else FluentIcon.DOCUMENT
                name_item = QTableWidgetItem(icon.icon(), f['name'])
                name_item.setData(QtCore.Qt.UserRole, f)  # 存入完整数据

                # 大小列
                size_val = f"{f['size'] / 1024:.1f} KB" if not f['is_dir'] else ""
                size_item = QTableWidgetItem(size_val)

                # 日期列
                date_item = QTableWidgetItem(f['mtime'])

                self.table.setItem(row, 0, name_item)
                self.table.setItem(row, 1, size_item)
                self.table.setItem(row, 2, date_item)

        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "错误", f"读取目录失败: {e}")

    def _on_item_clicked(self, item):
        """处理单击事件，同步下方输入框"""
        row = item.row()
        # 获取第一列存入的数据结构
        data = self.table.item(row, 0).data(QtCore.Qt.UserRole)

        if self.is_folder_mode:
            # 文件夹模式：只有点击文件夹才更新，或者始终显示当前目录+选中的子目录
            if data['is_dir']:
                self.line_selection.setText(data['path'])
            else:
                self.line_selection.setText(self.current_path)
        else:
            # 文件模式：只有点击文件才同步路径
            if not data['is_dir']:
                self.line_selection.setText(data['path'])
            else:
                self.line_selection.clear()

    def _on_item_double_clicked(self, item):
        """双击处理：文件夹进入，文件选中退出"""
        row = item.row()
        data = self.table.item(row, 0).data(QtCore.Qt.UserRole)

        if data['is_dir']:
            self._load_path(data['path'])
        else:
            if not self.is_folder_mode:
                self.line_selection.setText(data['path'])
                self.accept()

    def _go_up(self):
        if self.current_path == "/": return
        parent = os.path.dirname(self.current_path.rstrip('/'))
        if not parent: parent = "/"
        self._load_path(parent)

    def get_selected_result(self):
        """返回最终选择的路径"""
        return self.line_selection.text()

    def closeEvent(self, event):
        self.session.close()
        super().closeEvent(event)


# --- 修改后的 FileSelectWidget ---
class FileSelectWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(str)
    fixed_height = True

    def __init__(self, parent=None, default_ext=""):
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

        self.path_edit = LineEdit(parent=self)
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
                is_folder_mode=self._is_folder_mode,
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
        )
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)