# -*- coding: utf-8 -*-
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, List

from PyQt5.QtCore import Qt, QSize, QUrl, pyqtSignal
from PyQt5.QtGui import QPixmap, QDesktopServices
from PyQt5.QtWidgets import (QVBoxLayout, QWidget, QHBoxLayout, QTextEdit,
                             QFrame, QLabel, QScrollArea, QSizePolicy,
                             QGridLayout, QSpacerItem, QApplication, QTreeWidgetItem)
from qfluentwidgets import (TransparentToolButton, FluentIcon, IconWidget,
                            CardWidget, TreeWidget)

from app.utils.utils import get_icon


# === 工具函数 ===
def is_image_path(value: Any) -> bool:
    """判断值是否为有效的本地图片路径"""
    if not isinstance(value, str):
        return False
    path = Path(value)
    return path.exists() and path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff'}


def extract_image_paths(data: Any, max_count: int = 4) -> List[str]:
    """递归提取数据中的图片路径（最多 max_count 个）"""
    paths = []

    def _extract(obj):
        if len(paths) >= max_count:
            return
        if isinstance(obj, str) and is_image_path(obj):
            paths.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                _extract(v)
        elif isinstance(obj, list):
            for item in obj:
                _extract(item)

    _extract(data)
    return paths[:max_count]


# === 自定义组件 ===
class StatusBadge(QLabel):
    """胶囊形状的标签，用于显示触发类型"""

    def __init__(self, text, color="#404040", text_color="#E0E0E0", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: {text_color};
                border-radius: 4px;
                padding: 2px 8px;
                font-family: 'Segoe UI', 'Microsoft YaHei';
                font-size: 11px;
                font-weight: bold;
            }}
        """)
        self.adjustSize()


class CodeViewer(QTextEdit):
    """仿IDE风格的代码/JSON查看器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E; 
                color: #D4D4D4;
                border-radius: 6px;
                border: 1px solid #3E3E42;
                font-family: 'Consolas', 'JetBrains Mono', 'Monospace';
                font-size: 11px;
                padding: 8px;
                selection-background-color: #264F78;
                selection-color: #FFFFFF;
            }
            QTextEdit:hover {
                border: 1px solid #505050;
            }
        """)


class ImagePreviewWidget(QWidget):
    """图片预览组件 - 显示缩略图并支持点击放大"""

    imageClicked = pyqtSignal(str)  # 发送被点击的图片路径

    def __init__(self, image_paths: List[str], parent=None):
        super().__init__(parent)
        self.image_paths = image_paths
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(6)

        # 标题
        title = QLabel("🖼️ PREVIEW")
        title.setStyleSheet("color: #808080; font-weight: bold; font-size: 11px; padding-left: 2px;")
        layout.addWidget(title)

        # 图片网格
        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)

        for idx, path in enumerate(self.image_paths):
            # 创建可点击的图片容器
            container = QWidget()
            container.setCursor(Qt.PointingHandCursor)
            container.setStyleSheet("""
                QWidget {
                    border: 1px solid #3E3E42;
                    border-radius: 4px;
                    background-color: #252526;
                }
                QWidget:hover {
                    border: 1px solid #505050;
                    background-color: #2A2A2B;
                }
            """)

            img_layout = QVBoxLayout(container)
            img_layout.setContentsMargins(4, 4, 4, 4)

            # 缩略图
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                img_label = QLabel()
                img_label.setPixmap(pixmap)
                img_label.setAlignment(Qt.AlignCenter)
                img_layout.addWidget(img_label)

            # 文件名（截断显示）
            name_label = QLabel(os.path.basename(path))
            name_label.setStyleSheet("color: #A0A0A0; font-size: 9px; padding: 2px;")
            name_label.setAlignment(Qt.AlignCenter)
            name_label.setWordWrap(True)
            img_layout.addWidget(name_label)

            # 点击事件
            container.mousePressEvent = lambda e, p=path: self.imageClicked.emit(p)

            # 添加到网格（2列布局）
            row = idx // 2
            col = idx % 2
            grid.addWidget(container, row, col)

        # 添加弹性空间
        if len(self.image_paths) < 4:
            grid.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum), 0, 2)

        layout.addLayout(grid)
        layout.addStretch(1)


class DataTreeWidget(TreeWidget):
    """增强型树形数据查看器，支持多种数据类型渲染"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setStyleSheet("""
            QTreeWidget {
                background-color: #1E1E1E;
                border-radius: 6px;
                border: 1px solid #3E3E42;
                color: #D4D4D4;
                font-family: 'Consolas', 'JetBrains Mono', 'Monospace';
                font-size: 11px;
                show-decoration-selected: 0;
            }
            QTreeWidget::item {
                padding: 4px;
                border-radius: 3px;
            }
            QTreeWidget::item:hover {
                background-color: #2A2A2A;
            }
            QTreeWidget::branch {
                background: transparent;
            }
        """)
        self.setIndentation(15)
        self.setAlternatingRowColors(False)
        self.setVerticalScrollMode(self.ScrollPerPixel)
        self.setHorizontalScrollMode(self.ScrollPerPixel)

    def populate(self, data: Any):
        """递归填充树形结构"""
        self.clear()
        self._add_item(data, "root", self.invisibleRootItem())

    def _add_item(self, value: Any, key: str, parent: QTreeWidgetItem):
        # 处理 None 值
        if value is None:
            item = QTreeWidgetItem(parent, [f"{key}: null"])
            item.setForeground(0, Qt.gray)
            return

        # 处理基础类型
        if isinstance(value, (str, int, float, bool)):
            display = json.dumps(value, ensure_ascii=False) if isinstance(value, str) else str(value)
            item = QTreeWidgetItem(parent, [f"{key}: {display}"])

            # 类型着色
            if isinstance(value, str):
                item.setForeground(0, Qt.green)
            elif isinstance(value, bool):
                item.setForeground(0, Qt.cyan)
            elif isinstance(value, (int, float)):
                item.setForeground(0, Qt.magenta)
            return

        # 处理字典
        if isinstance(value, dict):
            item = QTreeWidgetItem(parent, [f"{key} {{...}}" if key != "root" else "{...}"])
            item.setForeground(0, Qt.yellow)
            item.setExpanded(True if key == "root" else False)

            for k, v in sorted(value.items()):
                self._add_item(v, str(k), item)
            return

        # 处理列表
        if isinstance(value, list):
            count = len(value)
            item = QTreeWidgetItem(parent, [f"{key} [{count}]" if key != "root" else f"[{count}]"])
            item.setForeground(0, Qt.cyan)
            item.setExpanded(False)

            # 只展开小列表
            if count <= 5:
                item.setExpanded(True)
                for idx, v in enumerate(value):
                    self._add_item(v, f"[{idx}]", item)
            else:
                # 添加前3项预览
                for idx in range(min(3, count)):
                    self._add_item(value[idx], f"[{idx}]", item)
                if count > 3:
                    more = QTreeWidgetItem(item, [f"... and {count - 3} more items"])
                    more.setForeground(0, Qt.gray)
            return

        # 其他类型
        display = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
        item = QTreeWidgetItem(parent, [f"{key}: {display}"])
        item.setForeground(0, Qt.gray)


class ExecutionResultCard(CardWidget):
    """
    ComfyUI 风格执行记录卡片 - 优化版
    特性：
    - 智能图片预览（自动检测输出中的图片路径）
    - 树形结构数据展示（提升复杂数据可读性）
    - 响应式高度（内容自适应，最大高度限制）
    - 图片点击放大（使用系统默认图片查看器）
    - 性能优化（仅展开时加载资源）
    """

    def __init__(self, record, parent=None):
        super().__init__(parent)
        self.record = record
        self.is_expanded = False
        self.image_previews: List[str] = []

        self._setup_comfy_style()
        self.setup_ui()
        self.update_data(record)

    def _setup_comfy_style(self):
        self.setBorderRadius(10)
        self.status_colors = {
            "running": "#2196F3",  # 蓝
            "success": "#4CAF50",  # 绿
            "failed": "#F44336",  # 红
            "cancelled": "#9E9E9E"  # 灰
        }
        self.bg_color = "#2B2D30"
        self.setStyleSheet(f"""
            ExecutionResultCard {{
                background-color: {self.bg_color};
                border: 1px solid #3E3E42;
                border-radius: 10px;
            }}
            QLabel {{ color: #E0E0E0; }}
            ExecutionResultCard:hover {{
                border: 1px solid #505050;
            }}
        """)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # === Header ===
        self.header_widget = QWidget()
        self.header_widget.setFixedHeight(68)
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(16, 0, 16, 0)
        header_layout.setSpacing(14)

        # A. 状态条 (左侧装饰条)
        self.status_strip = QFrame()
        self.status_strip.setFixedWidth(4)
        self.status_strip.setStyleSheet(f"background-color: {self.status_colors['running']}; border-radius: 2px;")
        header_layout.addWidget(self.status_strip)

        # B. 状态图标
        self.status_icon = IconWidget(FluentIcon.INFO)
        self.status_icon.setFixedSize(20, 20)
        header_layout.addWidget(self.status_icon)

        # C. 核心信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        info_layout.setAlignment(Qt.AlignVCenter)

        self.name_label = QLabel()
        self.name_label.setStyleSheet("font-weight: 600; font-size: 14px; color: #FFFFFF;")
        self.id_label = QLabel()
        self.id_label.setStyleSheet("color: #888888; font-family: 'Consolas'; font-size: 10px;")

        info_layout.addWidget(self.name_label)
        info_layout.addWidget(self.id_label)
        header_layout.addLayout(info_layout)

        header_layout.addStretch(1)

        # D. 元数据
        meta_layout = QVBoxLayout()
        meta_layout.setSpacing(4)
        meta_layout.setAlignment(Qt.AlignVCenter | Qt.AlignRight)

        self.trigger_badge = StatusBadge("MANUAL")
        meta_layout.addWidget(self.trigger_badge, 0, Qt.AlignRight)

        self.duration_label = QLabel("--:--:--")
        self.duration_label.setStyleSheet("color: #A0A0A0; font-size: 11px; font-family: 'Consolas';")
        meta_layout.addWidget(self.duration_label, 0, Qt.AlignRight)

        header_layout.addLayout(meta_layout)

        # E. 展开/折叠按钮
        self.expand_btn = TransparentToolButton(get_icon("展开"), self)
        self.expand_btn.setFixedSize(32, 32)
        self.expand_btn.setIconSize(QSize(16, 16))
        self.expand_btn.clicked.connect(self.toggle_expand)
        header_layout.addWidget(self.expand_btn)

        main_layout.addWidget(self.header_widget)

        # === Details (可滚动区域) ===
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.detail_widget = QWidget()
        self.detail_widget.setStyleSheet(
            "background-color: #252526; border-bottom-left-radius: 10px; border-bottom-right-radius: 10px;")
        self.detail_layout = QVBoxLayout(self.detail_widget)
        self.detail_layout.setContentsMargins(16, 12, 16, 16)
        self.detail_layout.setSpacing(12)

        # 输入区域
        self._create_section("INPUT", self.detail_layout, is_input=True)

        # 输出区域（包含图片预览）
        self._create_section("OUTPUT", self.detail_layout, is_input=False)

        # 错误日志
        self.error_container = QWidget()
        self.error_container.setVisible(False)
        error_layout = QVBoxLayout(self.error_container)
        error_layout.setContentsMargins(0, 0, 0, 0)
        error_layout.setSpacing(4)

        error_title = QLabel("⚠️ ERROR LOG")
        error_title.setStyleSheet("color: #F44336; font-weight: bold; font-size: 11px;")
        error_layout.addWidget(error_title)

        self.error_view = CodeViewer()
        self.error_view.setStyleSheet(
            self.error_view.styleSheet() + "border: 1px solid #602020; background-color: #2D1010;")
        self.error_view.setMaximumHeight(100)
        error_layout.addWidget(self.error_view)

        self.detail_layout.addWidget(self.error_container)
        self.detail_layout.addStretch(1)

        self.scroll_area.setWidget(self.detail_widget)
        self.scroll_area.setVisible(False)
        main_layout.addWidget(self.scroll_area)

    def _create_section(self, title: str, parent_layout: QVBoxLayout, is_input: bool = True) -> QWidget:
        """创建带标题的内容区域"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 标题
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #808080; font-weight: bold; font-size: 11px; padding-left: 2px;")
        layout.addWidget(title_label)

        # 内容容器
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        # 树形视图（默认）
        tree_view = DataTreeWidget()
        tree_view.setMinimumHeight(60)
        tree_view.setMaximumHeight(180 if is_input else 220)
        content_layout.addWidget(tree_view)

        # 原始JSON视图（可选）
        json_view = CodeViewer()
        json_view.setVisible(False)
        json_view.setMaximumHeight(180 if is_input else 220)
        content_layout.addWidget(json_view)

        # 切换按钮
        btn_container = QWidget()
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)

        toggle_btn = TransparentToolButton(FluentIcon.VIEW, self)
        toggle_btn.setFixedSize(24, 24)
        toggle_btn.setToolTip("Toggle JSON view")
        toggle_btn.clicked.connect(lambda: self._toggle_view_mode(tree_view, json_view, toggle_btn, is_input))
        btn_layout.addWidget(toggle_btn)
        btn_layout.addStretch(1)

        layout.addWidget(content_container)
        layout.addWidget(btn_container)

        parent_layout.addWidget(container)

        # 保存引用
        if is_input:
            self.input_tree = tree_view
            self.input_json = json_view
            self.input_toggle_btn = toggle_btn
        else:
            self.output_tree = tree_view
            self.output_json = json_view
            self.output_toggle_btn = toggle_btn
            self.output_content = content_container

        return container

    def _toggle_view_mode(self, tree_view: DataTreeWidget, json_view: CodeViewer, btn: TransparentToolButton,
                          is_input: bool):
        """切换树形视图和JSON视图"""
        is_tree_visible = tree_view.isVisible()
        tree_view.setVisible(not is_tree_visible)
        json_view.setVisible(is_tree_visible)

        # 更新按钮图标
        btn.setIcon(FluentIcon.CODE if is_tree_visible else FluentIcon.VIEW)
        btn.setToolTip("View as JSON" if is_tree_visible else "View as Tree")

        # 重新渲染当前视图
        data = self.record.input_data if is_input else self.record.output_data
        if is_tree_visible:
            try:
                json_view.setText(json.dumps(data, indent=2, ensure_ascii=False))
            except Exception as e:
                json_view.setText(f"Error rendering JSON: {str(e)}")
        else:
            tree_view.populate(data)

    def update_data(self, record):
        """更新卡片数据"""
        self.record = record
        self.name_label.setText(record.canvas_name or "Untitled Workflow")

        eid_short = record.execution_id[:8] if record.execution_id else "N/A"
        self.id_label.setText(f"Execution ID: {eid_short}")

        trigger_text = record.trigger_type.upper() if record.trigger_type else "MANUAL"
        self.trigger_badge.setText(trigger_text)
        self.trigger_badge.setStyleSheet(self.trigger_badge.styleSheet().replace("#404040", "#303030"))

        self.refresh_duration()
        self._update_status_visuals(record.status)

        # 仅在展开状态时更新详细内容
        if self.is_expanded:
            self._render_details()

    def refresh_duration(self):
        """更新执行时长显示"""
        if not self.record.start_time:
            self.duration_label.setText("--:--:--")
            return

        start_dt = datetime.fromtimestamp(self.record.start_time)
        time_str = start_dt.strftime("%H:%M:%S")

        if self.record.end_time:
            duration = self.record.end_time - self.record.start_time
            self.duration_label.setText(f"{time_str} · {duration:.2f}s")
        else:
            duration = time.time() - self.record.start_time
            self.duration_label.setText(f"{time_str} · {duration:.1f}s...")

    def _update_status_visuals(self, status: str):
        """更新状态相关UI元素 - 修复：移除 setSpin 调用"""
        color_hex = self.status_colors.get(status, "#9E9E9E")

        # 更新状态条
        radius = "border-bottom-left-radius: 0px;" if self.is_expanded else "border-bottom-left-radius: 10px;"
        self.status_strip.setStyleSheet(f"""
            background-color: {color_hex}; 
            border-top-left-radius: 10px; 
            {radius}
        """)

        # 更新图标和文字（移除所有 setSpin 调用）
        if status == "running":
            self.status_icon.setIcon(FluentIcon.UPDATE)  # 使用 UPDATE 图标表示运行中
            self.name_label.setStyleSheet(f"font-weight: 600; font-size: 14px; color: {color_hex};")
        elif status == "success":
            self.status_icon.setIcon(FluentIcon.COMPLETED)
            self.name_label.setStyleSheet("font-weight: 600; font-size: 14px; color: #FFFFFF;")
        elif status == "failed":
            self.status_icon.setIcon(get_icon("失败"))
            self.name_label.setStyleSheet("font-weight: 600; font-size: 14px; color: #F44336;")
        else:  # cancelled
            self.status_icon.setIcon(FluentIcon.CANCEL)
            self.name_label.setStyleSheet("font-weight: 600; font-size: 14px; color: #9E9E9E;")

        self.status_icon.setStyleSheet(f"color: {color_hex};")

    def _render_details(self):
        """渲染详细内容（仅在展开时调用）"""
        # 清理旧的图片预览
        if hasattr(self, 'output_content') and self.output_content.layout():
            for i in reversed(range(self.output_content.layout().count())):
                widget = self.output_content.layout().itemAt(i).widget()
                if isinstance(widget, ImagePreviewWidget):
                    widget.deleteLater()

        # 提取图片路径
        self.image_previews = extract_image_paths(self.record.output_data)

        # 添加图片预览（如果有）
        if self.image_previews and hasattr(self, 'output_content'):
            preview_widget = ImagePreviewWidget(self.image_previews)
            preview_widget.imageClicked.connect(self._open_image_fullscreen)
            self.output_content.layout().insertWidget(0, preview_widget)

        # 渲染输入数据（默认树形视图）
        if hasattr(self, 'input_tree') and self.input_tree.isVisible():
            self.input_tree.populate(self.record.input_data)
        elif hasattr(self, 'input_json'):
            try:
                self.input_json.setText(json.dumps(self.record.input_data, indent=2, ensure_ascii=False))
            except:
                self.input_json.setText(str(self.record.input_data))

        # 渲染输出数据（默认树形视图）
        if hasattr(self, 'output_tree') and self.output_tree.isVisible():
            self.output_tree.populate(self.record.output_data)
        elif hasattr(self, 'output_json'):
            try:
                self.output_json.setText(json.dumps(self.record.output_data, indent=2, ensure_ascii=False))
            except:
                self.output_json.setText(str(self.record.output_data))

        # 错误日志
        if self.record.error_msg:
            self.error_container.setVisible(True)
            self.error_view.setText(self.record.error_msg)
        else:
            self.error_container.setVisible(False)

    def _open_image_fullscreen(self, path: str):
        """使用系统默认应用打开图片"""
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception as e:
            print(f"Failed to open image: {e}")

    def toggle_expand(self):
        """切换展开/折叠状态"""
        self.is_expanded = not self.is_expanded
        self.scroll_area.setVisible(self.is_expanded)
        self.expand_btn.setIcon(get_icon("折叠" if self.is_expanded else "展开"))

        # 更新状态条圆角
        self._update_status_visuals(self.record.status)

        # 展开时渲染内容
        if self.is_expanded:
            self._render_details()
            # 设置最大高度避免卡片过高
            screen_height = QApplication.primaryScreen().availableGeometry().height()
            max_height = min(600, int(screen_height * 0.7))
            self.setMaximumHeight(68 + max_height)
        else:
            self.setMaximumHeight(68)
            self.setFixedHeight(68)  # 保持折叠状态固定高度