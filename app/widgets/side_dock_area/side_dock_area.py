# -*- coding: utf-8 -*-
from typing import Type, Optional, Dict

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QStackedWidget, QHBoxLayout

from .button_bar import RightToolPanel
from .plugins.property_panel.api import PropertyToolWindow
from .plugins.test1 import LogWindow
from .plugins.test2 import VariableWindow
from .registry import SideDockRegistry
from .tool_window import DockPosition, ToolWindow
from ..basic_widget.splitter import ModernSplitter

SideDockRegistry.register(PropertyToolWindow.name, PropertyToolWindow)
SideDockRegistry.register(VariableWindow.name, VariableWindow)
SideDockRegistry.register(LogWindow.name, LogWindow)


class SideDockArea(QWidget):
    def __init__(self, canvas_page):
        super().__init__()
        self.canvas_page = canvas_page
        self._instances: Dict[str, ToolWindow] = {}
        main_layout = QHBoxLayout(self)  # ← 水平布局：[ 内容区 | 按钮栏 ]
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 内容区
        self.splitter = ModernSplitter(Qt.Vertical)
        self.top_stack = QStackedWidget()
        self.bottom_stack = QStackedWidget()
        self.splitter.addWidget(self.top_stack)
        self.splitter.addWidget(self.bottom_stack)

        # 工具面板
        self.tool_panel = RightToolPanel(canvas_page, self)

        self.tool_panel.topToolChecked.connect(self._show_top_tool)
        self.tool_panel.topToolUnchecked.connect(self._hide_top_tool)
        self.tool_panel.bottomToolChecked.connect(self._show_bottom_tool)
        self.tool_panel.bottomToolUnchecked.connect(self._hide_bottom_tool)

        main_layout.addWidget(self.splitter, 1)  # 占主要空间
        main_layout.addWidget(self.tool_panel, 0)  # 不拉伸，靠右
        # 初始隐藏
        self.top_stack.hide()
        self.bottom_stack.hide()
        self._load_plugins()

    def _show_top_tool(self, tool_name):
        view = self.get_tool_instance(tool_name)
        idx = self.top_stack.indexOf(view)
        if idx == -1:
            idx = self.top_stack.addWidget(view)
        self.top_stack.setCurrentIndex(idx)
        self.top_stack.show()
        self._update_splitter()

    def _hide_top_tool(self, tool_name):
        self.top_stack.hide()
        self._update_splitter()

    def _show_bottom_tool(self, tool_name):
        view = self.get_tool_instance(tool_name)
        idx = self.bottom_stack.indexOf(view)
        if idx == -1:
            idx = self.bottom_stack.addWidget(view)
        self.bottom_stack.setCurrentIndex(idx)
        self.bottom_stack.show()
        self._update_splitter()

    def _hide_bottom_tool(self, tool_name):
        self.bottom_stack.hide()
        self._update_splitter()

    def _update_splitter(self):
        top_vis = self.top_stack.isVisible()
        bot_vis = self.bottom_stack.isVisible()
        if top_vis and bot_vis:
            self.splitter.setSizes([1, 1])
        elif top_vis:
            self.splitter.setSizes([1, 0])
        elif bot_vis:
            self.splitter.setSizes([0, 1])

    def _load_plugins(self):
        """自动按注册时的 default_position 添加到对应区域，并默认选中第一个 TOP 插件"""
        top_classes = []
        for name, entry in SideDockRegistry.get_all().items():
            if entry.position == DockPosition.TOP:
                self.tool_panel.add_to_top(entry.cls)
                top_classes.append(entry.cls)
            elif entry.position == DockPosition.BOTTOM:
                self.tool_panel.add_to_bottom(entry.cls)

        # 自动选中第一个 TOP 插件（模拟 PyCharm 默认行为）
        if top_classes:
            first_cls = top_classes[0]
            # 触发“选中”逻辑：手动调用显示 + 按钮置为 checked
            self._show_top_tool(first_cls.name)
            # 同时让对应按钮进入 checked 状态（视觉同步）
            self.tool_panel._set_top_button_checked(first_cls)

    def _get_or_create_instance(self, cls: Type[ToolWindow]) -> ToolWindow:
        """根据 singleton 策略获取或创建实例"""
        name = cls.name
        if name not in self._instances:
            self._instances[name] = cls(self.canvas_page)
        return self._instances[name]

    def get_tool_instance(self, name: str) -> Optional[ToolWindow]:
        """外部可通过 name 获取面板实例，用于信号连接等"""
        entry = SideDockRegistry._entries.get(name)
        if entry is None:
            return None
        return self._get_or_create_instance(entry.cls)