# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QFormLayout, QToolButton, QFrame, QSizePolicy, QApplication
from qfluentwidgets import (
    LineEdit, BodyLabel, TextEdit,
    FluentIcon, setFont, EditableComboBox
)

from app.scan_components import ComponentScanner
from app.utils.utils import get_icon
from app.widgets.side_dock_area.plugins.component_info.port_editory_widget import PortEditorWidget
from app.widgets.side_dock_area.plugins.component_info.property_editory_widget import PropertyEditorWidget
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class CollapsibleCard(QWidget):
    """可折叠的卡片容器（带平滑动画）"""
    toggled = pyqtSignal(bool)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._is_expanded = True

        # === 标题按钮 ===
        self.toggle_button = QToolButton()
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setText(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(True)
        self.toggle_button.clicked.connect(self.toggle)
        setFont(self.toggle_button, 14, QFont.Weight.Bold)
        self.toggle_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.toggle_button.setMinimumHeight(32)

        # 设置样式：整行 hover，文字左对齐
        self.toggle_button.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                padding: 6px 8px;
                text-align: left;
                color: #FFFFFF;
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
        self.content_layout.setContentsMargins(10, 0, 10, 5)
        self.content_widget.setVisible(True)

        # 初始设置 maximumHeight（用于展开状态）
        self.content_widget.setMaximumHeight(16777215)  # Qt 的默认最大值

        # === 动画设置 ===
        self.animation = QPropertyAnimation(self.content_widget, b"maximumHeight")
        self.animation.setDuration(200)  # 200ms，VS Code 风格
        self.animation.setEasingCurve(QEasingCurve.OutCubic)  # 更自然的缓动

        # === 主布局 ===
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toggle_button)
        layout.addWidget(self.content_widget)
        self.update_icon()

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)
        # 如果已折叠，新内容不会显示，但下次展开会包含

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
            self.content_widget.setMaximumHeight(16777215)

            # 强制布局计算，不使用 processEvents
            self.content_layout.activate()
            content_height = self.content_layout.sizeHint().height()
            margins = self.content_layout.contentsMargins()
            content_height += margins.top() + margins.bottom()
            if content_height <= 0:
                content_height = 100

            # 重置为 0 开始动画
            self.content_widget.setMaximumHeight(0)

            self.animation.setDuration(250)
            self.animation.setEasingCurve(QEasingCurve.OutQuad)
            self.animation.setStartValue(0)
            self.animation.setEndValue(content_height)
            self.animation.start()

            self.animation.finished.connect(
                lambda: (
                    self.content_widget.setVisible(True),
                    self.content_widget.setMaximumHeight(16777215)
                )
            )
        else:
            # 折叠
            current_height = self.content_widget.height()
            if current_height == 0:
                self.content_widget.setVisible(False)
                return

            self.animation.setDuration(250)
            self.animation.setEasingCurve(QEasingCurve.OutQuad)
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
    _name_edit = None
    _category_edit = None
    _description_edit = None
    _requirements_edit = None
    _input_port_editor = None
    _output_port_editor = None
    _property_editor = None

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        # === 基本信息 ===
        basic_card = CollapsibleCard("基本信息")
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        self._name_edit = LineEdit()
        self._category_edit = EditableComboBox()
        self._category_edit.setMaxVisibleItems(12)
        ComponentScanner.register_on_change(self.refresh_category_combobox)
        self.refresh_category_combobox()
        self._description_edit = TextEdit()  # 改为 TextEdit
        self._description_edit.setMaximumHeight(100)
        form_layout.addRow(BodyLabel("组件名称:"), self._name_edit)
        form_layout.addRow(BodyLabel("组件分类:"), self._category_edit)
        form_layout.addRow(BodyLabel("组件描述:"), self._description_edit)
        basic_card.add_widget(form_widget)

        # === 依赖信息 ===
        dep_card = CollapsibleCard("依赖信息")
        self._requirements_edit = TextEdit()
        self._requirements_edit.setMaximumHeight(120)
        dep_card.add_widget(self._requirements_edit)

        # === 输入端口 ===
        input_card = CollapsibleCard("输入端口")
        self._input_port_editor = PortEditorWidget("input")
        input_card.add_widget(self._input_port_editor)

        # === 输出端口 ===
        output_card = CollapsibleCard("输出端口")
        self._output_port_editor = PortEditorWidget("output")
        output_card.add_widget(self._output_port_editor)

        # === 属性参数 ===
        prop_card = CollapsibleCard("属性参数")
        self._property_editor = PropertyEditorWidget(self)
        prop_card.add_widget(self._property_editor)

        # 默认全部展开（可选）
        for card in [basic_card, dep_card, input_card, output_card, prop_card]:
            main_layout.addWidget(card)

        # 可选：添加 stretch 保证底部对齐
        main_layout.addStretch(1)

    def refresh_category_combobox(self):
        self._category_edit.clear()
        compoent_map, _ = ComponentScanner().get_components()
        categories = {getattr(cls, 'category', 'General') for cls in compoent_map.values()}
        self._category_edit.addItems(categories)

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