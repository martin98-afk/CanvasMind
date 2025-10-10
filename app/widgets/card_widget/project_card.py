# -*- coding: utf-8 -*-
import os
import json
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QGuiApplication
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QGridLayout
from PyQt5.QtWidgets import QGraphicsDropShadowEffect
from qfluentwidgets import (
    CardWidget, BodyLabel, PrimaryPushButton,
    ToolButton, FluentIcon, InfoBar,
    ImageLabel
)


from app.utils.service_manager import SERVICE_MANAGER
from app.widgets.dialog_widget.service_request_dialog import ServiceRequestDialog


class ClickableLabel(BodyLabel):
    """可点击的标签，用于复制文本"""
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
        # 可选：向上冒泡通知父窗口显示提示
        InfoBar.success(
            title="已复制",
            content="服务地址已复制到剪贴板",
            parent=self.parent,
            duration=1500
        )


class ProjectCard(CardWidget):
    def __init__(self, project_path, parent=None):
        super().__init__(parent)
        self.project_path = project_path
        self.project_name = os.path.basename(project_path)
        self._setup_ui()

    def _setup_ui(self):
        # 更现代的高度和圆角
        self.setFixedSize(400, 320)
        self.setBorderRadius(12)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(12)
        self.setStyleSheet("""
            QWidget#ProjectCardTitle { font-size: 14px; font-weight: 600; }
            QLabel.projectMetaKey { color: #666; }
            QLabel.projectMetaVal { color: #333; }
        """)

        preview_path = os.path.join(self.project_path, "preview.png")
        if os.path.exists(preview_path):
            self.image_label = ImageLabel(preview_path, self)
            self.image_label.setFixedSize(250, 150)
            self.image_label.setBorderRadius(8, 8, 8, 8)  # ✅ 修复：四个角都设为8
        else:
            self.image_label = BodyLabel("无预览图")
            self.image_label.setFixedSize(250, 150)
            self.image_label.setAlignment(Qt.AlignCenter)
            self.image_label.setStyleSheet("""
                color: #999;
                background-color: #fafafa;
                border-radius: 8px;
                border: 1px dashed #e0e0e0;
                font-size: 12px;
            """)
        main_layout.addWidget(self.image_label, 0, Qt.AlignCenter)

        # === 项目名称 ===
        self.name_label = BodyLabel(self.project_name)
        self.name_label.setFont(QFont("Microsoft YaHei", 14, QFont.DemiBold))
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setObjectName("ProjectCardTitle")
        main_layout.addWidget(self.name_label)

        # === 元信息区域（网格，更清晰）===
        self.meta_grid = QGridLayout()
        self.meta_grid.setSpacing(6)
        self.meta_grid.setAlignment(Qt.AlignLeft)
        self._populate_meta_grid()
        main_layout.addLayout(self.meta_grid)

        # === 服务状态（动态，初始隐藏）===
        self.status_label = ClickableLabel(parent=self)
        self.status_label.setFont(QFont("Microsoft YaHei", 10))
        self.status_label.setVisible(False)
        main_layout.addWidget(self.status_label)

        main_layout.addStretch()  # 推动按钮到底部

        # === 按钮区域 ===
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(10)

        # 主操作按钮
        self.run_btn = PrimaryPushButton("运行", self, FluentIcon.PLAY)
        self.service_btn = PrimaryPushButton("上线", self, FluentIcon.LINK)
        self.request_btn = PrimaryPushButton("请求", self, FluentIcon.SEND)
        self.request_btn.setEnabled(False)

        # 工具按钮
        self.view_log_btn = ToolButton(FluentIcon.VIEW, self)
        self.open_folder_btn = ToolButton(FluentIcon.FOLDER, self)
        self.delete_btn = ToolButton(FluentIcon.DELETE, self)

        self.view_log_btn.setToolTip("查看日志")
        self.open_folder_btn.setToolTip("打开文件夹")
        self.delete_btn.setToolTip("删除项目")

        # 设置按钮样式：紧凑、统一高度
        for btn in [self.run_btn, self.service_btn, self.request_btn]:
            btn.setFixedHeight(28)
            btn.setFont(QFont("Microsoft YaHei", 9))

        for btn in [self.view_log_btn, self.open_folder_btn, self.delete_btn]:
            btn.setFixedSize(28, 28)

        # 布局
        left_box = QHBoxLayout()
        left_box.addWidget(self.run_btn)
        left_box.addWidget(self.service_btn)
        left_box.addWidget(self.request_btn)

        right_box = QHBoxLayout()
        right_box.setSpacing(8)
        right_box.addWidget(self.view_log_btn)
        right_box.addWidget(self.open_folder_btn)
        right_box.addWidget(self.delete_btn)

        btn_layout.addLayout(left_box)
        btn_layout.addStretch()
        btn_layout.addLayout(right_box)

        main_layout.addLayout(btn_layout)

        self._update_service_button()
        self.request_btn.clicked.connect(self._open_request_dialog)

        # 悬浮阴影
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(22)
        self._shadow.setXOffset(0)
        self._shadow.setYOffset(4)
        self._shadow.setColor(Qt.black)
        self.setGraphicsEffect(None)

    def enterEvent(self, event):
        try:
            self.setGraphicsEffect(self._shadow)
        except Exception:
            pass
        super().enterEvent(event)

    def leaveEvent(self, event):
        try:
            self.setGraphicsEffect(None)
        except Exception:
            pass
        super().leaveEvent(event)

    def _populate_meta_grid(self):
        def add_row(r, key, val):
            k = BodyLabel(key)
            k.setProperty("class", "projectMetaKey")
            v = BodyLabel(val)
            v.setProperty("class", "projectMetaVal")
            self.meta_grid.addWidget(k, r, 0)
            self.meta_grid.addWidget(v, r, 1)

        row = 0
        # 来自画布
        spec_file = os.path.join(self.project_path, "project_spec.json")
        if os.path.exists(spec_file):
            try:
                with open(spec_file, 'r', encoding='utf-8') as f:
                    spec = json.load(f)
                    original = spec.get("original_canvas") or spec.get("graph_name")
                    if original and original not in ("unknown", ""):
                        add_row(row, "来自", original); row += 1
            except Exception:
                pass

        # 创建时间
        try:
            stat = os.stat(self.project_path)
            create_time = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d")
            add_row(row, "创建", create_time); row += 1
        except Exception:
            pass

        # 依赖（最多3个）
        req_file = os.path.join(self.project_path, "requirements.txt")
        if os.path.exists(req_file):
            try:
                with open(req_file, 'r', encoding='utf-8') as f:
                    packages = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                    if packages:
                        deps = ", ".join(packages[:3])
                        if len(packages) > 3:
                            deps += f" +{len(packages) - 3}"
                        add_row(row, "依赖", deps); row += 1
            except Exception:
                pass

    def _update_service_button(self):
        if SERVICE_MANAGER.is_running(self.project_path):
            self.service_btn.setText("下线")
            self.service_btn.setIcon(FluentIcon.PAUSE)
            self.request_btn.setEnabled(True)
            url = SERVICE_MANAGER.get_url(self.project_path)
            if url:
                self.status_label.setText(url)  # 直接设文本
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
            InfoBar.warning("服务未运行", "请先点击'上线'启动服务", parent=self.parent())
            return
        url = SERVICE_MANAGER.get_url(self.project_path)
        if url:
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