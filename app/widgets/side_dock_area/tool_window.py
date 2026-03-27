# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Type, Dict, Any

from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QIcon

from app.utils.config import Settings


class DockPosition(Enum):
    TOP = "top"
    BOTTOM = "bottom"
    HIDDEN = "hidden"


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


class ToolWindow(QWidget):
    name: str = "Unnamed"
    icon = None
    singleton = True
    default_position: DockPosition = DockPosition.HIDDEN

    _manifest: Optional[PluginManifest] = None

    def __init__(self, page, button):
        super().__init__()
        self.homepage = page
        self.button = button

        self._init_unified_font()

        self.setup_ui()

    def _init_unified_font(self):
        """
        在基类中统一配置字体
        """
        # 1. 获取字体名称 (这里替换为你实际获取配置的代码)
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
