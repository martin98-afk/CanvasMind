# -*- coding: utf-8 -*-
import os
import json
import subprocess
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QGuiApplication, QPixmap
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QGridLayout, QGraphicsDropShadowEffect
from qfluentwidgets import (
    CardWidget, BodyLabel, PrimaryPushButton,
    ToolButton, FluentIcon, InfoBar, ImageLabel
)

from app.utils.service_manager import SERVICE_MANAGER
from app.widgets.dialog_widget.service_request_dialog import ServiceRequestDialog


class ClickableLabel(BodyLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text)
        self.parent = parent
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setCursor(Qt.PointingHandCursor)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("color: #1e88e5; text-decoration: underline;")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.copy_to_clipboard()
        super().mousePressEvent(event)

    def copy_to_clipboard(self):
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(self.text())
        InfoBar.success("已复制", "服务地址已复制到剪贴板", parent=self.parent, duration=1500)


class ProjectCard(CardWidget):
    def __init__(self, project_path, parent=None):
        super().__init__(parent)
        self.project_path = os.path.abspath(project_path)
        self.project_name = os.path.basename(self.project_path)
        self.home = parent
        self._setup_ui()
        self.setCursor(Qt.PointingHandCursor)

    def _setup_ui(self):
        self.setFixedSize(400, 330)
        self.setBorderRadius(12)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(12)
        self.setStyleSheet("""
            QWidget#ProjectCardTitle { font-size: 14px; font-weight: 600; }
            QLabel.projectMetaKey { color: #666; }
            QLabel.projectMetaVal { color: #333; }
        """)

        # 项目名称（固定）
        self.name_label = BodyLabel(self.project_name)
        self.name_label.setFont(QFont("Microsoft YaHei", 14, QFont.DemiBold))
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setWordWrap(True)
        self.name_label.setObjectName("ProjectCardTitle")
        main_layout.addWidget(self.name_label)

        # 预览图（可刷新）
        self.image_label = None
        self._create_or_update_preview()

        # 元信息（可刷新）
        self.meta_grid = QGridLayout()
        self.meta_grid.setSpacing(6)
        main_layout.addLayout(self.meta_grid)
        self._populate_meta_grid()

        # 服务状态（可刷新）
        self.status_label = ClickableLabel(parent=self)
        self.status_label.setFont(QFont("Microsoft YaHei", 10))
        self.status_label.setVisible(False)
        main_layout.addWidget(self.status_label)

        main_layout.addStretch()

        # 按钮区（固定）
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.run_btn = PrimaryPushButton("运行", self, FluentIcon.PLAY)
        self.service_btn = PrimaryPushButton("上线", self, FluentIcon.LINK)
        self.request_btn = PrimaryPushButton("请求", self, FluentIcon.SEND)
        self.request_btn.setEnabled(False)

        self.edit_btn = ToolButton(FluentIcon.EDIT, self)
        self.view_log_btn = ToolButton(FluentIcon.VIEW, self)
        self.delete_btn = ToolButton(FluentIcon.DELETE, self)

        self.view_log_btn.setToolTip("查看日志")
        self.delete_btn.setToolTip("删除项目")

        for btn in [self.run_btn, self.service_btn, self.request_btn]:
            btn.setFixedHeight(28)
            btn.setFont(QFont("Microsoft YaHei", 9))
        for btn in [self.edit_btn, self.view_log_btn, self.delete_btn]:
            btn.setFixedSize(28, 28)

        left_box = QHBoxLayout()
        left_box.addWidget(self.run_btn)
        left_box.addWidget(self.service_btn)
        left_box.addWidget(self.request_btn)

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
        self.request_btn.clicked.connect(self._open_request_dialog)

        # 阴影
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(22)
        self._shadow.setXOffset(0)
        self._shadow.setYOffset(4)
        self._shadow.setColor(Qt.black)
        self.setGraphicsEffect(None)

    def _create_or_update_preview(self):
        """创建或更新预览图控件"""
        preview_path = os.path.join(self.project_path, "preview.png")
        has_preview = os.path.exists(preview_path)
        # === 彻底移除旧的 image_label（无论类型）===
        if self.image_label:
            # 从布局中移除
            main_layout = self.layout()
            main_layout.removeWidget(self.image_label)
            # 立即删除
            self.image_label.deleteLater()
            self.image_label = None

        # === 创建新控件 ===
        if has_preview:
            self.image_label = ImageLabel(preview_path, self)
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

        # 插入到 name_label 下方（索引 1）
        main_layout = self.layout()
        main_layout.insertWidget(1, self.image_label, 0, Qt.AlignCenter)

    def _clear_meta_grid(self):
        while self.meta_grid.count():
            child = self.meta_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _populate_meta_grid(self):
        self._clear_meta_grid()
        row = 0

        spec_file = os.path.join(self.project_path, "project_spec.json")
        if os.path.exists(spec_file):
            try:
                with open(spec_file, 'r', encoding='utf-8') as f:
                    spec = json.load(f)
                    original = spec.get("original_canvas") or spec.get("graph_name")
                    if original and original not in ("unknown", ""):
                        self._add_meta_row(row, "来自", original)
                        row += 1
            except Exception:
                pass

        try:
            stat = os.stat(self.project_path)
            create_time = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d")
            self._add_meta_row(row, "创建", create_time)
            row += 1
        except Exception:
            pass

        req_file = os.path.join(self.project_path, "requirements.txt")
        if os.path.exists(req_file):
            try:
                with open(req_file, 'r', encoding='utf-8') as f:
                    packages = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                    if packages:
                        deps = ", ".join(packages[:3])
                        if len(packages) > 3:
                            deps += f" +{len(packages) - 3}"
                        self._add_meta_row(row, "依赖", deps)
                        row += 1
            except Exception:
                pass

    def _add_meta_row(self, row, key, val):
        k = BodyLabel(key)
        k.setProperty("class", "projectMetaKey")
        v = BodyLabel(val)
        v.setProperty("class", "projectMetaVal")
        self.meta_grid.addWidget(k, row, 0)
        self.meta_grid.addWidget(v, row, 1)

    def _update_service_button(self):
        if SERVICE_MANAGER.is_running(self.project_path):
            self.service_btn.setText("下线")
            self.service_btn.setIcon(FluentIcon.PAUSE)
            self.request_btn.setEnabled(True)
            url = SERVICE_MANAGER.get_url(self.project_path)
            if url:
                self.status_label.setText(url)
                self.status_label.setVisible(True)
            else:
                self.status_label.setVisible(False)
        else:
            self.service_btn.setText("上线")
            self.service_btn.setIcon(FluentIcon.LINK)
            self.request_btn.setEnabled(False)
            self.status_label.setVisible(False)

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
            self.run_btn.setEnabled(False)
        else:
            self.run_btn.setText("运行")
            self.run_btn.setIcon(FluentIcon.PLAY)
            self.run_btn.setEnabled(True)

    # ✅ ===== 新增：增量刷新接口 =====
    def refresh(self):
        """被 watchfiles 事件调用，刷新卡片内容"""
        # 1. 更新预览图
        self._create_or_update_preview()
        # 2. 更新元信息
        self._populate_meta_grid()
        # 3. 更新服务状态按钮
        self._update_service_button()

    # ✅ 点击卡片打开文件夹
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._open_project_folder()
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