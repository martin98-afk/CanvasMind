# -*- coding: utf-8 -*-
import os
import json
import subprocess
import sys
from pathlib import Path
from PyQt5.QtCore import Qt, QSize, QRect, QRectF
from PyQt5.QtGui import QFont, QGuiApplication, QPixmap, QPainter, QColor, QPen, QPainterPath
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QFrame, QDialog
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


class PreviewLabel(QLabel):
    """自定义预览标签，确保图片完整显示（Contain模式），支持双击放大"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScaledContents(False)
        self._pixmap = None
        self.setFixedSize(368, 160)
        # 设置背景样式，类似相框
        self.setStyleSheet(
            f"background-color: {'rgba(255, 255, 255, 0.05)' if isDarkTheme() else 'rgba(0, 0, 0, 0.03)'};"
            f"border-radius: 6px;"
            f"border: 1px solid {'#333' if isDarkTheme() else '#e0e0e0'};"
        )
        self.setAlignment(Qt.AlignCenter)
        self.setText("无预览图")  # 默认文本

    def set_image(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self.setText("") if pixmap and not pixmap.isNull() else self.setText("无预览图")
        self.update()  # 触发重绘

    def paintEvent(self, event):
        # 1. 绘制背景和边框（由样式表处理，或者这里也可以手动画）
        super().paintEvent(event)  # 绘制样式表定义的背景/文字

        if not self._pixmap or self._pixmap.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # 2. 计算保持比例的矩形 (Contain 模式)
        target_rect = QRectF(self.rect())
        # 留一点内边距，避免紧贴边框
        target_rect.adjust(4, 4, -4, -4)

        # 计算缩放后的尺寸
        scaled_size = self._pixmap.size().scaled(target_rect.size().toSize(), Qt.KeepAspectRatio)

        # 计算居中位置
        x = target_rect.x() + (target_rect.width() - scaled_size.width()) / 2
        y = target_rect.y() + (target_rect.height() - scaled_size.height()) / 2

        draw_rect = QRectF(x, y, scaled_size.width(), scaled_size.height())

        # 3. 绘制圆角图片
        path = QPainterPath()
        path.addRoundedRect(draw_rect, 4, 4)
        painter.setClipPath(path)
        painter.drawPixmap(draw_rect.toRect(), self._pixmap)

    def mouseDoubleClickEvent(self, event):
        if self._pixmap and not self._pixmap.isNull():
            # 双击显示大图弹窗
            self._show_lightbox()
        super().mouseDoubleClickEvent(event)

    def _show_lightbox(self):
        dialog = QDialog(self.window())
        dialog.setWindowTitle("预览图")
        dialog.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        dialog.resize(800, 600)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        img_lbl = QLabel()
        img_lbl.setAlignment(Qt.AlignCenter)
        # 大图也保持比例适应
        scaled_pix = self._pixmap.scaled(QSize(780, 580), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        img_lbl.setPixmap(scaled_pix)
        img_lbl.setStyleSheet("background-color: #1e1e1e;" if isDarkTheme() else "background-color: #f0f0f0;")

        layout.addWidget(img_lbl)
        dialog.exec()


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
        self.preview_label = None  # 改用自定义 Label
        self.is_selected = False
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedSize(400, 310)
        self.setBorderRadius(10)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(10)

        # === 顶部：标题 ===
        top_layout = QHBoxLayout()
        self.name_label = BodyLabel(self.project_name)
        self.name_label.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        self.name_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.name_label.setWordWrap(False)
        self.name_label.setToolTip(self.project_name)
        top_layout.addWidget(self.name_label)
        top_layout.addStretch()
        main_layout.addLayout(top_layout)

        # === 预览图 (使用自定义 PreviewLabel) ===
        self.preview_label = PreviewLabel(self)
        self.preview_label.setCursor(Qt.PointingHandCursor)
        self.preview_label.setToolTip("双击查看大图")
        main_layout.addWidget(self.preview_label)

        self._create_or_update_preview()

        # === 状态区 (API / MCP) ===
        status_container = QFrame()
        status_container.setStyleSheet("background-color: transparent;")
        status_layout = QVBoxLayout(status_container)
        status_layout.setContentsMargins(4, 0, 4, 0)
        status_layout.setSpacing(4)

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
        self.service_btn.clicked.connect(self._handle_service_toggle)
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
        """加载原图传给 PreviewLabel，由其内部处理缩放"""
        preview_path = Path(self.project_path) / "preview.png"
        if preview_path.exists():
            pixmap = QPixmap(str(preview_path))
            self.preview_label.set_image(pixmap)
        else:
            self.preview_label.set_image(None)

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
        self._create_or_update_preview()
        self._load_status_info()
        self._update_service_button()

    def _get_project_python_exe(self):
        """从项目导出的 workflow json 中读取记录的 Python 环境路径"""
        workflow_json = Path(self.project_path) / "model.workflow.json"
        if workflow_json.exists():
            try:
                with open(workflow_json, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 尝试从 runtime -> environment_exe 获取路径
                    exe_path = data.get("runtime", {}).get("environment_exe")
                    if exe_path and os.path.exists(exe_path):
                        return exe_path.replace("\\", "/")
            except Exception as e:
                logger.exception(f"解析项目 Python 环境失败: {e}")

        # 兜底方案：如果没找到或路径失效，返回当前运行环境
        return sys.executable.replace("\\", "/")

    def _handle_service_toggle(self):
        """处理上线/下线按钮逻辑"""
        try:
            if not SERVICE_MANAGER.is_running(self.project_path):
                # 1. 启动服务获取动态 URL
                url = SERVICE_MANAGER.start_service(self.project_path)

                # 2. 【关键：动态写入地址文件】
                url_file = Path(self.project_path) / "service_url.txt"
                url_file.write_text(url, encoding="utf-8")

                InfoBar.success("上线成功", f"服务已启动: {url}", parent=self.window())
            else:
                # 下线逻辑
                SERVICE_MANAGER.stop_service(self.project_path)
                # 下线时可以删除地址文件，防止误调
                url_file = Path(self.project_path) / "service_url.txt"
                if url_file.exists():
                    url_file.unlink()

                InfoBar.warning("服务已下线", "API 端口已释放", parent=self.window())

            # 3. 刷新卡片状态（会触发 _load_status_info）
            self.refresh()

        except Exception as e:
            InfoBar.error("操作失败", str(e), parent=self.window())

    def _load_status_info(self):
        """状态加载逻辑：没上线不给复制"""
        is_api_running = SERVICE_MANAGER.is_running(self.project_path)
        mcp_script_exists = (Path(self.project_path) / "mcp_instance.py").exists()

        # API 状态
        if is_api_running:
            api_url = SERVICE_MANAGER.get_url(self.project_path)
            api_status = 'green'
        else:
            api_url = "API服务：未上线"
            api_status = 'gray'

        # MCP 状态：只有 【API运行中】 且 【脚本已导出】 才允许复制
        if is_api_running and mcp_script_exists:
            project_python = self._get_project_python_exe()
            mcp_config = {
                "mcpServers": {
                    f"Canvas_{self.project_name}": {
                        "command": project_python.replace("\\", "/"),
                        "args": [str((Path(self.project_path) / "mcp_instance.py").absolute()).replace("\\", "/")]
                    }
                }
            }
            mcp_content = "MCP配置：点击复制 JSON"
            mcp_copy_data = json.dumps(mcp_config, indent=2, ensure_ascii=False)
            mcp_status = 'green'
        else:
            mcp_content = "MCP工具：请先上线服务" if mcp_script_exists else "MCP工具：未导出脚本"
            mcp_copy_data = ""  # 没上线，点击复制也没内容
            mcp_status = 'gray'

        self._update_dot_and_label(self.api_dot, self.api_label, api_status, api_url,
                                   copy_content=api_url if is_api_running else None)

        self._update_dot_and_label(self.mcp_dot, self.mcp_label, mcp_status, mcp_content,
                                   copy_content=mcp_copy_data)

    def _update_dot_and_label(self, dot, label, status, text, copy_content=None):
        # 颜色定义
        color_map = {
            'green': '#4caf50',
            'gray': '#d0d0d0' if not isDarkTheme() else '#666666'
        }

        # 更新圆点颜色
        dot.setStyleSheet(f"""
            min-width: 8px; min-height: 8px; max-width: 8px; max-height: 8px;
            border-radius: 4px; 
            background-color: {color_map.get(status, 'gray')};
        """)

        # 更新文字
        label.setText(text)

        # 重要：更新 ClickableLabel 内部的复制内容
        label.copy_content = copy_content or ""

        # 更新颜色样式
        if status == 'green':
            label.setStyleSheet("color: #4caf50; font-weight: bold; text-decoration: underline;")
            label.setToolTip("点击直接复制 MCP JSON 配置")
        else:
            color = "#666666" if not isDarkTheme() else "#aaaaaa"
            label.setStyleSheet(f"color: {color}; font-weight: normal;")
            label.setToolTip("当前项目缺少 mcp_instance.py")

    def set_selected(self, is_selected: bool):
        if self.is_selected == is_selected:
            return
        self.is_selected = is_selected
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.is_selected:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            c = themeColor()
            pen = QPen(c, 2)
            painter.setPen(pen)
            rect = self.rect().adjusted(1, 1, -1, -1)
            painter.drawRoundedRect(rect, 10, 10)

    def mousePressEvent(self, event):
        clicked_widget = self.childAt(event.pos())
        buttons = {
            self.run_btn, self.service_btn,
            self.edit_btn, self.view_log_btn, self.delete_btn,
            self.api_label, self.mcp_label
        }
        is_button_clicked = False
        if clicked_widget:
            curr = clicked_widget
            while curr and curr != self:
                if curr in buttons:
                    is_button_clicked = True
                    break
                curr = curr.parent()

        # 如果点击的是预览图，不认为是选中项目，让预览图自己处理双击事件
        # 但是这里要注意，单击预览图也应该选中卡片
        if clicked_widget == self.preview_label:
            # 允许向下传递以触发 Label 的双击，但同时也触发选卡片
            pass

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