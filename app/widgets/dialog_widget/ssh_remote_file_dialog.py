import os
import stat
from datetime import datetime

import paramiko
from Qt import QtWidgets, QtCore
from Qt.QtWidgets import QHeaderView, QTableWidgetItem
from qfluentwidgets import LineEdit, FluentIcon, ToolButton
from qfluentwidgets import (TableWidget, BodyLabel, PrimaryPushButton,
                            PushButton, ListWidget)


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
    def __init__(self, env_data, selection_mode="file", file_filter="*", parent=None):
        """
        selection_mode:
            - "file": 只能选择文件
            - "folder": 只能选择文件夹
            - "any": 文件和文件夹都可以选择
        """
        super().__init__(parent)
        self.env_data = env_data
        self.selection_mode = selection_mode  # 修改为模式字符串
        self.session = SSFTSession(env_data)
        self.current_path = env_data.get('workdir', '/')

        self.setWindowTitle("远程文件浏览器 (SSH)")
        self.resize(1100, 700)

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

        self.side_bar = ListWidget()
        self.side_bar.setFixedWidth(180)
        self._add_shortcut("工作目录", self.env_data.get('workdir', '/'), FluentIcon.HOME)
        self._add_shortcut("根目录", "/", FluentIcon.FOLDER)
        self.side_bar.itemClicked.connect(lambda it: self._load_path(it.data(QtCore.Qt.UserRole)))
        main_layout.addWidget(self.side_bar)

        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)
        right_layout.setContentsMargins(15, 15, 15, 15)
        right_layout.setSpacing(12)

        top_bar = QtWidgets.QHBoxLayout()
        self.btn_back = ToolButton(FluentIcon.UP)
        self.btn_back.clicked.connect(self._go_up)
        self.path_edit = LineEdit()
        self.path_edit.setPlaceholderText("远程路径...")
        self.path_edit.returnPressed.connect(lambda: self._load_path(self.path_edit.text()))
        top_bar.addWidget(self.btn_back)
        top_bar.addWidget(self.path_edit)
        right_layout.addLayout(top_bar)

        self.table = TableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["名称", "大小", "修改日期"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)

        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(True)
        self.table.setColumnWidth(0, 500)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 150)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)

        self.table.itemClicked.connect(self._on_item_clicked)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)

        right_layout.addWidget(self.table)

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

            # 在文件夹模式或“任何”模式下，进入新目录时默认选择当前目录路径
            if self.selection_mode in ["folder", "any"]:
                self.line_selection.setText(self.current_path)

            self.table.setRowCount(0)
            for f in files:
                row = self.table.rowCount()
                self.table.insertRow(row)
                icon = FluentIcon.FOLDER if f['is_dir'] else FluentIcon.DOCUMENT
                name_item = QTableWidgetItem(icon.icon(), f['name'])
                name_item.setData(QtCore.Qt.UserRole, f)
                size_val = f"{f['size'] / 1024:.1f} KB" if not f['is_dir'] else ""
                size_item = QTableWidgetItem(size_val)
                date_item = QTableWidgetItem(f['mtime'])
                self.table.setItem(row, 0, name_item)
                self.table.setItem(row, 1, size_item)
                self.table.setItem(row, 2, date_item)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "错误", f"读取目录失败: {e}")

    def _on_item_clicked(self, item):
        """处理单击事件，同步下方输入框"""
        row = item.row()
        data = self.table.item(row, 0).data(QtCore.Qt.UserRole)

        if self.selection_mode == "any":
            # 【新模式】点击任何东西都更新路径
            self.line_selection.setText(data['path'])

        elif self.selection_mode == "folder":
            if data['is_dir']:
                self.line_selection.setText(data['path'])
            else:
                self.line_selection.setText(self.current_path)

        elif self.selection_mode == "file":
            if not data['is_dir']:
                self.line_selection.setText(data['path'])
            else:
                self.line_selection.clear()

    def _on_item_double_clicked(self, item):
        """双击处理"""
        row = item.row()
        data = self.table.item(row, 0).data(QtCore.Qt.UserRole)

        if data['is_dir']:
            # 无论什么模式，双击文件夹都是“进入”
            self._load_path(data['path'])
        else:
            # 如果双击的是文件，在 file 或 any 模式下直接完成选择
            if self.selection_mode in ["file", "any"]:
                self.line_selection.setText(data['path'])
                self.accept()

    def _go_up(self):
        if self.current_path == "/": return
        parent = os.path.dirname(self.current_path.rstrip('/'))
        if not parent: parent = "/"
        self._load_path(parent)

    def get_selected_result(self):
        return self.line_selection.text()

    def closeEvent(self, event):
        self.session.close()
        super().closeEvent(event)