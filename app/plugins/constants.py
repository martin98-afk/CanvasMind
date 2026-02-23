# -*- coding: utf-8 -*-
from enum import Enum


class PluginType(Enum):
    """插件类型枚举（与基类保持一致）"""
    NODE = "node"
    TRIGGER = "trigger"
