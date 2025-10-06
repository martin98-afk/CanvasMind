# -*- coding: utf-8 -*-
import os
from datetime import datetime

from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout
from qfluentwidgets import (
    CardWidget, BodyLabel, PrimaryPushButton,
    ToolButton, FluentIcon, InfoBar,
    HyperlinkButton
)

from app.utils.service_manager import SERVICE_MANAGER
from app.widgets.service_request_dialog import ServiceRequestDialog


class ProjectCard(CardWidget):
    def __init__(self, project_path, parent=None):
        super().__init__(parent)
        self.project_path = project_path
        self.project_name = os.path.basename(project_path)
        self.service_url_label = None
        self._setup_ui()

    def _setup_ui(self):
        # 固定高度，保证流式布局整齐
        self.setFixedHeight(220)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 项目名称
        self.name_label = BodyLabel(self.project_name)
        self.name_label.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        layout.addWidget(self.name_label)

        # 项目信息
        info_text = self._get_project_info()
        self.info_label = BodyLabel(info_text)
        self.info_label.setWordWrap(True)
        self.info_label.setMaximumHeight(80)
        self.info_label.setStyleSheet("color: #888888; font-size: 12px;")
        layout.addWidget(self.info_label)

        # 服务 URL（初始隐藏）
        self.service_url_label = HyperlinkButton("", "服务地址")
        self.service_url_label.setVisible(False)
        layout.addWidget(self.service_url_label)

        # 按钮布局
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.run_btn = PrimaryPushButton(text="运行", icon=FluentIcon.PLAY, parent=self)
        self.run_btn.setFixedWidth(80)

        self.service_btn = PrimaryPushButton(text="上线", icon=FluentIcon.LINK, parent=self)
        self.service_btn.setFixedWidth(80)

        self.request_btn = PrimaryPushButton(text="请求", icon=FluentIcon.SEND, parent=self)
        self.request_btn.setFixedWidth(80)
        self.request_btn.setEnabled(False)
        self.request_btn.clicked.connect(self._open_request_dialog)

        self.view_log_btn = ToolButton(FluentIcon.VIEW, self)
        self.view_log_btn.setToolTip("查看日志")

        self.open_folder_btn = ToolButton(FluentIcon.FOLDER, self)
        self.open_folder_btn.setToolTip("打开文件夹")

        self.delete_btn = ToolButton(FluentIcon.DELETE, self)
        self.delete_btn.setToolTip("删除项目")

        left_btns = QHBoxLayout()
        left_btns.addWidget(self.run_btn)
        left_btns.addWidget(self.service_btn)
        left_btns.addWidget(self.request_btn)

        right_btns = QHBoxLayout()
        right_btns.addWidget(self.view_log_btn)
        right_btns.addWidget(self.open_folder_btn)
        right_btns.addWidget(self.delete_btn)

        btn_layout.addLayout(left_btns)
        btn_layout.addStretch()
        btn_layout.addLayout(right_btns)

        layout.addLayout(btn_layout)

        self._update_service_button()

    def _update_service_button(self):
        if SERVICE_MANAGER.is_running(self.project_path):
            self.service_btn.setText("下线")
            self.service_btn.setIcon(FluentIcon.PAUSE)
            self.request_btn.setEnabled(True)
            url = SERVICE_MANAGER.get_url(self.project_path)
            if url:
                self.service_url_label.setUrl(QUrl(url))
                self.service_url_label.setText(url)
                self.service_url_label.setVisible(True)
        else:
            self.service_btn.setText("上线")
            self.service_btn.setIcon(FluentIcon.LINK)
            self.request_btn.setEnabled(False)
            self.service_url_label.setVisible(False)

    def _get_project_info(self):
        info_lines = []
        try:
            stat = os.stat(self.project_path)
            create_time = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d")
            info_lines.append(f"创建: {create_time}")
        except Exception:
            info_lines.append("创建: 未知")

        req_file = os.path.join(self.project_path, "requirements.txt")
        if os.path.exists(req_file):
            try:
                with open(req_file, 'r', encoding='utf-8') as f:
                    packages = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                    if packages:
                        deps = ", ".join(packages[:5])
                        if len(packages) > 5:
                            deps += f" +{len(packages) - 5} 个"
                        info_lines.append(f"依赖: {deps}")
            except Exception:
                pass

        components_dir = os.path.join(self.project_path, "components")
        if os.path.exists(components_dir):
            try:
                comp_count = sum([len(files) for r, d, files in os.walk(components_dir)])
                info_lines.append(f"组件: {comp_count} 个")
            except Exception:
                pass

        if os.path.exists(os.path.join(self.project_path, "api_server.py")):
            info_lines.append("支持微服务")

        return "\n".join(info_lines)

    def _open_request_dialog(self):
        if not SERVICE_MANAGER.is_running(self.project_path):
            InfoBar.warning("服务未运行", "请先点击'上线'启动服务", parent=self.parent())
            return

        url = SERVICE_MANAGER.get_url(self.project_path)
        if not url:
            return

        dialog = ServiceRequestDialog(self.project_path, url, self.parent())
        dialog.exec()

    def update_status(self, is_running=False):
        if is_running:
            self.run_btn.setText("停止")
            self.run_btn.setIcon(FluentIcon.PAUSE)
            self.run_btn.setEnabled(False)
        else:
            self.run_btn.setText("运行")
            self.run_btn.setIcon(FluentIcon.PLAY)
            self.run_btn.setEnabled(True)
