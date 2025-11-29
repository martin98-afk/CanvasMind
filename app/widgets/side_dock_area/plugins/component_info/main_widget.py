# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QHBoxLayout, QFormLayout

from qfluentwidgets import SimpleCardWidget, LineEdit, BodyLabel, TextEdit

from app.utils.utils import get_icon
from app.widgets.basic_widget.splitter import ModernSplitter
from app.widgets.side_dock_area.plugins.component_info.port_editory_widget import PortEditorWidget
from app.widgets.side_dock_area.plugins.component_info.property_editory_widget import PropertyEditorWidget
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class ComponentInfoWindow(ToolWindow):
    name = "组件属性面板"
    icon = get_icon("配置")
    default_position = DockPosition.TOP  # ← 默认放在顶部
    _name_edit = None
    _category_edit = None
    _description_edit = None
    _requirements_edit = None
    _input_port_editor = None
    _output_port_editor = None
    _property_editor = None

    def setup_ui(self):
        info_layout = QVBoxLayout(self)
        info_layout.setContentsMargins(0, 0, 0, 0)
        # --- 基本信息卡片 ---
        basic_info_widget = SimpleCardWidget()
        basic_info_widget.setMinimumWidth(450)
        # 使用水平布局来并排放置信息和依赖
        basic_info_h_layout = QHBoxLayout(basic_info_widget)
        basic_info_h_layout.setContentsMargins(0, 0, 0, 0)  # 设置整体边距
        # 左侧：名称、分类、描述
        left_form_widget = QWidget(self)  # 容器用于左侧表单
        left_form_layout = QFormLayout(left_form_widget)
        self._name_edit = LineEdit()
        self._category_edit = LineEdit()
        self._description_edit = LineEdit()
        left_form_layout.addRow(BodyLabel("组件基本信息:"))
        left_form_layout.addRow(BodyLabel("组件名称:"), self._name_edit)
        left_form_layout.addRow(BodyLabel("组件分类:"), self._category_edit)
        left_form_layout.addRow(BodyLabel("组件描述:"), self._description_edit)
        # 右侧：依赖 requirements
        right_req_widget = QWidget(self)  # 容器用于右侧依赖
        right_req_layout = QVBoxLayout(right_req_widget)  # 垂直布局放标签和编辑器
        right_req_layout.addWidget(BodyLabel("组件依赖:"))  # 标签
        self._requirements_edit = TextEdit()  # 使用 qfluentwidgets 的 TextEdit
        self._requirements_edit.setFixedHeight(115)  # 设置固定高度，或使用 setMaximumHeight
        right_req_layout.addWidget(self._requirements_edit)  # 编辑器
        # 将左右两个容器添加到水平布局
        basic_info_h_layout.addWidget(left_form_widget)
        basic_info_h_layout.addWidget(right_req_widget)
        # 设置拉伸因子，让左侧稍微窄一些，右侧稍微宽一些，或者相等
        basic_info_h_layout.setStretch(0, 1)  # 左侧 (信息)
        basic_info_h_layout.setStretch(1, 1)  # 右侧 (依赖)
        info_layout.addWidget(basic_info_widget)
        # 端口编辑器（上下布局）
        port_splitter = ModernSplitter(Qt.Horizontal)
        # 输入输出端口编辑器
        self._input_port_editor = PortEditorWidget("input")
        self._output_port_editor = PortEditorWidget("output")
        port_splitter.addWidget(self._input_port_editor)
        port_splitter.addWidget(self._output_port_editor)
        port_splitter.setSizes([200, 100])  # 初始大小
        info_layout.addWidget(port_splitter, stretch=1)
        # 属性编辑器
        self._property_editor = PropertyEditorWidget(self)
        info_layout.addWidget(self._property_editor, stretch=1)

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