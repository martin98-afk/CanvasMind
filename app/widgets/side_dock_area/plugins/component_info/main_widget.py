# -*- coding: utf-8 -*-
from typing import Optional
from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QFormLayout, QToolButton, QFrame, QSizePolicy, QApplication
from qfluentwidgets import (
    LineEdit, BodyLabel, TextEdit,
    FluentIcon, setFont, EditableComboBox, SmoothScrollArea
)

from app.scan_components import ComponentScanner
from app.utils.utils import get_icon
from app.widgets.side_dock_area.plugins.component_info.port_editory_widget import PortEditorWidget
from app.widgets.side_dock_area.plugins.component_info.property_editory_widget import PropertyEditorWidget
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class CollapsibleCard(QWidget):
    """可折叠的卡片容器（带平滑动画，避免幽灵窗口）"""
    toggled = pyqtSignal(bool)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._is_expanded = False  # 默认折叠，避免初始化触发动画

        # === 标题按钮 ===
        self.toggle_button = QToolButton()
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setText(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(False)
        self.toggle_button.clicked.connect(self.toggle)
        setFont(self.toggle_button, 14, QFont.Weight.Bold)
        self.toggle_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.toggle_button.setMinimumHeight(24)
        self.toggle_button.setMaximumHeight(24)
        self.toggle_button.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                padding: 6px 8px;
                text-align: left;
                color: #FFFFFF;
                min-height: 24px;
                max-height: 24px;
                qproperty-iconSize: 16px 16px;
            }
            QToolButton:hover {
                background: rgba(255, 255, 255, 12);
            }
            QToolButton:pressed {
                background: rgba(255, 255, 255, 20);
            }
        """)

        # === 内容容器 ===
        self.content_widget = QFrame()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_widget.setMinimumHeight(0)
        self.content_widget.setMaximumHeight(0)  # 初始折叠
        self.content_layout.setContentsMargins(10, 0, 10, 0)  # 避免 0 边距导致 layout 异常
        self.content_widget.setVisible(False)

        # === 动画 ===
        self.animation = QPropertyAnimation(self.content_widget, b"maximumHeight")
        self.animation.setDuration(250)
        self.animation.setEasingCurve(QEasingCurve.OutQuad)

        # === 布局 ===
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toggle_button)
        layout.addWidget(self.content_widget)
        self.update_icon()

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)

    def toggle(self):
        self._is_expanded = not self._is_expanded
        self._animate_toggle()
        self.update_icon()
        self.toggled.emit(self._is_expanded)

    def _animate_toggle(self):
        try:
            self.animation.finished.disconnect()
        except TypeError:
            pass

        if self._is_expanded:
            # 展开
            self.content_widget.setVisible(True)

            def _start_expand():
                # 安全计算高度：仅在 widget 可见时才计算
                if self.isVisible():
                    # 先设为最大高度，让 layout 计算真实高度
                    self.content_widget.setMaximumHeight(16777215)
                    QApplication.processEvents()  # 确保 layout 更新
                    content_height = self.content_widget.sizeHint().height()
                    if content_height <= 0:
                        content_height = 100
                else:
                    # 估算高度（避免触发布局）
                    content_height = 100

                self.content_widget.setMaximumHeight(0)
                self.animation.setStartValue(0)
                self.animation.setEndValue(content_height)
                self.animation.start()

                self.animation.finished.connect(
                    lambda: self.content_widget.setMaximumHeight(16777215)
                )

            QTimer.singleShot(0, _start_expand)

        else:
            # 折叠
            current_height = self.content_widget.height()
            if current_height <= 0:
                self.content_widget.setVisible(False)
                return

            self.animation.setStartValue(current_height)
            self.animation.setEndValue(0)
            self.animation.start()

            self.animation.finished.connect(
                lambda: self.content_widget.setVisible(False)
            )

    def update_icon(self):
        if self._is_expanded:
            self.toggle_button.setIcon(FluentIcon.CHEVRON_DOWN_MED.icon())
        else:
            self.toggle_button.setIcon(FluentIcon.CHEVRON_RIGHT_MED.icon())

    def set_expanded(self, expanded: bool):
        if expanded != self._is_expanded:
            self._is_expanded = expanded
            self.toggle_button.setChecked(expanded)
            self._animate_toggle()
            self.update_icon()


class ComponentInfoWindow(ToolWindow):
    name = "组件属性面板"
    icon = get_icon("配置")
    default_position = DockPosition.TOP
    _first_show = False
    _name_edit = None
    _category_edit = None
    _description_edit = None
    _requirements_edit = None
    _input_port_editor = None
    _output_port_editor = None
    _property_editor = None

    def setup_ui(self):
        """原 setup_ui 内容，现在作用于 content_layout"""
        # === 使用 ScrollArea 包裹内容 ===
        self.scroll_area = SmoothScrollArea()
        # 透明背景
        self.scroll_area.setStyleSheet("background: transparent;")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setFrameShape(QFrame.NoFrame)  # 去掉边框

        # 内容容器
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        # === 基本信息 ===
        self.basic_card = CollapsibleCard("基本信息")
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        self._name_edit = LineEdit()
        self._category_edit = EditableComboBox()
        self._category_edit.setMaxVisibleItems(12)
        ComponentScanner.register_on_change(self.refresh_category_combobox)
        self.refresh_category_combobox()
        self._description_edit = TextEdit()
        self._description_edit.setMaximumHeight(100)
        form_layout.addRow(BodyLabel("组件名称:"), self._name_edit)
        form_layout.addRow(BodyLabel("组件分类:"), self._category_edit)
        form_layout.addRow(BodyLabel("组件描述:"), self._description_edit)
        self.basic_card.add_widget(form_widget)

        # === 依赖信息 ===
        self.dep_card = CollapsibleCard("依赖信息")
        self._requirements_edit = TextEdit()
        self._requirements_edit.setMaximumHeight(120)
        self.dep_card.add_widget(self._requirements_edit)

        # === 输入端口 ===
        self.input_card = CollapsibleCard("输入端口")
        self._input_port_editor = PortEditorWidget("input")
        self.input_card.add_widget(self._input_port_editor)

        # === 输出端口 ===
        self.output_card = CollapsibleCard("输出端口")
        self._output_port_editor = PortEditorWidget("output")
        self.output_card.add_widget(self._output_port_editor)

        # === 属性参数 ===
        self.prop_card = CollapsibleCard("属性参数")
        self._property_editor = PropertyEditorWidget(self)
        self.prop_card.add_widget(self._property_editor)

        # 添加到 content_layout
        for card in [self.basic_card, self.dep_card, self.input_card, self.output_card, self.prop_card]:
            self.content_layout.addWidget(card)

        self.content_layout.addStretch(1)
        self.content_widget.setLayout(self.content_layout)
        self.scroll_area.setWidget(self.content_widget)

        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.scroll_area)
        self.setMinimumWidth(480)

    def showEvent(self, event):
        if not self._first_show:
            self._first_show = True
            # 可选：首次显示时展开基本信息卡
            QTimer.singleShot(100, lambda: self.basic_card.set_expanded(True))
            QTimer.singleShot(100, lambda: self.input_card.set_expanded(True))
            QTimer.singleShot(100, lambda: self.output_card.set_expanded(True))
            QTimer.singleShot(100, lambda: self.prop_card.set_expanded(True))
        super().showEvent(event)

    def refresh_category_combobox(self):
        current_category = self.category_edit.currentText()
        self._category_edit.clear()
        compoent_map, _ = ComponentScanner().get_components()
        categories = {getattr(cls, 'category', 'General') for cls in compoent_map.values()}
        self._category_edit.addItems(categories)
        if current_category in categories:
            self._category_edit.setCurrentText(current_category)

    def clear_all(self):
        self.name_edit.clear()
        self.refresh_category_combobox()
        self.description_edit.clear()
        self.requirements_edit.clear()
        self.input_port_editor.set_ports([])
        self.output_port_editor.set_ports([])
        self.property_editor.set_properties({})

    @property
    def name_edit(self):
        return self._name_edit

    @property
    def category_edit(self):
        return self._category_edit

    @property
    def description_edit(self):
        return self._description_edit

    @property
    def requirements_edit(self):
        return self._requirements_edit

    @property
    def input_port_editor(self):
        return self._input_port_editor

    @property
    def output_port_editor(self):
        return self._output_port_editor

    @property
    def property_editor(self):
        return self._property_editor