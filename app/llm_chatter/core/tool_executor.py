# -*- coding: utf-8 -*-
"""
工具执行器模块 - 统一处理各种工具调用
"""
from loguru import logger
from typing import Dict, Optional, Callable

from app.llm_chatter.tools import BuiltinTools, ToolResult
from app.llm_chatter.utils.file_operation_recorder import (
    FileOperationRecorder,
)


class ToolExecutor:
    """工具执行器 - 统一调度各种工具"""

    # 需要记录的文件操作
    _FILE_OPS_TO_TRACK = {
        "write", "edit", "multiedit", "patch"
    }

    def __init__(self, homepage=None, workdir: str = None):
        self._homepage = homepage
        self._builtin_tools: Optional[BuiltinTools] = None
        self._canvas_tools_executor = None
        self._workdir = workdir
        self._custom_tools: Dict[str, Callable] = {}
        self._session_id: Optional[str] = None
        self._call_id: Optional[str] = None

        # 文件操作记录器
        self._file_recorder: Optional[FileOperationRecorder] = None

        self._initialize_builtin_tools()

    def _initialize_builtin_tools(self):
        """初始化内置工具"""
        import os
        from pathlib import Path

        workdir = self._workdir
        if not workdir:
            try:
                from app.utils.utils import resource_path

                workdir = resource_path("")
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

    def is_valid(self) -> bool:
        """检查 ToolExecutor 是否仍然有效（UI 未关闭）"""
        if self._builtin_tools is None:
            return False
        # 检查 QObject 是否已被删除
        try:
            # 如果对象已删除，尝试访问 sip 会有异常
            from PyQt5 import sip
            if sip.isdeleted(self._builtin_tools):
                return False
        except Exception:
            pass
        return True

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

    def reset_session_state(self):
        """Reset session-scoped state when switching sessions"""
        if self._builtin_tools:
            self._builtin_tools.reset_session_state()

    def _init_file_recorder(self):
        """初始化文件操作记录器"""
        if self._file_recorder is None:
            self._file_recorder = FileOperationRecorder()

    def set_session_context(self, session_id: str, call_id: str = None):
        """
        设置会话上下文（用于文件操作记录）

        Args:
            session_id: 会话 ID
            call_id: 当前调用 ID（可选）
        """
        self._session_id = session_id
        self._call_id = call_id
        self._init_file_recorder()

    def set_call_id(self, call_id: str):
        """设置当前调用 ID"""
        self._call_id = call_id

    @property
    def file_recorder(self) -> Optional[FileOperationRecorder]:
        """获取文件操作记录器"""
        return self._file_recorder

    def _record_file_operation_before(self, tool_name: str, args: dict):
        """
        在文件操作执行前记录备份信息

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            str: 文件完整路径，用于后续的编辑后备份
        """
        if tool_name not in self._FILE_OPS_TO_TRACK:
            return None

        if not self._session_id:
            return None

        if not self._call_id:
            return None

        if not self._file_recorder:
            return None

        # 获取文件路径
        path = args.get("path")
        if not path:
            return None

        logger.debug(f"[ToolExecutor] 准备记录文件操作: tool={tool_name}, path={path}")

        # 处理 URL 格式的文件路径 (如 file:/D:/xxx 或 file:///D:/xxx)
        import re
        if path.startswith("file:"):
            # 移除 file: 前缀，处理单斜杠或双斜杠
            path = re.sub(r'^file:/{1,3}', '', path)


        # 获取完整的文件路径
        if hasattr(self._builtin_tools, "_file_tools"):
            full_path = self._builtin_tools._file_tools._resolve_path(path)
        else:
            from pathlib import Path
            full_path = Path(path).resolve()



        # 记录操作（内部会处理文件不存在的情况）
        try:
            backup_path = self._file_recorder.record_operation(
                session_id=self._session_id,
                call_id=self._call_id,
                tool_name=tool_name,
                file_path=str(full_path)
            )
            if backup_path:
                logger.info(f"[FileRecorder] 已备份: {full_path} -> {backup_path}")
            else:
                # 文件不存在（如新建文件 write_file），跳过记录是正常的
                logger.debug(f"[ToolExecutor] 文件操作记录返回 None")
        except Exception as e:
            # 记录失败不阻塞工具执行
            logger.warning(f"[ToolExecutor] 记录文件操作失败: {e}")

        return str(full_path)

    def _record_file_operation_after(self, tool_name: str, args: dict, file_path_before: str):
        """
        在文件操作执行成功后备份编辑后的文件

        Args:
            tool_name: 工具名称
            args: 工具参数
            file_path_before: 执行前的文件路径
        """
        if not file_path_before:
            return

        if tool_name not in self._FILE_OPS_TO_TRACK:
            return

        if not self._session_id or not self._call_id:
            return

        if not self._file_recorder:
            return

        try:
            self._file_recorder.record_after_operation(
                session_id=self._session_id,
                call_id=self._call_id,
                tool_name=tool_name,
                file_path=file_path_before
            )
        except Exception as e:
            # 记录失败不阻塞主流程
            logger.warning(f"[ToolExecutor] 编辑后备份失败: {e}")

    def cancel_tool(self, tool_name: str = None):
        """取消正在执行的工具
        
        Args:
            tool_name: 要取消的工具名称，None 表示取消所有
        """
        if self._builtin_tools:
            # 取消文件工具（如 grep）
            if self._builtin_tools._file_tools:
                self._builtin_tools._file_tools.cancel()
        
        logger.info(f"[ToolExecutor] Tool cancelled: {tool_name or 'all'}")

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

    # 工具必需参数定义
    REQUIRED_ARGS = {
        "read": ["path"],
        "write": ["path", "content"],
        "edit": ["path", "oldString", "newString"],
        "multiedit": ["path", "edits"],
        "grep": ["pattern"],
        "glob": ["pattern"],
        "patch": ["path", "patch_content"],
        "bash": ["command"],
        "webfetch": ["url"],
        "websearch": ["query"],
        "scan_repo": [],
        "stage_files": ["files"],
        "run_verify": [],
        "git_status": [],
        "git_log": [],
        "git_diff": [],
        "get_diagnostics": ["file_path"],
        "summarize_changes": ["text"],
        "memory_list": [],
        "memory_search": ["query"],
        "memory_save": ["content"],
        "memory_consolidate": [],
        "todowrite": ["todos"],
        "todoread": [],
        "task": ["agent", "description"],
        "skill": ["name"],
        "list_skills": [],
        "question": ["question"],
        "list_webhooks": [],
        "trigger_webhook": ["endpoint"],
    }

    def execute(self, tool_name: str, args: dict, cancelled_ref: list = None) -> ToolResult:
        """
        执行工具调用

        Args:
            tool_name: 工具名称
            args: 工具参数
            cancelled_ref: 取消标志引用 [bool]

        Returns:
            ToolResult: 执行结果
        """
        # 检查 ToolExecutor 是否仍然有效（API 模式下 UI 可能已关闭）
        if not self.is_valid():
            logger.warning(f"[ToolExecutor] ToolExecutor is invalid (UI may be closed)")
            return ToolResult(False, error="UI has been closed, tool execution unavailable")

        logger.info(f"[ToolExecutor] Executing tool: {tool_name}, args: {args}")

        # 校验必需参数
        if tool_name in self.REQUIRED_ARGS:
            required = self.REQUIRED_ARGS[tool_name]
            missing = [p for p in required if not args.get(p)]
            if missing:
                return ToolResult(False, error=f"Missing required arguments: {missing}")

        # 对于耗时工具（如 grep, bash, webfetch, websearch），使用异步执行
        if tool_name == "grep":
            return self._execute_grep_async(args, cancelled_ref)
        elif tool_name == "webfetch":
            return self._execute_webfetch_async(args, cancelled_ref)
        elif tool_name == "websearch":
            return self._execute_websearch_async(args, cancelled_ref)

        # 文件操作前记录（用于撤销）
        file_path_before = self._record_file_operation_before(tool_name, args)

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
                show_line_numbers=args.get("show_line_numbers", False),
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
                result = executor()
                # 文件操作成功后备份编辑后的文件（用于差异对比）
                if tool_name in self._FILE_OPS_TO_TRACK and result and result.success:
                    self._record_file_operation_after(tool_name, args, file_path_before)
                return result
            except Exception as e:
                return ToolResult(False, error=f"Execution error: {str(e)}")

        if self._canvas_tools_executor and tool_name.startswith("canvas_"):
            return self._execute_canvas_tool(tool_name, args)

        return ToolResult(False, error=f"Unknown tool: {tool_name}")

    def _execute_grep_async(self, args: dict, cancelled_ref: list = None) -> ToolResult:
        """
        异步执行 grep，使用子线程，完成后返回结果
        
        Args:
            args: 工具参数
            cancelled_ref: 取消标志引用 [bool]
        
        Returns:
            ToolResult: 执行结果
        """
        if not self._builtin_tools or not self._builtin_tools._file_tools:
            return ToolResult(False, error="FileTools not available")
        
        pattern = args.get("pattern", "")
        path = args.get("path", ".")
        include = args.get("include")
        
        # 使用 FileTools 的异步接口
        result_holder = [None]
        finished = [False]
        
        def on_grep_done(result):
            result_holder[0] = result
            finished[0] = True
        
        # 启动异步 grep
        self._builtin_tools._file_tools.grep_files(
            pattern=pattern,
            path=path,
            include=include,
            callback=on_grep_done
        )
        
        # 使用定时器循环处理主线程事件，这样取消信号可以被处理
        def wait_for_result():
            from PyQt5.QtWidgets import QApplication
            QApplication.processEvents()
            
            if finished[0]:
                return
            
            # 检查取消标志
            if cancelled_ref is not None and cancelled_ref[0]:
                self._builtin_tools._file_tools.cancel()
                result_holder[0] = ToolResult(False, error="用户中止")
                finished[0] = True
                return
            
            # 继续等待
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(50, wait_for_result)
        
        wait_for_result()
        
        # 等待完成
        while not finished[0]:
            from PyQt5.QtWidgets import QApplication
            QApplication.processEvents()
            import time
            time.sleep(0.05)
        
        return result_holder[0] if result_holder[0] else ToolResult(False, error="Grep failed")

    def _execute_webfetch_async(self, args: dict, cancelled_ref: list = None) -> ToolResult:
        """异步执行网页抓取"""
        if not self._builtin_tools or not self._builtin_tools._web_tools:
            return ToolResult(False, error="WebTools not available")
        
        url = args.get("url", "")
        format = args.get("format", "markdown")
        max_chars = args.get("max_chars", 26000)
        
        result_holder = [None]
        finished = [False]
        
        def on_fetch_done(result):
            result_holder[0] = result
            finished[0] = True
        
        self._builtin_tools._web_tools.fetch_web(
            url=url, format=format, max_chars=max_chars,
            callback=on_fetch_done, cancelled_ref=cancelled_ref
        )
        
        def wait_for_result():
            from PyQt5.QtWidgets import QApplication
            QApplication.processEvents()
            if finished[0]: return
            if cancelled_ref is not None and cancelled_ref[0]:
                result_holder[0] = ToolResult(False, error="用户中止")
                finished[0] = True
                return
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(50, wait_for_result)
        
        wait_for_result()
        
        while not finished[0]:
            from PyQt5.QtWidgets import QApplication
            QApplication.processEvents()
            import time
            time.sleep(0.05)
        
        return result_holder[0] if result_holder[0] else ToolResult(False, error="WebFetch failed")

    def _execute_websearch_async(self, args: dict, cancelled_ref: list = None) -> ToolResult:
        """异步执行网络搜索"""
        if not self._builtin_tools or not self._builtin_tools._web_tools:
            return ToolResult(False, error="WebTools not available")
        
        query = args.get("query", "")
        num_results = args.get("num_results", 10)
        
        result_holder = [None]
        finished = [False]
        
        def on_search_done(result):
            result_holder[0] = result
            finished[0] = True
        
        self._builtin_tools._web_tools.search_web(
            query=query, num_results=num_results,
            callback=on_search_done, cancelled_ref=cancelled_ref
        )
        
        def wait_for_result():
            from PyQt5.QtWidgets import QApplication
            QApplication.processEvents()
            if finished[0]: return
            if cancelled_ref is not None and cancelled_ref[0]:
                result_holder[0] = ToolResult(False, error="用户中止")
                finished[0] = True
                return
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(50, wait_for_result)
        
        wait_for_result()
        
        while not finished[0]:
            from PyQt5.QtWidgets import QApplication
            QApplication.processEvents()
            import time
            time.sleep(0.05)
        
        return result_holder[0] if result_holder[0] else ToolResult(False, error="WebSearch failed")

    def _execute_canvas_tool(self, tool_name: str, args: dict):
        if not self._canvas_tools_executor:
            return ToolResult(False, error="Canvas tools executor not available")

        canvas_tool_map = {
            "canvas_get_variables": lambda: self._canvas_tools_executor.canvas_get_variables(
                var_type=args.get("var_type"),
                include_values=args.get("include_values", True),
            ),
            "canvas_set_variable": lambda: self._canvas_tools_executor.canvas_set_variable(
                var_name=args.get("var_name", ""),
                value=args.get("value"),
                var_type=args.get("var_type", "custom"),
                from_node=args.get("from_node"),
                from_port=args.get("from_port"),
            ),
            "canvas_run_node": lambda: self._canvas_tools_executor.canvas_run_node(
                mode=args.get("mode", "node"), node_name=args.get("node_name")
            ),
            "canvas_get_logs": lambda: self._canvas_tools_executor.canvas_get_logs(
                node_name=args.get("node_name", ""),
                log_type=args.get("log_type", "historical"),
            ),
            # "canvas_edit_run": lambda: self._canvas_tools_executor.canvas_edit_run(
            #     node_name=args.get("node_name", ""), code=args.get("code", "")
            # ),
            "canvas_nodes": lambda: self._canvas_tools_executor.canvas_nodes(),
            "canvas_exec_state": lambda: self._canvas_tools_executor.canvas_exec_state(
                task_id=args.get("task_id"),
                include_nodes=args.get("include_nodes", True),
                include_logs=args.get("include_logs", False),
                log_tail_chars=args.get("log_tail_chars", 2000),
                recent_limit=args.get("recent_limit", 5),
            ),
            "canvas_snapshot": lambda: self._canvas_tools_executor.canvas_snapshot(
                node_names=args.get("node_names"),
                include_logs=args.get("include_logs", True),
                log_type=args.get("log_type", "historical"),
                log_tail_chars=args.get("log_tail_chars", 4000),
                include_code=args.get("include_code", False),
                include_input_data=args.get("include_input_data", False),
                include_output_data=args.get("include_output_data", False),
                data_truncation=args.get("data_truncation", 2000),
            ),
            "canvas_set_prop": lambda: self._canvas_tools_executor.canvas_set_prop(
                node_name=args.get("node_name", ""),
                properties=args.get("properties", {}),
                target=args.get("target"),
            ),
            "canvas_create_node": lambda: self._canvas_tools_executor.canvas_create_node(
                node_name=args.get("node_name"),
                position=args.get("position"),
            ),
            "canvas_connect_nodes": lambda: self._canvas_tools_executor.canvas_connect_nodes(
                connections=args.get("connections", []),
            ),
            "canvas_edit_prop": lambda: self._canvas_tools_executor.canvas_edit_prop(
                node_name=args.get("node_name", ""),
                edits=args.get("edits", []),
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
