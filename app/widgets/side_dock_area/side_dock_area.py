# -*- coding: utf-8 -*-
from typing import Type, Optional, Dict

from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import QWidget, QStackedWidget, QHBoxLayout

from .button_bar import RightToolPanel
from .plugins.ipython_console import IPythonConsoleToolWindow
from app.widgets.side_dock_area.plugins.property_panel import PropertyToolWindow
from .plugins.llm_chatter.main_widget import OpenAIChatToolWindow
from .plugins.variable_explorer import VariableExplorerToolWindow
from .registry import SideDockRegistry
from .tool_window import DockPosition, ToolWindow
from ..basic_widget.splitter import ModernSplitter

SideDockRegistry.register(PropertyToolWindow.name, PropertyToolWindow)
SideDockRegistry.register(OpenAIChatToolWindow.name, OpenAIChatToolWindow)
SideDockRegistry.register(IPythonConsoleToolWindow.name, IPythonConsoleToolWindow)
SideDockRegistry.register(VariableExplorerToolWindow.name, VariableExplorerToolWindow)


class AdaptiveStackedWidget(QStackedWidget):
    def sizeHint(self) -> QSize:
        current = self.currentWidget()
        if current:
            return current.sizeHint()
        return QSize(0, 0)

    def minimumSizeHint(self) -> QSize:
        current = self.currentWidget()
        if current:
            return current.minimumSizeHint()
        return QSize(0, 0)


class SideDockArea(QWidget):
    def __init__(self, canvas_page):
        super().__init__()
        self.canvas_page = canvas_page
        self._instances: Dict[str, ToolWindow] = {}
        main_layout = QHBoxLayout(self)  # ← 水平布局：[ 内容区 | 按钮栏 ]
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        # 内容区
        self.splitter = ModernSplitter(Qt.Vertical)
        self.top_stack = AdaptiveStackedWidget()
        self.bottom_stack = AdaptiveStackedWidget()
        # 初始隐藏
        self.top_stack.hide()
        self.bottom_stack.hide()
        self._top_visible = False
        self._bottom_visible = False

        self.splitter.addWidget(self.top_stack)
        self.splitter.addWidget(self.bottom_stack)
        # 工具面板
        self.tool_panel = RightToolPanel(canvas_page, self)

        self.tool_panel.topToolChecked.connect(self._show_top_tool)
        self.tool_panel.topToolUnchecked.connect(self._hide_top_tool)
        self.tool_panel.bottomToolChecked.connect(self._show_bottom_tool)
        self.tool_panel.bottomToolUnchecked.connect(self._hide_bottom_tool)

        main_layout.addWidget(self.splitter)  # 占主要空间

        self._load_plugins()

    def _show_top_tool(self, tool_name):
        view = self.get_tool_instance(tool_name)
        idx = self.top_stack.indexOf(view)
        if idx == -1:
            idx = self.top_stack.addWidget(view)
        self.top_stack.setCurrentIndex(idx)
        self.top_stack.show()
        self._top_visible = True
        self._update_splitter()

    def _hide_top_tool(self, tool_name):
        self.top_stack.hide()
        self._top_visible = False
        self._update_splitter()

    def _show_bottom_tool(self, tool_name):
        view = self.get_tool_instance(tool_name)
        idx = self.bottom_stack.indexOf(view)
        if idx == -1:
            idx = self.bottom_stack.addWidget(view)
        self.bottom_stack.setCurrentIndex(idx)
        self.bottom_stack.show()
        self._bottom_visible = True
        self._update_splitter()

    def _hide_bottom_tool(self, tool_name):
        self.bottom_stack.hide()
        self._bottom_visible = False
        self._update_splitter()

    def _update_splitter(self):
        self.content_visible = self._top_visible or self._bottom_visible
        if not self.content_visible:
            self.splitter.setSizes([0, 0])
            self.canvas_page.ui_manager.hide_splitter()
            return
        self.canvas_page.ui_manager.show_splitter()
        if self._top_visible and self._bottom_visible:
            self.splitter.setSizes([1, 1])
        elif self._top_visible:
            self.splitter.setSizes([1, 0])
        else:
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
            QtCore.QTimer.singleShot(100, lambda: self._show_top_tool(first_cls.name))
            # 同时让对应按钮进入 checked 状态（视觉同步）
            self.tool_panel._set_top_button_checked(first_cls)

    def _get_or_create_instance(self, cls: Type[ToolWindow]) -> ToolWindow:
        """根据 singleton 策略获取或创建实例"""
        name = cls.name
        if cls.singleton:
            if name not in self._instances:
                self._instances[name] = cls(self.canvas_page)
            return self._instances[name]
        else:
            return cls(self.canvas_page)

    def get_tool_instance(self, name: str) -> Optional[ToolWindow]:
        """外部可通过 name 获取面板实例，用于信号连接等"""
        entry = SideDockRegistry._entries.get(name)
        if entry is None:
            return None
        return self._get_or_create_instance(entry.cls)