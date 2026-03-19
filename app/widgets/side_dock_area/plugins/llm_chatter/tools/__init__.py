from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from app.widgets.side_dock_area.plugins.llm_chatter.tools.result import ToolResult
from app.widgets.side_dock_area.plugins.llm_chatter.tools.file_tools import FileTools
from app.widgets.side_dock_area.plugins.llm_chatter.tools.git_tools import GitTools
from app.widgets.side_dock_area.plugins.llm_chatter.tools.web_tools import WebTools
from app.widgets.side_dock_area.plugins.llm_chatter.tools.terminal_tools import (
    TerminalTools,
)
from app.widgets.side_dock_area.plugins.llm_chatter.tools.task_tools import TaskTools
from app.widgets.side_dock_area.plugins.llm_chatter.tools.canvas_tools import (
    CanvasTools,
)


class BuiltinTools:
    """内置工具集，整合所有工具模块"""

    def __init__(self, homepage=None, workdir: str = None):
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
        self._git_tools = GitTools(self.workdir)
        self._web_tools = WebTools(self.workdir)
        self._terminal_tools = TerminalTools(self.workdir)
        self._task_tools = TaskTools(self.workdir)
        self._canvas_tools = CanvasTools(self.workdir)

        self._todo_list = []
        self._loaded_skills = {}
        self._skill_workspaces = {}
        self._sub_agent_manager = None
        self._set_stage_callback = None

        logger.info(f"[BuiltinTools] Workdir: {self.workdir}")

    @property
    def file_tools(self):
        return self._file_tools

    @property
    def git_tools(self):
        return self._git_tools

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

    def read_file(self, filePath: str, offset: int = 1, limit: int = 2000):
        return self._file_tools.read_file(filePath, offset, limit)

    def write_file(self, filePath: str, content: str):
        return self._file_tools.write_file(filePath, content)

    def edit_file(
        self, filePath: str, oldString: str, newString: str, replaceAll: bool = False
    ):
        return self._file_tools.edit_file(filePath, oldString, newString, replaceAll)

    def grep_files(self, pattern: str, path: str = None, include: str = None):
        return self._file_tools.grep_files(pattern, path, include)

    def glob_files(self, pattern: str, path: str = None):
        return self._file_tools.glob_files(pattern, path)

    def list_directory(self, path: str = None):
        return self._file_tools.list_directory(path)

    def apply_patch(self, filePath: str, patch_content: str):
        return self._file_tools.apply_patch(filePath, patch_content)

    def diff_files(self, file1: str, file2: str = None, use_git: bool = False):
        return self._file_tools.diff_files(file1, file2, use_git)

    def multi_edit(self, filePath: str, edits: List[Dict]):
        return self._file_tools.multi_edit(filePath, edits)

    def execute_bash(self, command: str, timeout: int = 120):
        return self._terminal_tools.execute_bash(command, timeout)

    def run_verify(self, command: str = "", timeout: int = 120):
        return self._terminal_tools.run_verify(command, timeout)

    def git_status(self, path: str = None):
        return self._git_tools.git_status(path)

    def git_log(self, path: str = None, max_count: int = 10):
        return self._git_tools.git_log(path, max_count)

    def git_diff(self, ref1: str = None, ref2: str = None, path: str = None):
        return self._git_tools.git_diff(ref1, ref2, path)

    def fetch_web(self, url: str, format: str = "markdown"):
        return self._web_tools.fetch_web(url, format)

    def search_web(self, query: str, num_results: int = 10):
        return self._web_tools.search_web(query, num_results)

    def todo_write(self, todos: List[Dict]):
        result = self._task_tools.todo_write(todos)
        self._todo_list = list(self._task_tools._todo_list)
        return result

    def todo_clear(self):
        self._task_tools.todo_clear()
        self._todo_list = []

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

    def switch_stage(self, stage: str):
        return self._task_tools.switch_stage(stage)

    def ask_question(
        self, question: str, options: List[str] = None, multiple: bool = False
    ):
        return self._task_tools.ask_question(question, options, multiple)

    def list_canvases(self):
        return self._canvas_tools.list_canvases()

    def trigger_canvas(
        self,
        endpoint: str,
        data: dict = None,
        callback_url: str = None,
        timeout: int = 300,
    ):
        return self._canvas_tools.trigger_canvas(endpoint, data, callback_url, timeout)

    def summarize_changes(self) -> ToolResult:
        return ToolResult(True, content="Summarize functionality - to be implemented")

    def _resolve_path(self, path: str):
        if not path:
            return self.workdir
        import os

        try:
            expanded = os.path.expandvars(path)
            if expanded != path:
                path = expanded
            p = Path(path)
            if p.is_absolute():
                return p.resolve()
            else:
                return (self.workdir / p).resolve()
        except (ValueError, OSError, RuntimeError) as e:
            logger.warning(f"[BuiltinTools] Failed to resolve path {path}: {e}")
            return self.workdir


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
                "description": "读取文件内容，支持指定行范围",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filePath": {"type": "string", "description": "文件路径"},
                        "offset": {"type": "integer", "description": "起始行号"},
                        "limit": {"type": "integer", "description": "最大行数"},
                    },
                    "required": ["filePath"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write",
                "description": "创建新文件或覆盖现有文件",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filePath": {"type": "string", "description": "文件路径"},
                        "content": {"type": "string", "description": "文件内容"},
                    },
                    "required": ["filePath", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "edit",
                "description": "通过精确字符串替换来编辑文件",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filePath": {"type": "string", "description": "文件路径"},
                        "oldString": {"type": "string", "description": "要替换的文本"},
                        "newString": {"type": "string", "description": "替换后的文本"},
                        "replaceAll": {
                            "type": "boolean",
                            "description": "是否替换所有",
                        },
                    },
                    "required": ["filePath", "oldString", "newString"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "grep",
                "description": "使用正则表达式搜索文件内容",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "正则表达式"},
                        "path": {"type": "string", "description": "搜索路径"},
                        "include": {"type": "string", "description": "文件过滤"},
                    },
                    "required": ["pattern"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "glob",
                "description": "通过glob模式查找文件",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "glob模式"},
                        "path": {"type": "string", "description": "搜索路径"},
                    },
                    "required": ["pattern"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list",
                "description": "列出目录内容",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "目录路径"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "multiedit",
                "description": "一次性执行多个编辑操作，适用于批量修改",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filePath": {"type": "string", "description": "文件路径"},
                        "edits": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "oldString": {
                                        "type": "string",
                                        "description": "要替换的文本",
                                    },
                                    "newString": {
                                        "type": "string",
                                        "description": "替换后的文本",
                                    },
                                    "replaceAll": {
                                        "type": "boolean",
                                        "description": "是否替换所有",
                                    },
                                },
                                "required": ["oldString", "newString"],
                            },
                            "description": "编辑操作列表",
                        },
                    },
                    "required": ["filePath", "edits"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "patch",
                "description": "对文件应用补丁",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filePath": {"type": "string", "description": "文件路径"},
                        "patch_content": {"type": "string", "description": "补丁内容"},
                    },
                    "required": ["filePath", "patch_content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "diff",
                "description": "对比两个文件或文件与git版本的差异",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file1": {"type": "string", "description": "第一个文件路径"},
                        "file2": {
                            "type": "string",
                            "description": "第二个文件路径（可选）",
                        },
                        "use_git": {
                            "type": "boolean",
                            "description": "是否与git版本对比",
                        },
                    },
                    "required": ["file1"],
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
                "name": "webfetch",
                "description": "获取网页内容",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "网页URL"},
                        "format": {"type": "string", "description": "返回格式"},
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
                "name": "switch_stage",
                "description": "切换当前任务的阶段(stage)。可选阶段: discover(探索) -> plan(计划) -> edit(编辑) -> verify(验证) -> review(审查) -> summarize(总结)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "stage": {
                            "type": "string",
                            "description": "目标阶段名称",
                            "enum": [
                                "discover",
                                "plan",
                                "edit",
                                "verify",
                                "review",
                                "summarize",
                            ],
                        },
                    },
                    "required": ["stage"],
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
                        "question": {"type": "string", "description": "问题内容"},
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
        {
            "type": "function",
            "function": {
                "name": "list_canvases",
                "description": "列出所有在线可以执行的画布及其 webhook 触发器信息",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "trigger_canvas",
                "description": "通过 webhook 触发画布运行并等待结果返回",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "endpoint": {
                            "type": "string",
                            "description": "Webhook 端点（从 list_canvases 获取）",
                        },
                        "data": {
                            "type": "object",
                            "description": "传递给画布的数据（可选）",
                        },
                        "callback_url": {
                            "type": "string",
                            "description": "结果回调地址（可选）",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "等待结果超时时间，默认300秒",
                        },
                    },
                    "required": ["endpoint"],
                },
            },
        },
    ]
