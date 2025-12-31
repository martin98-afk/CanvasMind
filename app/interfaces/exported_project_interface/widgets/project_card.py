# -*- coding: utf-8 -*-
import os
import json
import subprocess
from pathlib import Path
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QFont, QGuiApplication, QPixmap, QPainter, QColor, QPen
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QFrame
from qfluentwidgets import (
    CardWidget, BodyLabel, PrimaryPushButton,
    FluentIcon, InfoBar, ImageLabel, TransparentToolButton, themeColor, isDarkTheme
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
        # 优化颜色，使其更符合现代 UI，深色模式适配
        color = "#4cc2ff" if isDarkTheme() else "#0078d4"
        self.setStyleSheet(f"color: {color}; text-decoration: none;")
        self.setFont(QFont("Microsoft YaHei", 9))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._copy_to_clipboard()
        super().mousePressEvent(event)

    def _copy_to_clipboard(self):
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(self.copy_content)
        InfoBar.success("已复制", "内容已复制到剪贴板", parent=self.parent, duration=1500)

    def enterEvent(self, event):
        self.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setFont(QFont("Microsoft YaHei", 9))
        super().leaveEvent(event)


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
        self.is_selected = False
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedSize(400, 310)  # 稍微增加高度以容纳新布局
        self.setBorderRadius(10)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(10)

        # === 顶部：标题 ===
        top_layout = QHBoxLayout()
        self.name_label = BodyLabel(self.project_name)
        self.name_label.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        self.name_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.name_label.setWordWrap(False)  # 不换行，溢出省略
        # 添加 tooltip 以防名字太长显示不全
        self.name_label.setToolTip(self.project_name)
        top_layout.addWidget(self.name_label)
        top_layout.addStretch()
        main_layout.addLayout(top_layout)

        # === 预览图 ===
        # 占位，后面 _create_or_update_preview 会填充
        self.preview_container = QLabel()
        self.preview_container.setFixedSize(368, 160)
        self.preview_container.setAlignment(Qt.AlignCenter)
        self.preview_container.setStyleSheet("background: transparent;")
        main_layout.addWidget(self.preview_container)

        self._create_or_update_preview()

        # === 状态区 (API / MCP) ===
        status_container = QFrame()
        status_container.setStyleSheet("background-color: transparent;")
        status_layout = QVBoxLayout(status_container)
        status_layout.setContentsMargins(4, 0, 4, 0)
        status_layout.setSpacing(4)

        # 辅助函数：创建一行状态
        def create_status_row(label_text):
            row = QHBoxLayout()
            row.setSpacing(8)
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet("border-radius: 4px; background: gray;")

            lbl = ClickableLabel(label_text, self)
            row.addWidget(dot)
            row.addWidget(lbl, 1)
            return row, dot, lbl

        api_row, self.api_dot, self.api_label = create_status_row("API服务：未部署")
        mcp_row, self.mcp_dot, self.mcp_label = create_status_row("MCP工具：未注册")

        status_layout.addLayout(api_row)
        status_layout.addLayout(mcp_row)
        main_layout.addWidget(status_container)

        # === 底部按钮区 ===
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 4, 0, 0)
        btn_layout.setSpacing(8)

        self.run_btn = PrimaryPushButton("运行", self, FluentIcon.PLAY)
        self.service_btn = PrimaryPushButton("上线", self, FluentIcon.LINK)
        # 按钮样式微调
        for btn in [self.run_btn, self.service_btn]:
            btn.setFixedHeight(30)
            btn.setFixedWidth(80)

        self.edit_btn = TransparentToolButton(FluentIcon.EDIT, self)
        self.view_log_btn = TransparentToolButton(FluentIcon.VIEW, self)
        self.delete_btn = TransparentToolButton(FluentIcon.DELETE, self)

        for btn in [self.edit_btn, self.view_log_btn, self.delete_btn]:
            btn.setFixedSize(30, 30)
            btn.setIconSize(QSize(16, 16))

        self.view_log_btn.setToolTip("查看日志")
        self.delete_btn.setToolTip("删除项目")
        self.edit_btn.setToolTip("编辑信息")

        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.service_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.view_log_btn)
        btn_layout.addWidget(self.delete_btn)

        main_layout.addLayout(btn_layout)

        self._update_service_button()
        self.setCursor(Qt.PointingHandCursor)

    def _create_or_update_preview(self):
        """刷新预览图，强制重载 QPixmap 避免缓存"""
        preview_path = Path(self.project_path) / "preview.png"

        pixmap = QPixmap()
        has_image = False

        if preview_path.exists():
            # 显式加载 pixmap，而不是让控件自己去缓存
            loaded = pixmap.load(str(preview_path))
            if loaded:
                has_image = True
                # 保持比例填充，缩放质量平滑
                pixmap = pixmap.scaled(
                    self.preview_container.size(),
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation
                )

        if has_image:
            self.preview_container.setPixmap(pixmap)
            # 设置裁剪，防止 KeepAspectRatioByExpanding 超出边界
            # 注意：QLabel 本身不支持 border-radius 裁剪图片，这里简单处理
            # 更好的做法是自定义 paintEvent 绘制圆角图片，或者样式表
            # 这里为了不改动太多代码，保持图片显示即可，样式表辅助
            self.preview_container.setStyleSheet(
                f"border-radius: 6px; border: 1px solid #e0e0e0;"
                if not isDarkTheme() else
                f"border-radius: 6px; border: 1px solid #333;"
            )
        else:
            self.preview_container.setPixmap(QPixmap())
            self.preview_container.setText("无预览图")
            self.preview_container.setStyleSheet("""
                color: #999;
                background-color: rgba(128, 128, 128, 0.1);
                border-radius: 6px;
                border: 1px dashed #bbb;
                font-size: 13px;
            """)

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
        else:
            self.run_btn.setText("运行")
            self.run_btn.setIcon(FluentIcon.PLAY)

    def refresh(self):
        """被 ExportedProjectsPage 调用"""
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
                # 简单验证 json 有效性
                with open(mcp_path, 'r', encoding='utf-8') as f:
                    json.load(f)
                mcp_content = "点击复制配置"
                mcp_status = 'green'
            except:
                mcp_content = ""
                mcp_status = 'gray'
        else:
            mcp_content = ""
            mcp_status = 'gray'

        self._update_dot_and_label(self.api_dot, self.api_label, api_status,
                                   api_url, copy_content=api_url if api_status == 'green' else None)
        self._update_dot_and_label(self.mcp_dot, self.mcp_label, mcp_status,
                                   "MCP工具：已注册" if mcp_status == 'green' else "MCP工具：未注册",
                                   copy_content=mcp_content if mcp_status == 'green' else None)

    def _update_dot_and_label(self, dot, label, status, text, copy_content=None):
        color_map = {'green': '#4caf50', 'gray': '#d0d0d0' if not isDarkTheme() else '#666666'}
        dot.setStyleSheet(f"""
            min-width: 8px; min-height: 8px; max-width: 8px; max-height: 8px;
            border-radius: 4px; 
            background-color: {color_map.get(status, 'gray')};
        """)
        label.setText(text)
        label.copy_content = copy_content or ""

        # 如果是绿色状态，加深标签文字颜色
        if status == 'green':
            label.setStyleSheet("color: #4caf50; font-weight: bold;")
        else:
            # 恢复默认
            color = "#666666" if not isDarkTheme() else "#aaaaaa"
            label.setStyleSheet(f"color: {color}; font-weight: normal;")

    def set_selected(self, is_selected: bool):
        """设置选中状态并刷新界面"""
        if self.is_selected == is_selected:
            return
        self.is_selected = is_selected
        self.update()  # 触发 paintEvent 重绘

    def paintEvent(self, event):
        """重写绘制事件，绘制选中状态的边框"""
        super().paintEvent(event)
        if self.is_selected:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            # 使用当前主题色
            c = themeColor()
            pen = QPen(c, 2)  # 2像素宽度的边框
            painter.setPen(pen)
            # 绘制圆角矩形边框，稍微内缩一点避免被切掉
            rect = self.rect().adjusted(1, 1, -1, -1)
            painter.drawRoundedRect(rect, 10, 10)

    def mousePressEvent(self, event):
        clicked_widget = self.childAt(event.pos())
        # 定义需要拦截点击事件的控件类型
        # 注意：childAt 可能返回 label 内部的对象，所以通常比较对象引用
        buttons = {
            self.run_btn, self.service_btn,
            self.edit_btn, self.view_log_btn, self.delete_btn,
            self.api_label, self.mcp_label
        }

        # 简单判断：如果点击的不是功能按钮，则认为是选中卡片
        is_button_clicked = False
        if clicked_widget:
            # 向上查找父级看是否是按钮
            curr = clicked_widget
            while curr and curr != self:
                if curr in buttons:
                    is_button_clicked = True
                    break
                curr = curr.parent()

        if not is_button_clicked:
            if self.home and hasattr(self.home, 'on_card_clicked'):
                self.home.on_card_clicked(self)

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