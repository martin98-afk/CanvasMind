# -*- coding: utf-8 -*-
from typing import Dict, Type
from .tool_window import ToolWindow, DockPosition


class SideDockRegistry:
    _instance = None
    _entries: Dict[str, 'DockEntry'] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(
            cls,
            name: str,
            window_class: Type[ToolWindow],
            position: DockPosition = None
    ):
        if position is None:
            position = window_class.default_position
        cls._entries[name] = DockEntry(window_class, position)

    @classmethod
    def get_all(cls):
        return cls._entries.copy()


class DockEntry:
    def __init__(self, cls: Type[ToolWindow], position: DockPosition):
        self.cls = cls
        self.position = position
