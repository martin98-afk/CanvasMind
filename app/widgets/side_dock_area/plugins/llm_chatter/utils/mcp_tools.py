# -*- coding: utf-8 -*-
"""
MCP 工具装饰器 - 通过装饰器注册函数为 MCP 工具
"""

import inspect
from typing import Callable, Dict, List, Any, Optional
from loguru import logger

_mcp_tools: Dict[str, Dict[str, Any]] = {}
_mcp_executors: Dict[str, Callable] = {}


def mcp_tool(
    name: str,
    description: str,
    parameters: Dict[str, Any],
):
    """
    MCP 工具装饰器

    用法:
        @mcp_tool(
            name="my_function",
            description="这是一个测试函数",
            parameters={
                "type": "object",
                "properties": {
                    "arg1": {"type": "string", "description": "参数1"},
                    "arg2": {"type": "integer", "description": "参数2"}
                },
                "required": ["arg1"]
            }
        )
        def my_function(arg1: str, arg2: int = 10) -> str:
            return f"{arg1} - {arg2}"
    """

    def decorator(func: Callable) -> Callable:
        tool_schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        }

        _mcp_tools[name] = tool_schema
        _mcp_executors[name] = func

        logger.info(f"[MCP] Registered tool: {name}")

        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        wrapper._mcp_tool_info = {
            "name": name,
            "schema": tool_schema,
        }

        return wrapper

    return decorator


def get_mcp_tools_schema() -> List[Dict]:
    """获取所有 MCP 工具的 schema"""
    return list(_mcp_tools.values())


def get_mcp_executor(name: str) -> Optional[Callable]:
    """获取 MCP 工具的执行器"""
    return _mcp_executors.get(name)


def execute_mcp_tool(name: str, arguments: Dict[str, Any]) -> Any:
    """执行 MCP 工具"""
    executor = get_mcp_executor(name)
    if not executor:
        return {"success": False, "error": f"Tool '{name}' not found"}

    try:
        sig = inspect.signature(executor)
        bound_args = {}

        for param_name, param in sig.parameters.items():
            if param_name in arguments:
                bound_args[param_name] = arguments[param_name]
            elif param.default is not inspect.Parameter.empty:
                bound_args[param_name] = param.default
            elif param.kind == inspect.Parameter.VAR_KEYWORD:
                bound_args.update(arguments)

        result = executor(**bound_args)
        return result
    except Exception as e:
        logger.error(f"[MCP] Error executing tool '{name}': {e}")
        return {"success": False, "error": str(e)}


def list_mcp_tools() -> List[str]:
    """列出所有已注册的 MCP 工具名称"""
    return list(_mcp_tools.keys())


def unregister_mcp_tool(name: str) -> bool:
    """注销 MCP 工具"""
    if name in _mcp_tools:
        del _mcp_tools[name]
        del _mcp_executors[name]
        logger.info(f"[MCP] Unregistered tool: {name}")
        return True
    return False


def merge_with_builtin_tools(builtin_tools: List[Dict]) -> List[Dict]:
    """合并 MCP 工具和内置工具"""
    return builtin_tools + get_mcp_tools_schema()
