# -*- coding: utf-8 -*-
"""
扁平式模型选择上拉框 - 类似 OpenCode 风格
展示所有已配置服务商的模型，服务商作为小标题，下面是模型列表
"""
import ast
from typing import Dict, List, Tuple, Optional, Any
from loguru import logger
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QPainter, QColor, QBrush, QPen
from PyQt5.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QLineEdit,
    QApplication,
)
from qfluentwidgets import (
    BodyLabel,
    LineEdit,
    CardWidget,
    setFont,
)
from app.utils.utils import get_icon, get_unified_font, get_font_family_css
from app.llm_chatter.constants import (
    PROVIDER_ICONS,
    PROVIDER_MODELS,
    FREE_PROVIDERS,
)
from app.widgets.card_widget.provider_setting_card import (
    ProviderIconWidget,
)


class ProviderHeader(QWidget):
    """服务商标题行"""

    def __init__(self, provider_name: str, parent=None):
        super().__init__(parent)
        self.provider_name = provider_name
        self.setFixedHeight(36)
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 8, 0)
        layout.setSpacing(8)

        # 服务商图标
        self.icon_widget = ProviderIconWidget(provider_name, 20)
        layout.addWidget(self.icon_widget)

        # 服务商名称
        self.name_label = QLabel(provider_name, self)
        self.name_label.setStyleSheet(f"color: #e0e0e0; {get_font_family_css()} font-size: 12px; font-weight: bold;")
        layout.addWidget(self.name_label)

        layout.addStretch(1)


class ModelItem(QWidget):
    """单个模型项 - 可点击"""
    clicked = pyqtSignal(str, str)  # provider_name, model_name

    def __init__(self, provider_name: str, model_name: str, is_active: bool = False, parent=None):
        super().__init__(parent)
        self.provider_name = provider_name
        self.model_name = model_name
        self.is_active = is_active
        self.setFixedHeight(34)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(30, 0, 12, 0)
        layout.setSpacing(8)

        # 选中状态指示点
        self.dot = QLabel("●", self)
        self.dot.setStyleSheet(
            f"color: #0078d4; {get_font_family_css()} font-size: 10px;" if self.is_active else f"color: transparent; {get_font_family_css()} font-size: 10px;"
        )
        self.dot.setFixedWidth(14)
        layout.addWidget(self.dot)

        # 模型名
        self.name_label = QLabel(self.model_name, self)
        if self.is_active:
            self.name_label.setStyleSheet(f"color: #ffffff; font-weight: bold; {get_font_family_css()} font-size: 13px;")
        else:
            self.name_label.setStyleSheet(f"color: #cccccc; {get_font_family_css()} font-size: 13px;")
        layout.addWidget(self.name_label, 1)

    def set_active(self, active: bool):
        self.is_active = active
        self.dot.setStyleSheet(
            f"color: #0078d4; {get_font_family_css()} font-size: 10px;" if active else f"color: transparent; {get_font_family_css()} font-size: 10px;"
        )
        if active:
            self.name_label.setStyleSheet(f"color: #ffffff; font-weight: bold; {get_font_family_css()} font-size: 13px;")
        else:
            self.name_label.setStyleSheet(f"color: #cccccc; {get_font_family_css()} font-size: 13px;")

    def mousePressEvent(self, event):
        self.clicked.emit(self.provider_name, self.model_name)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        if not self.is_active:
            self.name_label.setStyleSheet(f"color: #ffffff; {get_font_family_css()} font-size: 13px;")
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.is_active:
            self.name_label.setStyleSheet(f"color: #cccccc; {get_font_family_css()} font-size: 13px;")
        super().leaveEvent(event)


class ModelSelectorPopup(QWidget):
    """扁平式模型选择弹窗"""
    modelSelected = pyqtSignal(str, str)  # provider_name, model_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.parent_widget = parent

        # 数据
        self._provider_models: List[Tuple[str, List[str]]] = []  # [(provider, [models])]
        self._current_provider: str = ""
        self._current_model: str = ""
        self._model_widgets: List[ModelItem] = []
        self._all_model_items: List[Tuple[ModelItem, str, str]] = []  # (widget, provider, model)

        self._setup_ui()

    def _setup_ui(self):
        self.main_frame = QFrame(self)
        self.main_frame.setObjectName("popupFrame")
        self.main_frame.setStyleSheet("""
            QFrame#popupFrame {
                background-color: #2d2d2d;
                border: 1px solid #444444;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(self.main_frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)

        # 搜索框
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("搜索模型...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setStyleSheet("""
            QLineEdit {
                background-color: #3d3d3d;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 6px 10px;
                {get_font_family_css()} font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #0078d4;
            }
            QLineEdit::placeholder {
                color: #888888;
            }
        """)
        self.search_edit.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_edit)

        # 分隔线
        separator = QFrame(self)
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #3d3d3d; max-height: 1px; margin: 6px 0;")
        layout.addWidget(separator)

        # 滚动区域
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 6px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: #555555;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #666666;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        # 底部弹性空间，让内容靠上
        self.content_layout.addStretch(1)

        self.scroll_area.setWidget(self.content_widget)
        layout.addWidget(self.scroll_area, 1)

        # 整体窗口布局
        window_layout = QVBoxLayout(self)
        window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.addWidget(self.main_frame)

    def set_providers_data(
        self,
        provider_models: List[Tuple[str, List[str], bool]],  # (provider, [models], is_current_provider)
        current_provider: str,
        current_model: str,
    ):
        """设置服务商和模型数据"""
        self._current_provider = current_provider
        self._current_model = current_model
        self._provider_models = [(p, m) for p, m, _ in provider_models]
        self._model_widgets.clear()
        self._all_model_items.clear()

        # 清空内容区域（保留最后的 stretch）
        while self.content_layout.count() > 0:
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

        search_text = self.search_edit.text().strip().lower()

        for provider_name, models, is_current_provider in provider_models:
            # 过滤
            if search_text:
                filtered_models = [m for m in models if search_text in m.lower()]
                if not filtered_models:
                    continue
            else:
                filtered_models = models

            # 服务商标题
            header = ProviderHeader(provider_name, self)
            self.content_layout.addWidget(header)

            # 模型列表
            for model_name in filtered_models:
                is_active = (
                    provider_name == current_provider and model_name == current_model
                )
                item = ModelItem(provider_name, model_name, is_active, self)
                item.clicked.connect(self._on_model_clicked)
                self.content_layout.addWidget(item)
                self._model_widgets.append(item)
                self._all_model_items.append((item, provider_name, model_name))

        # 如果没有匹配的模型
        if not self._all_model_items and search_text:
            no_result = QLabel(f"未找到匹配 \"{search_text}\" 的模型", self)
            no_result.setAlignment(Qt.AlignCenter)
            no_result.setStyleSheet(f"color: #888888; {get_font_family_css()} font-size: 12px; padding: 20px;")
            self.content_layout.addWidget(no_result)

        # 底部弹性空间
        self.content_layout.addStretch(1)

        self.main_frame.adjustSize()
        self.adjustSize()

    def _clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self._clear_layout(child.layout())

    def _on_search_changed(self, text: str):
        """搜索文本变化时刷新列表"""
        # 重新构建 provider_models 数据（从保存的原始数据重建）
        # 需要重新获取 is_current_provider 信息
        provider_models_with_flag = []
        for prov, models in self._provider_models:
            is_cur = prov == self._current_provider
            provider_models_with_flag.append((prov, models, is_cur))

        self.set_providers_data(
            provider_models_with_flag,
            self._current_provider,
            self._current_model,
        )

    def _on_model_clicked(self, provider_name: str, model_name: str):
        """模型被点击"""
        self.modelSelected.emit(provider_name, model_name)
        self.close()

    def show_at(self, reference_widget: QWidget):
        """在参考控件上方显示弹窗（向上展开）"""
        self.adjustSize()

        # 设置最大尺寸
        screen = QApplication.primaryScreen()
        if screen:
            screen_geom = screen.availableGeometry()
            max_width = min(450, screen_geom.width() - 40)
            max_height = min(500, screen_geom.height() - 120)
            self.setMaximumSize(max_width, max_height)
        else:
            self.setMaximumSize(450, 500)

        btn_rect = reference_widget.rect()
        btn_global_pos = reference_widget.mapToGlobal(btn_rect.topLeft())
        btn_width = btn_rect.width()

        popup_width = min(self.width(), self.maximumWidth())
        popup_height = min(self.height(), self.maximumHeight())

        # 水平位置：左对齐到按钮左边缘
        x = btn_global_pos.x()

        # 垂直位置：在按钮上方展开
        y = btn_global_pos.y() - popup_height

        if screen:
            # 水平边界检查
            if x < screen_geom.left():
                x = screen_geom.left() + 10
            if x + popup_width > screen_geom.right():
                x = screen_geom.right() - popup_width - 10
            # 如果上方空间不够，显示在下方
            if y < screen_geom.top():
                y = btn_global_pos.y() + btn_rect.height()

        self.move(x, y)
        self.show()
        self.raise_()
        self.search_edit.setFocus()
        self.search_edit.selectAll()
