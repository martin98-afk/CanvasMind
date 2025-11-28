# -*- coding: utf-8 -*-
from typing import Dict, Type
from .tool_window import ToolWindow, DockPosition


class SideDockRegistry:
    _instance = None
    _registries: Dict[str, Dict[str, 'DockEntry']] = {}  # {context_id: entries}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(
        cls,
        context_id: str,
        name: str,
        window_class: Type[ToolWindow],
        position: DockPosition = None
    ):
        if context_id not in cls._registries:
            cls._registries[context_id] = {}
        entries = cls._registries[context_id]
        if position is None:
            position = window_class.default_position
        entries[name] = DockEntry(window_class, position)

    @classmethod
    def get_all(cls, context_id: str):
        return cls._registries.get(context_id, {}).copy()

    @classmethod
    def clear_context(cls, context_id: str):
        cls._registries.pop(context_id, None)

class DockEntry:
    def __init__(self, cls: Type[ToolWindow], position: DockPosition):
        self.cls = cls
        self.position = position
