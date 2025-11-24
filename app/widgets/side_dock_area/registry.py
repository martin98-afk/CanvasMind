# -*- coding: utf-8 -*-
from typing import Dict, Type
from .tool_window import ToolWindow

class SideDockRegistry:
    _instance = None
    _windows: Dict[str, Type[ToolWindow]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, name: str, window_class: Type[ToolWindow]):
        cls._windows[name] = window_class

    @classmethod
    def get_all(cls):
        return cls._windows.copy()