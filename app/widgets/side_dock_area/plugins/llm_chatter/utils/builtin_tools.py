# -*- coding: utf-8 -*-
"""
内置工具模块 - 兼容层
将导入转发到新的 tools 包
"""

from app.widgets.side_dock_area.plugins.llm_chatter.tools import (
    BuiltinTools,
    ToolResult,
    create_builtin_tools,
    get_builtin_tools_schema,
)

__all__ = [
    "BuiltinTools",
    "ToolResult",
    "create_builtin_tools",
    "get_builtin_tools_schema",
]
