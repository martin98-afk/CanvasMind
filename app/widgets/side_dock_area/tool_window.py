# -*- coding: utf-8 -*-
from dataclasses import dataclass
from enum import Enum
from PyQt5.QtWidgets import QWidget

from app.utils.config import Settings


class DockPosition(Enum):
    TOP = "top"
    BOTTOM = "bottom"
    HIDDEN = "hidden"  # 不自动注册到 dock


class ToolWindow(QWidget):
    name: str = "Unnamed"
    icon = None
    singleton = True
    default_position: DockPosition = DockPosition.HIDDEN

    def __init__(self, page, button):
        super().__init__()
        self.homepage = page
        self.button = button

        # --- 统一字体设置逻辑 ---
        self._init_unified_font()

        self.setup_ui()

    def _init_unified_font(self):
        """
        在基类中统一配置字体
        """
        # 1. 获取字体名称 (这里替换为你实际获取配置的代码)
        try:
            font_name = Settings.get_instance().canvas_font_type.value
        except Exception:
            font_name = "Microsoft YaHei"  # 默认字体

        # 2. 方案 A：使用 setFont (基础设置)
        font = self.font()
        font.setFamily(font_name)
        self.setFont(font)

        # 3. 方案 B：使用 StyleSheet (强制穿透解决嵌套控件无效问题)
        self.setStyleSheet(f"""
            ToolWindow, QWidget {{
                font-family: "{font_name}";
            }}
            /* 针对某些特殊控件的补充（如按钮、标签） */
            QLabel, QPushButton, QLineEdit, QComboBox, QTreeWidget, QTableWidget {{
                font-family: "{font_name}";
            }}
        """)

    def setup_ui(self):
        raise NotImplementedError

    def cleanup(self):
        pass

@dataclass
class DockItem:
    name: str
    widget: ToolWindow
    position: DockPosition  # TOP or BOTTOM
    order: int              # 在同 position 内的排序索引