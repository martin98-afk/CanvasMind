# -*- coding: utf-8 -*-
from typing import Type, Optional, Dict
from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import QWidget, QStackedWidget, QHBoxLayout

from .button_bar import RightToolPanel
from .registry import SideDockRegistry
from .tool_window import DockPosition, ToolWindow
from ..basic_widget.splitter import ModernSplitter


class AdaptiveStackedWidget(QStackedWidget):
    def sizeHint(self) -> QSize:
        current = self.currentWidget()
        return current.sizeHint() if current else QSize(0, 0)

    def minimumSizeHint(self) -> QSize:
        current = self.currentWidget()
        return current.minimumSizeHint() if current else QSize(0, 0)


class SideDockArea(QWidget):
    def __init__(self, page, context_id):
        super().__init__()
        self.page = page
        self.context_id = context_id
        self._instances: Dict[str, ToolWindow] = {}

        self.setUpdatesEnabled(False)

        try:
            main_layout = QHBoxLayout(self)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(0)

            # 内容分栏
            self.splitter = ModernSplitter(Qt.Vertical)
            self.top_stack = AdaptiveStackedWidget()
            self.bottom_stack = AdaptiveStackedWidget()
            self.top_stack.hide()
            self.bottom_stack.hide()
            self._top_visible = False
            self._bottom_visible = False
            self.last_content_visible = False

            self.splitter.addWidget(self.top_stack)
            self.splitter.addWidget(self.bottom_stack)

            # 工具按钮栏 (保留变量名 tool_panel)
            self.tool_panel = RightToolPanel(page, self)
            self.tool_panel.topToolChecked.connect(self._show_top_tool)
            self.tool_panel.topToolUnchecked.connect(self._hide_top_tool)
            self.tool_panel.bottomToolChecked.connect(self._show_bottom_tool)
            self.tool_panel.bottomToolUnchecked.connect(self._hide_bottom_tool)
            self.tool_panel.toolMoveRequested.connect(self._handle_tool_reposition)

            main_layout.addWidget(self.splitter)

            self._load_plugins(context_id)

        finally:
            self.setUpdatesEnabled(True)
            self.update()

    def _handle_tool_reposition(self, tool_name, pos_str):
        """处理拖拽后的位置逻辑切换"""
        instance = self.get_tool_instance(tool_name)
        if not instance: return

        new_pos = DockPosition.TOP if pos_str == "top" else DockPosition.BOTTOM
        # 如果位置没变，不处理
        if hasattr(instance, 'position') and instance.position == new_pos:
            return

        # 1. 记录当前开启状态
        was_visible = instance.isVisible()

        # 2. 从原 Stack 物理移除
        self.top_stack.removeWidget(instance)
        self.bottom_stack.removeWidget(instance)

        # 3. 按钮栏 UI 调整
        self.tool_panel.add_button_to_layout(tool_name, pos_str)

        # 4. 更新实例属性
        instance.position = new_pos

        # 5. 如果搬迁前是打开的，搬迁后在对应位置打开
        if was_visible:
            self.switch_to(tool_name)
        else:
            self._update_splitter()

    def switch_to(self, tool_name):
        view = self.get_tool_instance(tool_name)
        if view is None: return
        self.tool_panel.set_checked(tool_name)

    def _show_top_tool(self, tool_name):
        view = self.get_tool_instance(tool_name)
        if hasattr(view, "set_allowed_update"):
            view.set_allowed_update(True)
        if self.top_stack.indexOf(view) == -1:
            self.top_stack.addWidget(view)
        self.top_stack.setCurrentWidget(view)
        self.top_stack.show()
        self._top_visible = True
        self._update_splitter()

    def _hide_top_tool(self, tool_name):
        view = self.get_tool_instance(tool_name)
        if hasattr(view, "set_allowed_update"):
            view.set_allowed_update(False)
        self.top_stack.hide()
        self._top_visible = False
        self._update_splitter()

    def _show_bottom_tool(self, tool_name):
        view = self.get_tool_instance(tool_name)
        if hasattr(view, "set_allowed_update"):
            view.set_allowed_update(True)
        if self.bottom_stack.indexOf(view) == -1:
            self.bottom_stack.addWidget(view)
        self.bottom_stack.setCurrentWidget(view)
        self.bottom_stack.show()
        self._bottom_visible = True
        self._update_splitter()

    def _hide_bottom_tool(self, tool_name):
        view = self.get_tool_instance(tool_name)
        if hasattr(view, "set_allowed_update"):
            view.set_allowed_update(False)
        self.bottom_stack.hide()
        self._bottom_visible = False
        self._update_splitter()

    def _update_splitter(self):
        if self.last_content_visible and not (self._top_visible or self._bottom_visible):
            self.splitter.setSizes([0, 0])
            self.page.hide_splitter()
            self.last_content_visible = False
            return
        elif not self.last_content_visible and (self._top_visible or self._bottom_visible):
            self.last_content_visible = True
            self.page.show_splitter()

        if self._top_visible and self._bottom_visible:
            self.splitter.setSizes([1, 1])
        elif self._top_visible:
            self.splitter.setSizes([1, 0])
        else:
            self.splitter.setSizes([0, 1])

    def _load_plugins(self, context_id):
        top_classes = []
        for name, entry in SideDockRegistry.get_all(context_id).items():
            # 先创建按钮
            self.tool_panel.create_button(entry.cls)
            # 再按初始位置摆放按钮
            pos_str = "top" if entry.position == DockPosition.TOP else "bottom"
            self.tool_panel.add_button_to_layout(name, pos_str)

            if entry.position == DockPosition.TOP:
                top_classes.append(entry.cls)

        if top_classes:
            first_cls = top_classes[0]
            QtCore.QTimer.singleShot(100, lambda: self._show_top_tool(first_cls.name))
            self.last_content_visible = True
            self.tool_panel._set_top_button_checked(first_cls)

    def _get_or_create_instance(self, cls: Type[ToolWindow]) -> ToolWindow:
        """根据 singleton 策略获取或创建实例，并将 button 注入"""
        self.setUpdatesEnabled(False)
        try:
            name = cls.name
            if cls.singleton and name in self._instances:
                return self._instances[name]

            # 【关键重构】从 tool_panel 获取对应的按钮实例
            btn_instance = self.tool_panel._button_by_name.get(name)

            # 注入 button 到插件类构造函数中
            instance = cls(self.page, button=btn_instance)

            # 初始化位置信息
            entry = SideDockRegistry._registries.get(self.context_id).get(name)
            instance.position = entry.position if entry else DockPosition.TOP

            if cls.singleton:
                self._instances[name] = instance
            return instance
        finally:
            self.setUpdatesEnabled(True)
            self.update()

    def get_tool_instance(self, name: str) -> Optional[ToolWindow]:
        entry = SideDockRegistry._registries.get(self.context_id).get(name)
        if entry is None: return None
        return self._get_or_create_instance(entry.cls)

    def cleanup(self):
        try:
            self.tool_panel.topToolChecked.disconnect(self._show_top_tool)
            self.tool_panel.topToolUnchecked.disconnect(self._hide_top_tool)
            self.tool_panel.bottomToolChecked.disconnect(self._show_bottom_tool)
            self.tool_panel.bottomToolUnchecked.disconnect(self._hide_bottom_tool)
            self.tool_panel.toolMoveRequested.disconnect(self._handle_tool_reposition)
        except:
            pass

        for name, instance in self._instances.items():
            if hasattr(instance, 'cleanup'): instance.cleanup()
            instance.setParent(None)
            instance.deleteLater()
        self._instances.clear()

        def clear_stacked(stack: QStackedWidget):
            while stack.count():
                widget = stack.widget(0)
                stack.removeWidget(widget)
                widget.deleteLater()

        clear_stacked(self.top_stack)
        clear_stacked(self.bottom_stack)
        self.splitter.deleteLater()
        self.tool_panel.deleteLater()