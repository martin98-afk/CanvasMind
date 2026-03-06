# -*- coding: utf-8 -*-
"""
工具执行器模块 - 统一处理各种工具调用
"""

import json
from typing import Any, Dict, Optional, Callable
from loguru import logger

from app.widgets.side_dock_area.plugins.llm_chatter.utils.builtin_tools import (
    BuiltinTools,
    ToolResult,
)


class ToolExecutor:
    """工具执行器 - 统一调度各种工具"""

    def __init__(self, homepage=None, workdir: str = None):
        self._homepage = homepage
        self._builtin_tools: Optional[BuiltinTools] = None
        self._workdir = workdir
        self._custom_tools: Dict[str, Callable] = {}

        self._initialize_builtin_tools()

    def _initialize_builtin_tools(self):
        """初始化内置工具"""
        import os
        from pathlib import Path

        workdir = self._workdir
        if not workdir:
            try:
                from app.utils.utils import resource_path

                workdir = resource_path("app")
            except Exception:
                workdir = os.path.dirname(
                    os.path.dirname(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    )
                )

        try:
            if (
                hasattr(self._homepage, "workflow_name")
                and self._homepage.workflow_name
            ):
                canvas_name = self._homepage.workflow_name
                workspace_path = (
                    Path(workdir)
                    / "canvas_files"
                    / "workflows"
                    / canvas_name
                    / "workspace"
                )
                if workspace_path.exists():
                    workdir = str(workspace_path)
        except Exception:
            pass

        logger.info(f"[ToolExecutor] Initialized with workdir: {workdir}")
        self._builtin_tools = BuiltinTools(self._homepage, workdir)

    @property
    def builtin_tools(self) -> Optional[BuiltinTools]:
        return self._builtin_tools

    @property
    def todo_list(self):
        """获取待办事项列表"""
        if self._builtin_tools:
            return self._builtin_tools._todo_list
        return []

    def register_custom_tool(self, name: str, handler: Callable):
        """注册自定义工具"""
        self._custom_tools[name] = handler
        logger.info(f"[ToolExecutor] Registered custom tool: {name}")

    def execute(self, tool_name: str, args: dict) -> ToolResult:
        """
        执行工具调用

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            ToolResult: 执行结果
        """
        logger.info(f"[ToolExecutor] Executing tool: {tool_name}, args: {args}")

        if tool_name in self._custom_tools:
            try:
                result = self._custom_tools[tool_name](args)
                return ToolResult(True, content=result)
            except Exception as e:
                return ToolResult(False, error=f"Custom tool error: {str(e)}")

        tool_map = {
            "read": lambda: self._builtin_tools.read_file(
                args.get("filePath"), args.get("offset", 1), args.get("limit", 2000)
            ),
            "write": lambda: self._builtin_tools.write_file(
                args.get("filePath"), args.get("content", "")
            ),
            "edit": lambda: self._builtin_tools.edit_file(
                args.get("filePath"),
                args.get("oldString", ""),
                args.get("newString", ""),
                args.get("replaceAll", False),
            ),
            "grep": lambda: self._builtin_tools.grep_files(
                args.get("pattern"), args.get("path"), args.get("include")
            ),
            "glob": lambda: self._builtin_tools.glob_files(
                args.get("pattern"), args.get("path")
            ),
            "list": lambda: self._builtin_tools.list_directory(args.get("path")),
            "patch": lambda: self._builtin_tools.apply_patch(
                args.get("filePath"), args.get("patch_content", "")
            ),
            "bash": lambda: self._builtin_tools.execute_bash(
                args.get("command", ""), args.get("timeout", 120)
            ),
            "webfetch": lambda: self._builtin_tools.fetch_web(
                args.get("url", ""), args.get("format", "markdown")
            ),
            "websearch": lambda: self._builtin_tools.search_web(
                args.get("query", ""), args.get("num_results", 10)
            ),
            "todowrite": lambda: self._builtin_tools.todo_write(args.get("todos", [])),
            "todoread": lambda: self._builtin_tools.todo_read(),
            "task": lambda: self._builtin_tools.task_execute(
                args.get("agent", ""),
                args.get("description", ""),
                args.get("context", ""),
            ),
            "skill": lambda: self._builtin_tools.load_skill(args.get("name", "")),
            "list_skills": lambda: self._builtin_tools.list_skills(),
            "question": lambda: self._builtin_tools.ask_question(
                args.get("question", ""),
                args.get("options"),
                args.get("multiple", False),
            ),
        }

        executor = tool_map.get(tool_name)
        if executor:
            try:
                return executor()
            except Exception as e:
                return ToolResult(False, error=f"Execution error: {str(e)}")

        return ToolResult(False, error=f"Unknown tool: {tool_name}")

    def execute_skill(self, method: str, params: dict) -> dict:
        """执行技能"""
        if hasattr(self._homepage, "execute_skill"):
            try:
                return self._homepage.execute_skill(method, params)
            except Exception as e:
                logger.error(f"[ToolExecutor] Skill execution failed: {e}")
                return {"error": str(e)}
        return {"error": "Skill execution not available"}

    def reload_workdir(self, workdir: str):
        """重新加载工作目录"""
        self._workdir = workdir
        self._initialize_builtin_tools()

    def set_sub_agent_manager(self, sub_agent_manager):
        """设置子智能体管理器"""
        if self._builtin_tools:
            self._builtin_tools._sub_agent_manager = sub_agent_manager
            logger.info("[ToolExecutor] SubAgentManager attached to BuiltinTools")
