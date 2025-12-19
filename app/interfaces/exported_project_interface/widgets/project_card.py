# -*- coding: utf-8 -*-
import os
import json
import subprocess
from pathlib import Path
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QGuiApplication
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel
from qfluentwidgets import (
    CardWidget, BodyLabel, PrimaryPushButton,
    FluentIcon, InfoBar, ImageLabel, TransparentToolButton
)
from app.server_manager.http_server.service_manager import SERVICE_MANAGER
from app.widgets.dialog_widget.service_request_dialog import ServiceRequestDialog


class ClickableLabel(BodyLabel):
    def __init__(self, text="", parent=None, copy_content=None):
        super().__init__(text)
        self.parent = parent
        self.copy_content = copy_content or text
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setCursor(Qt.PointingHandCursor)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setStyleSheet("color: #1e88e5; text-decoration: underline;")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._copy_to_clipboard()
        super().mousePressEvent(event)

    def _copy_to_clipboard(self):
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(self.copy_content)
        InfoBar.success("已复制", "内容已复制到剪贴板", parent=self.parent, duration=1500)


class ProjectCard(CardWidget):
    def __init__(self, project_path, parent=None):
        super().__init__(parent)
        self.project_path = project_path
        self.project_name = Path(project_path).name
        self.home = parent
        self.api_dot = None
        self.mcp_dot = None
        self.api_label = None
        self.mcp_label = None
        self.image_label = None
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedSize(400, 300)
        self.setBorderRadius(12)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(12)

        # === 标题 ===
        self.name_label = BodyLabel(self.project_name)
        self.name_label.setFont(QFont("Microsoft YaHei", 14, QFont.DemiBold))
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setWordWrap(True)
        main_layout.addWidget(self.name_label)

        # === 预览图 ===
        self._create_or_update_preview()

        # === API 服务状态行 ===
        self.api_dot = QLabel()
        self.api_dot.setFixedSize(12, 12)
        self.api_dot.setStyleSheet("border-radius: 6px; background: gray;")
        self.api_label = ClickableLabel("API服务：未部署", self)
        api_layout = QHBoxLayout()
        api_layout.addWidget(self.api_dot)
        api_layout.addWidget(self.api_label, 1)
        api_layout.setSpacing(6)

        # === MCP 工具状态行 ===
        self.mcp_dot = QLabel()
        self.mcp_dot.setFixedSize(12, 12)
        self.mcp_dot.setStyleSheet("border-radius: 6px; background: gray;")
        self.mcp_label = ClickableLabel("MCP工具：未注册", self)
        mcp_layout = QHBoxLayout()
        mcp_layout.addWidget(self.mcp_dot)
        mcp_layout.addWidget(self.mcp_label, 1)
        mcp_layout.setSpacing(6)

        status_layout = QVBoxLayout()
        status_layout.setSpacing(4)
        status_layout.addLayout(api_layout)
        status_layout.addLayout(mcp_layout)
        main_layout.addLayout(status_layout)

        # === 按钮区 ===
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        self.run_btn = PrimaryPushButton("运行", self, FluentIcon.PLAY)
        self.service_btn = PrimaryPushButton("上线", self, FluentIcon.LINK)
        self.edit_btn = TransparentToolButton(FluentIcon.EDIT, self)
        self.view_log_btn = TransparentToolButton(FluentIcon.VIEW, self)
        self.delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
        self.view_log_btn.setToolTip("查看日志")
        self.delete_btn.setToolTip("删除项目")

        for btn in [self.run_btn, self.service_btn]:
            btn.setFixedHeight(28)
            btn.setFont(QFont("Microsoft YaHei", 9))
        for btn in [self.edit_btn, self.view_log_btn, self.delete_btn]:
            btn.setFixedSize(28, 28)

        left_box = QHBoxLayout()
        left_box.addWidget(self.run_btn)
        left_box.addWidget(self.service_btn)

        right_box = QHBoxLayout()
        right_box.setSpacing(8)
        right_box.addWidget(self.edit_btn)
        right_box.addWidget(self.view_log_btn)
        right_box.addWidget(self.delete_btn)

        btn_layout.addLayout(left_box)
        btn_layout.addStretch()
        btn_layout.addLayout(right_box)
        main_layout.addLayout(btn_layout)

        self._update_service_button()
        self.setCursor(Qt.PointingHandCursor)

    def _create_or_update_preview(self):
        if self.image_label:
            self.layout().removeWidget(self.image_label)
            self.image_label.deleteLater()
            self.image_label = None

        preview_path = Path(self.project_path) / "preview.png"
        if preview_path.exists():
            self.image_label = ImageLabel(str(preview_path), self)
            self.image_label.setFixedSize(340, 150)
            self.image_label.setBorderRadius(8, 8, 8, 8)
        else:
            self.image_label = BodyLabel("无预览图")
            self.image_label.setFixedSize(300, 150)
            self.image_label.setAlignment(Qt.AlignCenter)
            self.image_label.setStyleSheet("""
                color: #999;
                background-color: #fafafa;
                border-radius: 8px;
                border: 1px dashed #e0e0e0;
                font-size: 12px;
            """)
        self.layout().insertWidget(1, self.image_label, 0, Qt.AlignCenter)

    def _update_service_button(self):
        is_running = SERVICE_MANAGER.is_running(self.project_path)
        if is_running:
            self.service_btn.setText("下线")
            self.service_btn.setIcon(FluentIcon.PAUSE)
        else:
            self.service_btn.setText("上线")
            self.service_btn.setIcon(FluentIcon.LINK)

        self._load_status_info()

    def _open_request_dialog(self):
        if not SERVICE_MANAGER.is_running(self.project_path):
            InfoBar.warning("服务未运行", "请先点击'上线'启动服务", parent=self.home)
            return
        url = SERVICE_MANAGER.get_url(self.project_path)
        if url:
            dialog = ServiceRequestDialog(self.project_path, url, self.home)
            dialog.exec()

    def update_status(self, is_running=False):
        if is_running:
            self.run_btn.setText("停止")
            self.run_btn.setIcon(FluentIcon.PAUSE)
            # self.run_btn.setEnabled(False)
        else:
            self.run_btn.setText("运行")
            self.run_btn.setIcon(FluentIcon.PLAY)
            # self.run_btn.setEnabled(True)

    def refresh(self):
        """被 ExportedProjectsPage._toggle_service 或 watchfiles 调用"""
        self._create_or_update_preview()
        self._load_status_info()
        self._update_service_button()

    def _load_status_info(self):
        # --- API 服务 ---
        if SERVICE_MANAGER.is_running(self.project_path):
            api_url = SERVICE_MANAGER.get_url(self.project_path) or "API服务：运行中"
            api_status = 'green'
        else:
            api_url = "API服务：未部署"
            api_status = 'gray'

        # --- MCP 工具 ---
        mcp_path = Path(self.project_path) / "mcp.json"
        if mcp_path.exists():
            try:
                with open(mcp_path, 'r', encoding='utf-8') as f:
                    mcp_content = json.dumps(json.load(f), ensure_ascii=False, indent=2)
                mcp_status = 'green'
            except:
                mcp_content = ""
                mcp_status = 'gray'
        else:
            mcp_content = ""
            mcp_status = 'gray'

        # --- 更新 UI ---
        self._update_dot_and_label(self.api_dot, self.api_label, api_status,
                                   api_url, copy_content=api_url if api_status == 'green' else None)
        self._update_dot_and_label(self.mcp_dot, self.mcp_label, mcp_status,
                                   "MCP工具：已注册" if mcp_status == 'green' else "MCP工具：未注册",
                                   copy_content=mcp_content)

    def _update_dot_and_label(self, dot, label, status, text, copy_content=None):
        color_map = {'green': '#4caf50', 'gray': '#9e9e9e', 'red': '#f44336'}
        dot.setStyleSheet(f"border-radius: 6px; background: {color_map.get(status, '#9e9e9e')};")
        label.setText(text)
        label.copy_content = copy_content or ""

    def mousePressEvent(self, event):
        # 排除按钮区域，防止冲突
        clicked_widget = self.childAt(event.pos())
        buttons = {
            self.run_btn, self.service_btn,
            self.edit_btn, self.view_log_btn, self.delete_btn,
            self.api_label, self.mcp_label
        }
        if clicked_widget not in buttons:
            if self.home and hasattr(self.home, 'on_card_clicked'):
                self.home.on_card_clicked(self)
            else:
                # 默认行为：打开文件夹（可选，建议保留）
                self._open_project_folder()
        else:
            super().mousePressEvent(event)

    def _open_project_folder(self):
        try:
            if os.name == 'nt':
                os.startfile(self.project_path)
            else:
                subprocess.call(['xdg-open', self.project_path])
        except Exception as e:
            if self.home:
                InfoBar.error("打开失败", str(e), parent=self.home)