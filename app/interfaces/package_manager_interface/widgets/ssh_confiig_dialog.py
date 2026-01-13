# -*- coding: utf-8 -*-
from qfluentwidgets import (
    LineEdit, BodyLabel, StrongBodyLabel, MessageBoxBase, PasswordLineEdit
)


class SSHAddrDialog(MessageBoxBase):
    """自定义 SSH 配置对话框，支持新增和编辑模式"""

    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.titleLabel = StrongBodyLabel("SSH 环境配置", self)

        # 初始化组件
        self.name_edit = LineEdit(self)
        self.h_edit = LineEdit(self)
        self.u_edit = LineEdit(self)
        self.p_edit = PasswordLineEdit(self)
        self.path_edit = LineEdit(self)

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

        # 批量添加带 Label 的行
        self._add_form_item("环境名称:", self.name_edit)
        self._add_form_item("主机地址 (IP:端口):", self.h_edit)
        self._add_form_item("用户名:", self.u_edit)
        self._add_form_item("密码:", self.p_edit)
        self._add_form_item("远程 Python 路径:", self.path_edit)

        # 数据回显
        if data:
            self.name_edit.setText(data.get("name", ""))
            host_str = f"{data.get('host', '')}:{data.get('port', 22)}"
            self.h_edit.setText(host_str)
            self.u_edit.setText(data.get("user", ""))
            self.p_edit.setText(data.get("pwd", ""))
            self.path_edit.setText(data.get("path", ""))

    def _add_form_item(self, label_text, widget):
        """辅助方法：添加说明标签和对应的输入框"""
        label = BodyLabel(label_text, self)
        self.viewLayout.addWidget(label)
        self.viewLayout.addWidget(widget)
        self.viewLayout.addSpacing(8)  # 每一行之间的间距

    def get_info(self):
        """提取并解析用户输入的数据"""
        host_input = self.h_edit.text().strip()

        # 默认值处理
        host = host_input
        port = 22

        # 端口解析逻辑优化
        if ":" in host_input:
            try:
                parts = host_input.rsplit(":", 1)  # 从右侧分割，防止 IPv6 干扰
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