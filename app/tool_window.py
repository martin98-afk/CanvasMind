# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Any

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from qfluentwidgets import TransparentToolButton

from app.utils.config import Settings


class DockPosition(Enum):
    TOP = "top"
    BOTTOM = "bottom"
    HIDDEN = "hidden"


class DockCategory(Enum):
    CANVAS = "运行画布"
    COMPONENT = "组件开发"
    PROJECT = "项目管理"


@dataclass
class PluginManifest:
    name: str
    display_name: str = ""
    icon: Optional[Any] = None
    position: DockPosition = DockPosition.HIDDEN
    shortcut: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    singleton: bool = True
    auto_activate: bool = True


class PluginProtocol(ABC):
    @abstractmethod
    def get_manifest(self) -> PluginManifest:
        raise NotImplementedError

    def on_activate(self):
        pass

    def on_deactivate(self):
        pass


class ToolWindowTitleBar(QWidget):
    switchLayoutRequested = pyqtSignal()
    popupRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._custom_buttons = []
        self._popup_mode_buttons = []
        self._is_compact = False
        self._setup_ui()

    def _setup_ui(self):
        from qfluentwidgets import (
            ToolButton,
            IconWidget,
            isDarkTheme,
        )
        from app.utils.utils import get_icon

        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(6)

        self._icon_widget = IconWidget(self)
        self._icon_widget.setFixedSize(16, 16)

        self._title_label = QLabel(self)
        self._title_label.setObjectName("titleLabel")

        layout.addWidget(self._icon_widget)
        layout.addWidget(self._title_label)
        layout.addStretch()

        self._action_container = QWidget(self)
        self._action_container.setObjectName("actionContainer")
        self._action_layout = QHBoxLayout(self._action_container)
        self._action_layout.setContentsMargins(0, 0, 0, 0)
        self._action_layout.setSpacing(4)
        layout.addWidget(self._action_container)

        self._switch_layout_btn = TransparentToolButton(get_icon("上下切换"), self)
        self._switch_layout_btn.setFixedSize(24, 24)
        self._switch_layout_btn.setToolTip("切换到上/下半区")
        self._switch_layout_btn.clicked.connect(self._on_switch_clicked)

        self._popup_btn = TransparentToolButton(get_icon("弹出窗"), self)
        self._popup_btn.setFixedSize(24, 24)
        self._popup_btn.setToolTip("弹出窗口")
        self._popup_btn.clicked.connect(self._on_popup_clicked)

        layout.addWidget(self._switch_layout_btn)
        layout.addWidget(self._popup_btn)

        try:
            font_name = Settings.get_instance().llm_font_family.value
        except Exception:
            try:
                font_name = Settings.get_instance().canvas_font_selected.value
            except Exception:
                font_name = "Microsoft YaHei"

        if isDarkTheme():
            bg = "#2d2d2d"
            title_color = "#e0e0e0"
            btn_hover = "rgba(255, 255, 255, 15)"
            border_color = "#3a3a3a"
        else:
            bg = "#f5f5f5"
            title_color = "#333333"
            btn_hover = "rgba(0, 0, 0, 10)"
            border_color = "#e0e0e0"

        self.setStyleSheet(f"""
            ToolWindowTitleBar {{
                background-color: {bg};
                border-bottom: 1px solid {border_color};
            }}
            #titleLabel {{
                color: {title_color};
                font-size: 15px;
                font-weight: bold;
                font-family: "{font_name}";
                padding: 0 4px;
            }}
            #actionContainer {{
                background-color: transparent;
            }}
            ToolButton {{
                background-color: transparent;
                border: none;
                border-radius: 4px;
                padding: 2px;
            }}
            ToolButton:hover {{
                background-color: {btn_hover};
            }}
            ToolButton:pressed {{
                background-color: {btn_hover};
            }}
        """)

    def set_icon(self, icon):
        self._icon_widget.setIcon(icon)

    def set_title(self, title):
        self._title_label.setText(title)

    def add_button(self, widget, stretch=0):
        self._action_layout.insertWidget(
            self._action_layout.count() - 2, widget, stretch=stretch
        )
        self._custom_buttons.append(widget)

    def insert_button(self, index, widget, stretch=0):
        self._action_layout.insertWidget(index, widget, stretch=stretch)
        self._custom_buttons.append(widget)

    def remove_button(self, widget):
        self._action_layout.removeWidget(widget)
        if widget in self._custom_buttons:
            self._custom_buttons.remove(widget)
        widget.setParent(None)

    def add_popup_button(self, widget):
        title_layout = self.layout()
        if not title_layout:
            return
        switch_index = title_layout.indexOf(self._switch_layout_btn)
        title_layout.insertWidget(switch_index, widget)
        self._popup_mode_buttons.append(widget)

    def clear_popup_buttons(self):
        title_layout = self.layout()
        if not title_layout:
            return
        for btn in self._popup_mode_buttons:
            title_layout.removeWidget(btn)
            btn.setParent(None)
        self._popup_mode_buttons.clear()

    def set_compact(self, compact):
        self._is_compact = compact
        self._switch_layout_btn.setVisible(not compact)
        self._popup_btn.setVisible(not compact)
        self.setFixedHeight(24 if compact else 32)

    def _on_switch_clicked(self):
        self.switchLayoutRequested.emit()

    def _on_popup_clicked(self):
        self.popupRequested.emit()


class ToolWindow(QWidget):
    name: str = "Unnamed"
    icon = None
    singleton = True
    default_position: DockPosition = DockPosition.HIDDEN
    display_order: int = 999

    _manifest: Optional[PluginManifest] = None

    def __init__(self, page, button):
        super().__init__()
        self.homepage = page
        self.button = button
        self._title_bar = None
        self._content_widget = None
        self._layout_mode = "vertical"

        self._init_unified_font()

        self._init_title_bar()
        self.setup_ui()

    def _init_title_bar(self):
        if self._title_bar:
            return

        self._title_bar = ToolWindowTitleBar(self)
        self._title_bar.set_icon(self.icon)
        self._title_bar.set_title(self.name)
        self._title_bar.switchLayoutRequested.connect(self._handle_switch_layout)
        self._title_bar.popupRequested.connect(self._request_popup)
        self._title_bar.hide()
        self._setup_title_bar()

    def _setup_title_bar(self):
        pass

    switchLayoutRequested = pyqtSignal()

    def _handle_switch_layout(self):
        self._layout_mode = (
            "horizontal" if self._layout_mode == "vertical" else "vertical"
        )
        self._on_layout_changed()
        self.switchLayoutRequested.emit()

    def _toggle_layout(self):
        if self._layout_mode == "vertical":
            self._layout_mode = "horizontal"
        else:
            self._layout_mode = "vertical"
        self._on_layout_changed()

    def _on_layout_changed(self):
        pass

    def _request_popup(self):
        if hasattr(self.homepage, "_handle_tool_popup"):
            self.homepage._handle_tool_popup(self.name)

    def register_action_button(self, widget):
        if self._title_bar:
            self._title_bar.add_button(widget)

    def get_title_bar(self):
        return self._title_bar

    def _init_unified_font(self):
        try:
            font_name = Settings.get_instance().llm_font_family.value
        except Exception:
            try:
                font_name = Settings.get_instance().canvas_font_selected.value
            except Exception:
                font_name = "Microsoft YaHei"

        font = self.font()
        font.setFamily(font_name)
        self.setFont(font)

        self.setStyleSheet(f"""
            ToolWindow, QWidget {{
                font-family: "{font_name}";
            }}
            QLabel, QPushButton, QLineEdit, QComboBox, QTreeWidget, QTableWidget {{
                font-family: "{font_name}";
            }}
        """)

    def setup_ui(self):
        raise NotImplementedError

    def cleanup(self):
        pass

    @classmethod
    def get_manifest(cls) -> PluginManifest:
        if cls._manifest is not None:
            return cls._manifest
        return PluginManifest(
            name=cls.name,
            display_name=getattr(cls, "display_name", cls.name),
            icon=cls.icon,
            position=cls.default_position,
            singleton=cls.singleton,
            auto_activate=False,
        )


@dataclass
class DockItem:
    name: str
    widget: ToolWindow
    position: DockPosition  # TOP or BOTTOM
    order: int  # 在同 position 内的排序索引
