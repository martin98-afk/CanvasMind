# -*- coding: utf-8 -*-
from typing import Optional
from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QTimer
from PyQt5.QtGui import QFont, QTextOption
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
        self._is_expanded = False

        # === 标题按钮 ===
        self.toggle_button = QToolButton()
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setText(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(False)
        self.toggle_button.clicked.connect(self.toggle)
        setFont(self.toggle_button, 14, QFont.Weight.Bold)
        self.toggle_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.toggle_button.setMinimumHeight(20)
        self.toggle_button.setMaximumHeight(20)
        self.toggle_button.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                padding: 3px 3px;
                text-align: left;
                color: #FFFFFF;
                min-height: 20px;
                max-height: 20px;
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
        self.content_widget.setMaximumHeight(0)
        self.content_layout.setContentsMargins(4, 4, 4, 4)
        self.content_widget.setVisible(False)
        # 轻微背景提升层次（仅深色下可见）
        self.content_widget.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 5);
                border-radius: 6px;
                margin-top: 4px;
            }
        """)

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
            self.content_widget.setVisible(True)

            def _start_expand():
                if self.isVisible():
                    self.content_widget.setMaximumHeight(16777215)
                    QApplication.processEvents()
                    content_height = self.content_widget.sizeHint().height()
                    if content_height <= 0:
                        content_height = 100
                else:
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
        self.scroll_area = SmoothScrollArea()
        self.scroll_area.setStyleSheet("background: transparent;")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setFrameShape(QFrame.NoFrame)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(4, 14, 4, 4)
        self.content_layout.setSpacing(0)

        # 创建卡片
        self.basic_card = self._create_basic_card()
        self.dep_card = self._create_dependency_card()
        self.input_card = self._create_input_card()
        self.output_card = self._create_output_card()
        self.prop_card = self._create_property_card()

        for card in [self.basic_card, self.dep_card, self.input_card, self.output_card, self.prop_card]:
            self.content_layout.addWidget(card)

        self.content_layout.addStretch(1)
        self.scroll_area.setWidget(self.content_widget)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.scroll_area)

    def _create_basic_card(self):
        card = CollapsibleCard("基本信息")
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setLabelAlignment(Qt.AlignRight)
        form_layout.setSpacing(4)
        form_layout.setContentsMargins(0, 0, 0, 0)

        self._name_edit = LineEdit()
        self._name_edit.setPlaceholderText("请输入组件名称")

        self._category_edit = EditableComboBox()
        self._category_edit.setMaxVisibleItems(12)
        self._category_edit.setToolTip("可输入新分类名称")
        ComponentScanner.register_on_change(self.refresh_category_combobox)
        self.refresh_category_combobox()

        self._description_edit = TextEdit()
        self._description_edit.setMaximumHeight(120)
        self._description_edit.setPlaceholderText("请输入组件描述（支持换行）")
        self._description_edit.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self._description_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # 统一字体层级
        for label_text in ["组件名称:", "组件分类:", "组件描述:"]:
            label = BodyLabel(label_text)
            setFont(label, 12)
            form_layout.addRow(label, None)

        form_layout.setWidget(0, QFormLayout.FieldRole, self._name_edit)
        form_layout.setWidget(1, QFormLayout.FieldRole, self._category_edit)
        form_layout.setWidget(2, QFormLayout.FieldRole, self._description_edit)

        card.add_widget(form_widget)
        return card

    def _create_dependency_card(self):
        card = CollapsibleCard("依赖信息")
        self._requirements_edit = TextEdit()
        self._requirements_edit.setPlaceholderText("例如：requests>=2.25.0\nnumpy\n# 支持多行")
        self._requirements_edit.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self._requirements_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        card.add_widget(self._requirements_edit)
        return card

    def _create_input_card(self):
        card = CollapsibleCard("输入端口")
        self._input_port_editor = PortEditorWidget("input")
        card.add_widget(self._input_port_editor)
        return card

    def _create_output_card(self):
        card = CollapsibleCard("输出端口")
        self._output_port_editor = PortEditorWidget("output")
        card.add_widget(self._output_port_editor)
        return card

    def _create_property_card(self):
        card = CollapsibleCard("属性参数")
        self._property_editor = PropertyEditorWidget(self)
        card.add_widget(self._property_editor)
        return card

    def showEvent(self, event):
        if not self._first_show:
            self._first_show = True
            # 首次仅展开关键卡片
            QTimer.singleShot(100, lambda: self.basic_card.set_expanded(True))
            QTimer.singleShot(100, lambda: self.input_card.set_expanded(True))
            QTimer.singleShot(100, lambda: self.output_card.set_expanded(True))
            QTimer.singleShot(100, lambda: self.prop_card.set_expanded(True))
            # 依赖和属性按需展开
        super().showEvent(event)

    def refresh_category_combobox(self):
        current_category = self.category_edit.currentText()
        self._category_edit.clear()
        compoent_map, _ = ComponentScanner().get_components()
        categories = {getattr(cls, 'category', 'General') for cls in compoent_map.values()}
        self._category_edit.addItems(sorted(categories))
        if current_category in categories:
            self._category_edit.setCurrentText(current_category)

    def clear_all(self):
        if self._name_edit:
            self._name_edit.clear()
        self.refresh_category_combobox()
        if self._description_edit:
            self._description_edit.clear()
        if self._requirements_edit:
            self._requirements_edit.clear()
        if self._input_port_editor:
            self._input_port_editor.set_ports([])
        if self._output_port_editor:
            self._output_port_editor.set_ports([])
        if self._property_editor:
            self._property_editor.set_properties({})

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