# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QLabel, QStackedWidget, QVBoxLayout
from qfluentwidgets import SegmentedWidget

from app.interfaces.canvas_interaface.widgets.draggable_component_tree import (
    DraggableTreePanel,
)
from app.interfaces.canvas_interaface.widgets.subgraph_template_container import (
    SubgraphTemplatePanel,
)
from app.utils.config import Settings


class LeftPanel(QWidget):
    """左侧面板"""

    def __init__(self, parent=None):
        super().__init__()
        self._init_unified_font()
        self.container = SegmentedWidget(self)
        self.stackedWidget = QStackedWidget(self)
        self.vBoxLayout = QVBoxLayout(self)

        self.draggable_tree = DraggableTreePanel(parent)
        self.template_container = SubgraphTemplatePanel(parent)

        # Add tabs
        self.addSubInterface(self.draggable_tree, "draggableTree", self.tr("组件树"))
        self.addSubInterface(
            self.template_container, "templateManager", self.tr("模板库")
        )

        # Connect signal and initialize the current tab
        self.stackedWidget.currentChanged.connect(self.onCurrentIndexChanged)
        self.stackedWidget.setCurrentWidget(self.draggable_tree)
        self.container.setCurrentItem(self.draggable_tree.objectName())

        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.addWidget(self.container)
        self.vBoxLayout.addWidget(self.stackedWidget, 1)

    def _init_unified_font(self):
        """
        在基类中统一配置字体
        """
        # 1. 获取字体名称
        font_name = Settings.get_instance().canvas_font_selected.value
        # 2. 方案 A：使用 setFont (基础设置)
        font = self.font()
        font.setFamily(font_name)
        self.setFont(font)

        # 3. 方案 B：使用 StyleSheet (强制穿透解决嵌套控件无效问题)
        self.setStyleSheet(f"""
            LeftPanel, QWidget {{
                font-family: "{font_name}";
            }}
            /* 针对某些特殊控件的补充（如按钮、标签） */
            QLabel, QPushButton, QLineEdit, QComboBox, QTreeWidget, QTableWidget TreeWidget{{
                font-family: "{font_name}";
            }}
        """)

    def addSubInterface(self, widget: QWidget, objectName: str, text: str):
        self.stackedWidget.addWidget(widget)

        # Use the globally unique objectName as the route key
        self.container.addItem(
            routeKey=objectName,
            text=text,
            onClick=lambda: self.stackedWidget.setCurrentWidget(widget),
        )

    def onCurrentIndexChanged(self, index):
        widget = self.stackedWidget.widget(index)
        self.container.setCurrentItem(widget.objectName())

    def start_from_template(self):
        self.container.setCurrentItem(self.template_container.objectName())
        self.stackedWidget.setCurrentWidget(self.template_container)
