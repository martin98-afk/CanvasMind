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
        self._canvas_tools_executor = None
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
            return self._builtin_tools.todo_list
        return []

    def clear_todo_list(self):
        """清空待办事项列表"""
        if self._builtin_tools:
            self._builtin_tools.todo_clear()

    def register_custom_tool(self, name: str, handler: Callable):
        """注册自定义工具"""
        self._custom_tools[name] = handler
        logger.info(f"[ToolExecutor] Registered custom tool: {name}")

    def set_memory_manager(self, memory_manager):
        if self._builtin_tools:
            self._builtin_tools.set_memory_manager(memory_manager)
            logger.info("[ToolExecutor] MemoryManager attached to BuiltinTools")

    def set_llm_config_getter(self, getter: Callable):
        if self._builtin_tools:
            self._builtin_tools.set_llm_config_getter(getter)
            logger.info("[ToolExecutor] LLM config getter attached to BuiltinTools")

    def set_canvas_tools_executor(self, executor):
        self._canvas_tools_executor = executor
        logger.info("[ToolExecutor] Canvas tools executor attached")

    def set_session_messages_getter(self, getter: Callable):
        if self._builtin_tools:
            self._builtin_tools.set_session_messages_getter(getter)
            logger.info(
                "[ToolExecutor] Session messages getter attached to BuiltinTools"
            )

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
                path=args.get("path"),  # 统一使用 path
                offset=args.get("offset", 1),
                limit=args.get("limit", 500),  # 建议默认值设为 500，防止 Token 溢出
            ),
            "write": lambda: self._builtin_tools.write_file(
                path=args.get("path"), content=args.get("content", "")
            ),
            "edit": lambda: self._builtin_tools.edit_file(
                path=args.get("path"),
                oldString=args.get("oldString", ""),
                newString=args.get("newString", ""),
                replaceAll=args.get("replaceAll", False),
            ),
            "multiedit": lambda: self._builtin_tools.multi_edit(
                path=args.get("path"),
                edits=args.get("edits", []),
            ),
            "grep": lambda: self._builtin_tools.grep_files(
                pattern=args.get("pattern"),
                path=args.get("path", "."),  # 默认当前路径
                include=args.get("include"),
            ),
            "glob": lambda: self._builtin_tools.glob_files(
                pattern=args.get("pattern"),
                path=args.get("path", "."),  # 默认当前路径
            ),
            "list": lambda: self._builtin_tools.list_directory(
                path=args.get("path", ".")  # 默认当前路径
            ),
            "patch": lambda: self._builtin_tools.apply_patch(
                args.get("path"), args.get("patch_content", "")
            ),
            "git_status": lambda: self._builtin_tools.git_status(args.get("path")),
            "git_log": lambda: self._builtin_tools.git_log(
                args.get("path"), args.get("max_count", 10)
            ),
            "git_diff": lambda: self._builtin_tools.git_diff(
                args.get("ref1"), args.get("ref2"), args.get("path")
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
            "scan_repo": lambda: self._builtin_tools.scan_repo(
                args.get("path"), args.get("max_depth", 2)
            ),
            "stage_files": lambda: self._builtin_tools.stage_files(
                args.get("files", [])
            ),
            "run_verify": lambda: self._builtin_tools.run_verify(
                args.get("command", ""), args.get("timeout", 120)
            ),
            "get_diagnostics": lambda: self._builtin_tools.get_diagnostics(
                args.get("file_path", ""), args.get("language")
            ),
            "summarize_changes": lambda: self._builtin_tools.summarize_changes(
                args.get("text", ""), args.get("limit", 1200)
            ),
            "memory_list": lambda: self._builtin_tools.memory_list(
                args.get("limit", 10),
                args.get("include_disabled", False),
            ),
            "memory_search": lambda: self._builtin_tools.memory_search(
                args.get("query", ""),
                args.get("limit", 8),
                args.get("include_disabled", False),
            ),
            "memory_save": lambda: self._builtin_tools.memory_save(
                args.get("content", ""),
                args.get("confidence", 0.8),
                args.get("source", "assistant"),
                args.get("conflict_group", ""),
            ),
            "memory_consolidate": lambda: self._builtin_tools.memory_consolidate(
                args.get("max_items", 3),
                args.get("save", True),
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
            "list_webhooks": lambda: self._builtin_tools.list_canvases(),
            "trigger_webhook": lambda: self._builtin_tools.trigger_canvas(
                args.get("endpoint", ""),
                args.get("data"),
                args.get("callback_url"),
                args.get("timeout", 300),
            ),
        }

        executor = tool_map.get(tool_name)
        if executor:
            try:
                return executor()
            except Exception as e:
                return ToolResult(False, error=f"Execution error: {str(e)}")

        if self._canvas_tools_executor and tool_name.startswith("canvas_"):
            return self._execute_canvas_tool(tool_name, args)

        return ToolResult(False, error=f"Unknown tool: {tool_name}")

    def _execute_canvas_tool(self, tool_name: str, args: dict):
        if not self._canvas_tools_executor:
            return ToolResult(False, error="Canvas tools executor not available")

        canvas_tool_map = {
            "canvas_run_node": lambda: self._canvas_tools_executor.canvas_run_node(
                mode=args.get("mode", "node"), node_name=args.get("node_name")
            ),
            "canvas_get_logs": lambda: self._canvas_tools_executor.canvas_get_logs(
                node_name=args.get("node_name", ""),
                log_type=args.get("log_type", "historical"),
            ),
            "canvas_modify_and_run": lambda: self._canvas_tools_executor.canvas_modify_and_run(
                node_name=args.get("node_name", ""), code=args.get("code", "")
            ),
            "canvas_list_nodes": lambda: self._canvas_tools_executor.canvas_list_nodes(),
            "canvas_set_node_property": lambda: self._canvas_tools_executor.canvas_set_node_property(
                node_name=args.get("node_name", ""),
                properties=args.get("properties", {}),
                target=args.get("target"),
            ),
            "canvas_get_node_property": lambda: self._canvas_tools_executor.canvas_get_node_property(
                node_name=args.get("node_name", ""),
                property_names=args.get("property_names"),
            ),
        }

        executor = canvas_tool_map.get(tool_name)
        if executor:
            try:
                return executor()
            except Exception as e:
                return ToolResult(False, error=f"Canvas tool execution error: {str(e)}")
        return ToolResult(False, error=f"Unknown canvas tool: {tool_name}")

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
            self._builtin_tools._task_tools._sub_agent_manager = sub_agent_manager
            logger.info(
                "[ToolExecutor] SubAgentManager attached to BuiltinTools and TaskTools"
            )

    def set_stage_callback(self, callback):
        """设置 stage 切换回调"""
        if self._builtin_tools:
            self._builtin_tools._set_stage_callback = callback
            logger.info("[ToolExecutor] Stage callback attached to BuiltinTools")

    @property
    def file_modified_signal(self):
        """获取文件修改信号，用于连接"""
        if self._builtin_tools:
            return self._builtin_tools.fileModified
        return None
