# -*- coding: utf-8 -*-
import json
import time
from datetime import datetime

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import (QVBoxLayout, QWidget, QHBoxLayout, QTextEdit,
                             QFrame, QLabel)
from qfluentwidgets import (TransparentToolButton, FluentIcon, IconWidget,
                            CardWidget)

from app.utils.utils import get_icon


# === 自定义样式组件 ===

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
        # ComfyUI 风格的输入框：深灰背景，Consolas字体
        self.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E; 
                color: #D4D4D4;
                border-radius: 6px;
                border: 1px solid #3E3E42;
                font-family: 'Consolas', 'JetBrains Mono', 'Monospace';
                font-size: 11px;
                padding: 5px;
            }
            QTextEdit:hover {
                border: 1px solid #505050;
            }
        """)


class ExecutionResultCard(CardWidget):
    """
    ComfyUI 风格执行记录卡片
    """

    def __init__(self, record, parent=None):
        super().__init__(parent)
        self.record = record
        self.is_expanded = False

        # 基础样式设定
        self.setFixedHeight(68)  # 默认折叠高度
        self._setup_comfy_style()
        self.setup_ui()
        self.update_data(record)

    def _setup_comfy_style(self):
        """设置卡片整体的暗黑/节点风格"""
        # 移除默认 CardWidget 的边框和背景，自己接管
        self.setBorderRadius(8)

        # 定义状态颜色字典
        self.status_colors = {
            "running": "#2196F3",  # 蓝色
            "success": "#4CAF50",  # ComfyUI 绿色
            "failed": "#F44336",  # 红色
            "cancelled": "#9E9E9E"  # 灰色
        }

        # 默认背景色（深灰）
        self.bg_color = "#2B2D30"
        self.setStyleSheet(f"""
            ExecutionResultCard {{
                background-color: {self.bg_color};
                border: 1px solid #3E3E42;
            }}
            QLabel {{
                color: #E0E0E0; /* 全局文字亮色 */
            }}
        """)

    def setup_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # === 1. 顶部容器 (Header) ===
        self.header_widget = QWidget()
        self.header_widget.setFixedHeight(68)
        # 左侧加一个 Colored Bar 指示状态
        self.header_layout = QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(0, 0, 15, 0)  # 左侧0边距给状态条
        self.header_layout.setSpacing(12)

        # A. 左侧状态条 indicator
        self.status_strip = QFrame()
        self.status_strip.setFixedWidth(5)
        self.status_strip.setStyleSheet(
            "background-color: gray; border-top-left-radius: 8px; border-bottom-left-radius: 8px;")
        self.header_layout.addWidget(self.status_strip)

        # B. 状态图标 (带一点发光感)
        self.status_icon = IconWidget(FluentIcon.INFO)
        self.status_icon.setFixedSize(20, 20)
        self.header_layout.addWidget(self.status_icon)

        # C. 信息区 (名称 + ID)
        self.info_layout = QVBoxLayout()
        self.info_layout.setSpacing(2)
        self.info_layout.setAlignment(Qt.AlignVCenter)

        self.name_label = QLabel()
        self.name_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #FFFFFF;")

        self.id_label = QLabel()
        self.id_label.setStyleSheet("color: #808080; font-family: 'Consolas'; font-size: 10px;")

        self.info_layout.addWidget(self.name_label)
        self.info_layout.addWidget(self.id_label)
        self.header_layout.addLayout(self.info_layout)

        self.header_layout.addStretch(1)

        # D. 右侧元数据 (触发器Badge + 时间)
        self.meta_layout = QVBoxLayout()
        self.meta_layout.setSpacing(4)
        self.meta_layout.setAlignment(Qt.AlignVCenter | Qt.AlignRight)

        self.trigger_badge = StatusBadge("Manual")
        self.meta_layout.addWidget(self.trigger_badge, 0, Qt.AlignRight)

        self.duration_label = QLabel("--:--:--")
        self.duration_label.setStyleSheet("color: #A0A0A0; font-size: 11px;")
        self.meta_layout.addWidget(self.duration_label, 0, Qt.AlignRight)

        self.header_layout.addLayout(self.meta_layout)

        # E. 展开按钮
        self.expand_btn = TransparentToolButton(get_icon("展开"), self)  # 如果没有icon，改回 FluentIcon.CHEVRON_DOWN
        self.expand_btn.setFixedSize(32, 32)
        # 强制白色图标
        self.expand_btn.setIconSize(QSize(14, 14))
        self.expand_btn.clicked.connect(self.toggle_expand)
        self.header_layout.addWidget(self.expand_btn)

        self.layout.addWidget(self.header_widget)

        # === 2. 详情容器 (Details) ===
        self.detail_widget = QWidget()
        self.detail_widget.setStyleSheet(
            "background-color: #252526; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;")
        self.detail_layout = QVBoxLayout(self.detail_widget)
        self.detail_layout.setContentsMargins(20, 10, 20, 20)
        self.detail_layout.setSpacing(8)

        # 辅助函数：创建小标题
        def create_section_title(text):
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #808080; font-weight: bold; font-size: 11px;")
            return lbl

        # 输入
        self.detail_layout.addWidget(create_section_title("INPUT"))
        self.input_view = CodeViewer()
        self.input_view.setMaximumHeight(80)
        self.detail_layout.addWidget(self.input_view)

        # 输出
        self.detail_layout.addWidget(create_section_title("OUTPUT"))
        self.output_view = CodeViewer()
        self.output_view.setMaximumHeight(120)
        self.detail_layout.addWidget(self.output_view)

        # 错误
        self.error_container = QWidget()
        self.error_layout = QVBoxLayout(self.error_container)
        self.error_layout.setContentsMargins(0, 0, 0, 0)
        self.error_lbl = create_section_title("ERROR LOG")
        self.error_lbl.setStyleSheet("color: #F44336; font-weight: bold; font-size: 11px;")
        self.error_view = CodeViewer()
        self.error_view.setStyleSheet(
            self.error_view.styleSheet() + "border: 1px solid #602020; background-color: #2D1010;")
        self.error_view.setMaximumHeight(60)
        self.error_layout.addWidget(self.error_lbl)
        self.error_layout.addWidget(self.error_view)

        self.detail_layout.addWidget(self.error_container)

        self.detail_widget.setVisible(False)
        self.layout.addWidget(self.detail_widget)

    def update_data(self, record):
        """更新数据"""
        self.record = record

        self.name_label.setText(record.canvas_name)
        eid_short = record.execution_id[:8] if record.execution_id else "N/A"
        self.id_label.setText(f"#{eid_short}")

        # 更新 Badge
        self.trigger_badge.setText(record.trigger_type.upper())

        # 时间计算
        start_dt = datetime.fromtimestamp(record.start_time)
        time_str = start_dt.strftime("%H:%M:%S")
        if record.end_time:
            duration = record.end_time - record.start_time
            self.duration_label.setText(f"{time_str} ({duration:.2f}s)")
        else:
            duration = time.time() - record.start_time
            self.duration_label.setText(f"{time_str} ({duration:.1f}s...)")

        # 样式与状态更新
        self._update_status_visuals(record.status)

        if self.is_expanded:
            self._render_details()

    def _update_status_visuals(self, status):
        """核心美化逻辑：根据状态改变颜色"""
        color_hex = self.status_colors.get(status, "#9E9E9E")

        # 1. 设置左侧条颜色
        self.status_strip.setStyleSheet(f"""
            background-color: {color_hex}; 
            border-top-left-radius: 8px; 
            border-bottom-left-radius: 8px;
            /* 如果展开，左下角不需要圆角 */
            {'border-bottom-left-radius: 0px;' if self.is_expanded else ''}
        """)

        # 2. 设置 Icon
        if status == "running":
            self.status_icon.setIcon(FluentIcon.SYNC)
            # 运行状态下，文字高亮
            self.name_label.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {color_hex};")
        elif status == "success":
            self.status_icon.setIcon(FluentIcon.COMPLETED)
            self.name_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #FFFFFF;")
        elif status == "failed":
            self.status_icon.setIcon(get_icon("失败"))
            self.name_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #F44336;")
        else:
            self.status_icon.setIcon(FluentIcon.CANCEL)
            self.name_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #9E9E9E;")

        # 更新 Icon 颜色
        self.status_icon.setStyleSheet(f"color: {color_hex};")

    def _render_details(self):
        def safe_json(data):
            try:
                return json.dumps(data, indent=2, ensure_ascii=False)
            except:
                return str(data)

        self.input_view.setText(safe_json(self.record.input_data))
        self.output_view.setText(safe_json(self.record.output_data))

        if self.record.error_msg:
            self.error_container.setVisible(True)
            self.error_view.setText(self.record.error_msg)
        else:
            self.error_container.setVisible(False)

    def toggle_expand(self):
        self.is_expanded = not self.is_expanded
        self.detail_widget.setVisible(self.is_expanded)

        # 高度自适应
        if self.is_expanded:
            self.setFixedHeight(QSize(16777215, 16777215).height())  # 恢复自动高度
            self.expand_btn.setIcon(get_icon("折叠"))
        else:
            self.setFixedHeight(68)
            self.expand_btn.setIcon(get_icon("展开"))

        # 刷新边框圆角样式（因为展开后左下角不需要圆角，连接处要平滑）
        self._render_details()
        self._update_status_visuals(self.record.status)