from pathlib import Path
from typing import Dict, List

from PyQt5.QtCore import QObject, pyqtSignal
from loguru import logger

from app.llm_chatter.tools.diagnostics_tools import (
    DiagnosticsTools,
)
from app.llm_chatter.tools.file_tools import FileTools
from app.llm_chatter.tools.result import ToolResult
from app.llm_chatter.tools.task_tools import TaskTools
from app.llm_chatter.tools.terminal_tools import (
    TerminalTools,
)
from app.llm_chatter.tools.web_tools import WebTools


class BuiltinTools(QObject):
    """内置工具集，整合所有工具模块"""

    fileModified = pyqtSignal(str)

    def __init__(self, homepage=None, workdir: str = None):
        super().__init__(homepage)
        self.homepage = homepage

        if workdir:
            self.workdir = Path(workdir)
        else:
            try:
                from app.utils.utils import resource_path

                self.workdir = Path(resource_path("./"))
            except Exception:
                self.workdir = Path.cwd()

        self._file_tools = FileTools(self.workdir)
        self._web_tools = WebTools(self.workdir)
        self._terminal_tools = TerminalTools(self.workdir)
        self._task_tools = TaskTools(self.workdir)
        self._diagnostics_tools = DiagnosticsTools(self.workdir)

        self._todo_list = []
        self._loaded_skills = {}
        self._skill_workspaces = {}
        self._sub_agent_manager = None
        self._set_stage_callback = None
        self._memory_manager = None
        self._get_llm_config = None
        self._get_session_messages = None

        logger.info(f"[BuiltinTools] Workdir: {self.workdir}")

    @property
    def file_tools(self):
        return self._file_tools

    @property
    def web_tools(self):
        return self._web_tools

    @property
    def terminal_tools(self):
        return self._terminal_tools

    @property
    def task_tools(self):
        return self._task_tools

    @property
    def todo_list(self):
        return self._task_tools._todo_list

    @property
    def canvas_tools(self):
        return self._canvas_tools

    @property
    def diagnostics_tools(self):
        return self._diagnostics_tools

    def read_file(self, path: str, offset: int = 1, limit: int = 2000, show_line_numbers: bool = False):
        return self._file_tools.read_file(path, offset, limit, show_line_numbers)

    def write_file(self, path: str, content: str):
        result = self._file_tools.write_file(path, content)
        if result.success:
            resolved_path = self._file_tools._resolve_path(path)
            logger.info(
                f"[BuiltinTools] write_file success, emitting fileModified: {resolved_path}"
            )
            self.fileModified.emit(str(resolved_path))
        return result

    def edit_file(
        self, path: str, oldString: str, newString: str, replaceAll: bool = False
    ):
        result = self._file_tools.edit_file(path, oldString, newString, replaceAll)
        if result.success:
            resolved_path = self._file_tools._resolve_path(path)
            logger.info(
                f"[BuiltinTools] edit_file success, emitting fileModified: {resolved_path}"
            )
            self.fileModified.emit(str(resolved_path))
        return result

    def grep_files(self, pattern: str, path: str = None, include: str = None):
        return self._file_tools.grep_files(pattern, path, include)

    def glob_files(self, pattern: str, path: str = None):
        return self._file_tools.glob_files(pattern, path)

    def list_directory(self, path: str = None):
        return self._file_tools.list_directory(path)

    def apply_patch(self, path: str, patch_content: str):
        result = self._file_tools.apply_patch(path, patch_content)
        if result.success:
            resolved_path = self._file_tools._resolve_path(path)
            logger.info(
                f"[BuiltinTools] apply_patch success, emitting fileModified: {resolved_path}"
            )
            self.fileModified.emit(str(resolved_path))
        return result

    def diff_files(self, file1: str, file2: str = None, use_git: bool = False):
        return self._file_tools.diff_files(file1, file2, use_git)

    def multi_edit(self, path: str, edits: List[Dict]):
        result = self._file_tools.multi_edit(path, edits)
        if result.success:
            resolved_path = self._file_tools._resolve_path(path)
            logger.info(
                f"[BuiltinTools] multi_edit success, emitting fileModified: {resolved_path}"
            )
            self.fileModified.emit(str(resolved_path))
        return result

    def execute_bash(self, command: str, timeout: int = 120,):
        return self._terminal_tools.execute_bash(command, timeout)

    def run_verify(self, command: str = "", timeout: int = 120):
        return self._terminal_tools.run_verify(command, timeout)

    def fetch_web(self, url: str, format: str = "markdown", max_chars: int = 26000, callback=None, cancelled_ref: list = None):
        return self._web_tools.fetch_web(url, format, max_chars, callback, cancelled_ref)

    def search_web(self, query: str, num_results: int = 10, callback=None, cancelled_ref: list = None):
        return self._web_tools.search_web(query, num_results, callback, cancelled_ref)

    def todo_write(self, todos: List[Dict]):
        result = self._task_tools.todo_write(todos)
        self._todo_list = list(self._task_tools._todo_list)
        return result

    def todo_clear(self):
        self._task_tools.todo_clear()
        self._todo_list = []

    def reset_session_state(self):
        """Reset session-scoped state when switching sessions"""
        self._todo_list = []
        self._task_tools.reset_session_state()

    def todo_read(self):
        return self._task_tools.todo_read()

    def task_execute(self, agent: str, description: str, context: str = ""):
        return self._task_tools.task_execute(agent, description, context)

    def load_skill(self, name: str):
        return self._task_tools.load_skill(name)

    def list_skills(self):
        return self._task_tools.list_skills()

    def scan_repo(self, path: str = None, max_depth: int = 2):
        return self._task_tools.scan_repo(path, max_depth)

    def stage_files(self, files: List[str]):
        return self._task_tools.stage_files(files)

    def ask_question(
        self, question: str, options: List[str] = None, multiple: bool = False
    ):
        return self._task_tools.ask_question(question, options, multiple)

    def get_diagnostics(self, file_path: str, language: str = None):
        return self._diagnostics_tools.get_diagnostics(file_path, language)

    def summarize_changes(self, text: str = "", limit: int = 1200) -> ToolResult:
        text = (text or "").strip()
        if not text:
            return ToolResult(False, error="No text provided for summarization")

        clean_lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if clean_lines and clean_lines[-1] == stripped:
                continue
            clean_lines.append(stripped)

        summary = "\n".join(clean_lines)
        if len(summary) > limit:
            head = summary[: int(limit * 0.75)].rstrip()
            tail = summary[-int(limit * 0.15) :].lstrip()
            summary = f"{head}\n\n[... 已省略 {len(summary) - len(head) - len(tail)} 个字符 ...]\n\n{tail}"
        return ToolResult(True, content=summary)

    def set_memory_manager(self, memory_manager):
        self._memory_manager = memory_manager

    def set_llm_config_getter(self, getter):
        self._get_llm_config = getter

    def set_session_messages_getter(self, getter):
        self._get_session_messages = getter

    def memory_list(
        self,
        limit: int = 10,
        include_disabled: bool = False,
    ) -> ToolResult:
        if not self._memory_manager:
            return ToolResult(False, error="Memory manager not available")

        memories = self._memory_manager.get_user_memories()
        if not include_disabled:
            memories = [item for item in memories if item.get("enabled", True)]
        memories = memories[: max(1, int(limit or 10))]
        return ToolResult(
            True,
            content={
                "count": len(memories),
                "memories": memories,
                "formatted": self._memory_manager.format_memories_for_prompt(
                    memories,
                    title="长期记忆列表",
                    include_disabled=include_disabled,
                ),
            },
        )

    def memory_search(
        self,
        query: str = "",
        limit: int = 8,
        include_disabled: bool = False,
    ) -> ToolResult:
        if not self._memory_manager:
            return ToolResult(False, error="Memory manager not available")

        query = str(query or "").strip()
        memories = self._memory_manager.search_memories(
            query,
            include_disabled=include_disabled,
            limit=max(1, int(limit or 8)),
        )
        return ToolResult(
            True,
            content={
                "query": query,
                "count": len(memories),
                "memories": memories,
                "formatted": self._memory_manager.format_memories_for_prompt(
                    memories,
                    title=f"长期记忆搜索结果: {query or '全部'}",
                    include_disabled=include_disabled,
                ),
            },
        )

    def memory_save(
        self,
        content: str,
        confidence: float = 0.8,
        source: str = "assistant",
        conflict_group: str = "",
    ) -> ToolResult:
        if not self._memory_manager:
            return ToolResult(False, error="Memory manager not available")

        content = str(content or "").strip()
        if not content:
            return ToolResult(False, error="Memory content is empty")

        success = self._memory_manager.add_user_memory(
            content,
            source=source or "assistant",
            confidence=float(confidence or 0.8),
            conflict_group=str(conflict_group or ""),
        )
        if not success:
            return ToolResult(False, error="Failed to save memory")

        return ToolResult(
            True,
            content={
                "saved": True,
                "content": content,
                "source": source or "assistant",
                "confidence": float(confidence or 0.8),
                "conflict_group": str(conflict_group or ""),
            },
        )

    def memory_consolidate(
        self,
        max_items: int = 3,
        save: bool = True,
    ) -> ToolResult:
        if not self._memory_manager:
            return ToolResult(False, error="Memory manager not available")
        if not callable(self._get_llm_config):
            return ToolResult(False, error="LLM config getter not available")
        if not callable(self._get_session_messages):
            return ToolResult(False, error="Session messages getter not available")

        llm_config = self._get_llm_config() or {}
        messages = self._get_session_messages() or []
        if not messages:
            return ToolResult(False, error="No session messages available")

        max_items = max(1, int(max_items or 3))
        consolidated = self._memory_manager.consolidate_from_messages(
            messages,
            llm_config,
            max_items=max_items,
        )
        if not consolidated:
            return ToolResult(
                True,
                content={
                    "saved": False,
                    "count": 0,
                    "memories": [],
                    "formatted": "未提炼出适合写入长期记忆的新内容。",
                },
            )

        saved_count = 0
        if save:
            for item in consolidated:
                if self._memory_manager.add_user_memory(
                    item.get("content", ""),
                    source=item.get("source", "session"),
                    confidence=float(item.get("confidence", 0.8) or 0.8),
                    conflict_group=str(item.get("conflict_group", "") or ""),
                    category=str(item.get("category", "task_preference") or "task_preference"),
                ):
                    saved_count += 1

        formatted = self._memory_manager.format_memories_for_prompt(
            consolidated,
            title="本轮提炼出的长期记忆",
            include_disabled=False,
        )
        return ToolResult(
            True,
            content={
                "saved": bool(save),
                "saved_count": saved_count,
                "count": len(consolidated),
                "memories": consolidated,
                "formatted": formatted,
                "provider_linked": bool(
                    llm_config.get("API_URL") or llm_config.get("模型名称")
                ),
            },
        )


def create_builtin_tools(homepage=None, workdir: str = None) -> BuiltinTools:
    """创建内置工具实例"""
    return BuiltinTools(homepage, workdir)


def get_builtin_tools_schema() -> List[Dict]:
    """获取内置工具的 schema 定义（用于给 LLM 调用）"""
    return [
        {
            "type": "function",
            "function": {
                "name": "read",
                "description": "读取文件内容。可选带行号输出方便定位编辑。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件相对路径"},
                        "offset": {
                            "type": "integer",
                            "description": "起始行号 (从1开始)",
                            "default": 1,
                        },
                        "limit": {
                            "type": "integer",
                            "description": "读取的行数",
                            "default": 500,
                        },
                        "show_line_numbers": {
                            "type": "boolean",
                            "description": "是否显示行号，用于定位编辑",
                            "default": False,
                        },
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write",
                "description": "创建新文件或覆盖现有文件。会自动创建不存在的目录。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件相对路径"},
                        "content": {"type": "string", "description": "完整的文件内容"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "edit",
                "description": "通过精确字符串替换编辑文件。为防止误改，oldString 必须在文件中唯一。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件路径"},
                        "oldString": {
                            "type": "string",
                            "description": "要被替换的原始精确文本块",
                        },
                        "newString": {
                            "type": "string",
                            "description": "替换后的新文本块",
                        },
                        "replaceAll": {
                            "type": "boolean",
                            "description": "如果存在多个匹配项，是否全部替换",
                            "default": False,
                        },
                    },
                    "required": ["path", "oldString", "newString"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "grep",
                "description": "在指定目录下递归搜索匹配正则表达式的内容。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "正则表达式"},
                        "path": {
                            "type": "string",
                            "description": "起始搜索目录 (默认当前目录)",
                            "default": ".",
                        },
                        "include": {
                            "type": "string",
                            "description": "文件过滤模式 (如 '*.py')",
                        },
                    },
                    "required": ["pattern"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list",
                "description": "列出目录下的文件和文件夹。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "目录路径",
                            "default": ".",
                        }
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "glob",
                "description": "通过通配符模式递归查找文件，支持 **, *, ? 等glob语法。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "文件匹配模式 (如 '*.py', '**/*.json', 'src/**/*.ts')"
                        },
                        "path": {
                            "type": "string",
                            "description": "搜索起始路径 (默认当前目录)",
                            "default": ".",
                        },
                    },
                    "required": ["pattern"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "multiedit",
                "description": "在同一个文件中执行多处替换操作。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件路径"},
                        "edits": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "oldString": {
                                        "type": "string",
                                        "description": "旧文本",
                                    },
                                    "newString": {
                                        "type": "string",
                                        "description": "新文本",
                                    },
                                },
                                "required": ["oldString", "newString"],
                            },
                        },
                    },
                    "required": ["path", "edits"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "patch",
                "description": "通过 unified diff 格式对文件进行精确修改。支持追加行、删除行、替换行、在指定位置插入行等多处修改。适用于需要同时修改文件多个位置的场景。输入标准的 unified diff 格式（包含 @@ -start +start @@ 行号标记）。**推荐优先使用 patch**，比 write/edit 更安全可靠。\n\n使用规范：\n1. 修改前先用 read 确认文件当前行号和内容\n2. @@ 行号必须是文件中实际的行号（1-based），注意 context/delete 行数之和是旧文件行数\n3. context 行（以空格开头）是匹配锚点，必须与文件完全一致（缩进、空行、空格/制表符）\n4. 只保留必要的 context 行（上下各 1-2 行）减少出错\n\n常见失败原因：\n- @@ 行号不对：检查 hunk 第一行 context 在文件中的实际行号\n- 空行数量不匹配：文件有几个空行，patch 里也要有几个\n- 缩进/空格不一致：空格和制表符不能混用\n\n失败后修复：读取报错中提示的行号附近内容，对比 patch 与文件的差异，修正后重试",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件路径"},
                        "patch_content": {
                            "type": "string",
                            "description": "Unified diff 格式补丁内容。格式：\n--- filename\n+++ filename\n@@ -起始行,行数 +起始行,行数 @@\n[空格]上下文行（不变）\n[-]要删除的行\n[+]要添加的新行"
                        },
                    },
                    "required": ["path", "patch_content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "bash",
                "description": "执行shell命令",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "命令"},
                        "timeout": {"type": "integer", "description": "超时秒数"},
                    },
                    "required": ["command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_verify",
                "description": "运行针对当前任务的验证命令，默认尝试项目测试或语法检查",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "验证命令"},
                        "timeout": {"type": "integer", "description": "超时时间"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_diagnostics",
                "description": "获取文件的语法检查结果（错误、警告、提示）。支持 Python (pyright/mypy/flake8)、JavaScript/TypeScript (tsc/eslint)、Shell (shellcheck)。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径"},
                        "language": {
                            "type": "string",
                            "description": "语言类型，可选: python, javascript, typescript, shellscript",
                        },
                    },
                    "required": ["file_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "webfetch",
                "description": "获取网页内容",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "网页URL"},
                        "format": {
                            "type": "string",
                            "description": "返回格式, 支持:html, text, markdown",
                        },
                    },
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "websearch",
                "description": "网络搜索",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"},
                        "num_results": {"type": "integer", "description": "结果数量"},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "scan_repo",
                "description": "扫描仓库目录并返回结构化摘要，适合编码任务前快速建模上下文",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "扫描路径"},
                        "max_depth": {"type": "integer", "description": "最大扫描深度"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "stage_files",
                "description": "标记当前任务相关文件，帮助后续聚焦编辑和验证",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "files": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "文件路径列表",
                        },
                    },
                    "required": ["files"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "memory_list",
                "description": "列出当前工作区的长期记忆，可选择是否包含已禁用/冲突记忆",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "最多返回多少条记忆",
                        },
                        "include_disabled": {
                            "type": "boolean",
                            "description": "是否包含已禁用的冲突记忆",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "memory_search",
                "description": "检索和当前任务相关的长期记忆，适合在编码或追问前主动查用户偏好、项目约束和长期决策",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "检索关键词"},
                        "limit": {
                            "type": "integer",
                            "description": "最多返回多少条记忆",
                        },
                        "include_disabled": {
                            "type": "boolean",
                            "description": "是否包含已禁用的冲突记忆",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "memory_save",
                "description": "保存一条可能需要跨会话记忆的关键事实进入长期记忆",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "记忆内容"},
                        "confidence": {
                            "type": "number",
                            "description": "置信度，0 到 1",
                        },
                        "source": {"type": "string", "description": "记忆来源"},
                        "conflict_group": {
                            "type": "string",
                            "description": "冲突组，相同组的新记忆会压制旧记忆",
                        },
                    },
                    "required": ["content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "todowrite",
                "description": "创建和更新待办事项列表",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "todos": {"type": "array", "description": "待办列表"},
                    },
                    "required": ["todos"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "todoread",
                "description": "读取待办事项列表",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "task",
                "description": "分发任务给子智能体执行。子智能体有独立上下文，不继承主智能体的超长上下文。适用于复杂任务分解、并行处理、隔离上下文等场景。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent": {
                            "type": "string",
                            "description": "子智能体名称",
                            "enum": ["build", "plan", "skillful", "explore"],
                        },
                        "description": {
                            "type": "string",
                            "description": "任务描述，详细说明需要子智能体完成的工作",
                        },
                        "context": {
                            "type": "string",
                            "description": "传递给子智能体的上下文信息（可选）",
                        },
                    },
                    "required": ["agent", "description"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "skill",
                "description": "加载技能文档",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "技能名称"},
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_skills",
                "description": "列出所有可用技能",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "question",
                "description": "向用户提问并获取回答。当你需要了解用户偏好、需求或让用户做选择时，**必须**使用此工具，不要自行生成问卷或选项。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "问题内容及描述，尽量简洁，不要包含选项内容"},
                        "options": {"type": "array", "description": "选项列表"},
                        "multiple": {
                            "type": "boolean",
                            "description": "是否允许多选，默认false",
                        },
                    },
                    "required": ["question"],
                },
            },
        },
    ]
