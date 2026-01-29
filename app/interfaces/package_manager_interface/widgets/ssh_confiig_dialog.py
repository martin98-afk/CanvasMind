# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QHBoxLayout  # 或者是 from Qt.QtWidgets
from qfluentwidgets import (
    LineEdit, BodyLabel, StrongBodyLabel, MessageBoxBase,
    PasswordLineEdit, ToolButton, FluentIcon, InfoBar
)

from app.widgets.dialog_widget.ssh_remote_file_dialog import SSHRemoteFileDialog


class SSHAddrDialog(MessageBoxBase):
    """自定义 SSH 配置对话框，支持浏览远程文件"""

    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.titleLabel = StrongBodyLabel("SSH 环境配置", self)

        # 初始化组件
        self.name_edit = LineEdit(self)
        self.h_edit = LineEdit(self)
        self.u_edit = LineEdit(self)
        self.p_edit = PasswordLineEdit(self)
        self.path_edit = LineEdit(self)

        # 浏览按钮
        self.browse_btn = ToolButton(FluentIcon.FOLDER, self)
        self.browse_btn.setToolTip("浏览远程文件系统")
        self.browse_btn.clicked.connect(self._open_remote_browser)

        # 设置占位符
        self.name_edit.setPlaceholderText("例如: 生产服务器-01")
        self.h_edit.setPlaceholderText("192.168.1.100:22")
        self.u_edit.setPlaceholderText("root")
        self.p_edit.setPlaceholderText("请输入密码")
        self.path_edit.setPlaceholderText("/usr/bin/python3")

        # 布局组织
        self.widget.setMinimumWidth(450)
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(10)

        self._add_form_item("环境名称:", self.name_edit)
        self._add_form_item("主机地址 (IP:端口):", self.h_edit)
        self._add_form_item("用户名:", self.u_edit)
        self._add_form_item("密码:", self.p_edit)

        # 特殊处理：带按钮的路径行
        path_label = BodyLabel("远程 Python 路径:", self)
        self.viewLayout.addWidget(path_label)

        path_layout = QHBoxLayout()
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(8)
        path_layout.addWidget(self.path_edit, 1)
        path_layout.addWidget(self.browse_btn)
        self.viewLayout.addLayout(path_layout)
        self.viewLayout.addSpacing(8)

        # 数据回显
        if data:
            self.name_edit.setText(data.get("name", ""))
            host_str = f"{data.get('host', '')}:{data.get('port', 22)}"
            self.h_edit.setText(host_str)
            self.u_edit.setText(data.get("user", ""))
            self.p_edit.setText(data.get("pwd", ""))
            self.path_edit.setText(data.get("path", ""))

    def _add_form_item(self, label_text, widget):
        label = BodyLabel(label_text, self)
        self.viewLayout.addWidget(label)
        self.viewLayout.addWidget(widget)
        self.viewLayout.addSpacing(8)

    def _open_remote_browser(self):
        """实时解析当前填写的参数并打开远程浏览器"""
        info = self.get_info()

        # 简单校验
        if not info['host'] or not info['pwd']:
            InfoBar.warning(
                title='参数不足',
                content="请先填写主机地址、用户名和密码以连接远程服务器",
                parent=self.window()
            )
            return

        try:
            dialog = SSHRemoteFileDialog(
                env_data={
                    'host': info['host'],
                    'port': info['port'],
                    'user': info['user'],
                    'pwd': info['pwd'],
                    'workdir': info['path'] or '/'  # 默认从根目录开始找
                },
                selection_mode="any",
                parent=self
            )

            if dialog.exec_():
                selected_path = dialog.get_selected_result()
                if selected_path:
                    self.path_edit.setText(selected_path)
        except Exception as e:
            InfoBar.error(title="连接失败", content=str(e), parent=self.window())

    def get_info(self):
        """解析逻辑保持不变"""
        host_input = self.h_edit.text().strip()
        host = host_input
        port = 22

        if ":" in host_input:
            try:
                parts = host_input.rsplit(":", 1)
                host = parts[0]
                if len(parts) > 1 and parts[1].isdigit():
                    port = int(parts[1])
            except Exception:
                pass

        return {
            "name": self.name_edit.text().strip() or host or "未命名环境",
            "host": host,
            "port": port,
            "user": self.u_edit.text().strip() or "root",
            "pwd": self.p_edit.text().strip(),
            "path": self.path_edit.text().strip() or "/usr/bin/python3"
        }