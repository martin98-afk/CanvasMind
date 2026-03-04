# -*- coding: utf-8 -*-
"""
内置工具模块
实现类似 opencode 的工具执行能力
"""

import json
import re
import os
import subprocess
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
import fnmatch

from loguru import logger


class ToolResult:
    def __init__(self, success: bool, content: Any = None, error: str = None):
        self.success = success
        self.content = content
        self.error = error

    def to_dict(self) -> dict:
        if self.success:
            return {"success": True, "content": self.content}
        return {"success": False, "error": self.error}

    def __str__(self):
        if self.success:
            return str(self.content)
        return f"[Error] {self.error}"


class BuiltinTools:
    """内置工具集"""

    def __init__(self, homepage=None, workdir: str = None):
        self.homepage = homepage

        # 使用 resource_path 获取正确的基准路径（支持打包后的环境）
        if workdir:
            self.workdir = Path(workdir)
        else:
            # 尝试使用 resource_path 获取 app 目录
            try:
                from app.utils.utils import resource_path

                self.workdir = Path(resource_path("./"))
            except Exception:
                self.workdir = Path.cwd()

        self._todo_list: List[Dict] = []
        self._loaded_skills: Dict[str, str] = {}

        logger.info(f"[BuiltinTools] Workdir: {self.workdir}")

    def read_file(
        self, filePath: str, offset: int = 1, limit: int = 2000
    ) -> ToolResult:
        """读取文件内容"""
        logger.info(
            f"[BuiltinTools.read_file] filePath={filePath}, offset={offset}, limit={limit}"
        )
        try:
            if not filePath:
                return ToolResult(False, error="Missing required parameter: filePath")

            path = self._resolve_path(filePath)
            logger.info(f"[BuiltinTools.read_file] resolved path: {path}")
            if not path.exists():
                logger.warning(f"[BuiltinTools.read_file] File not found: {filePath}")
                return ToolResult(False, error=f"File not found: {filePath}")

            if path.is_dir():
                logger.info(
                    f"[BuiltinTools.read_file] Path is a directory, listing contents: {filePath}"
                )
                entries = []
                for item in sorted(path.iterdir()):
                    rel_path = item.relative_to(path)
                    entries.append(str(rel_path))
                if not entries:
                    return ToolResult(True, content="Empty directory")
                return ToolResult(
                    True, content="Directory contents:\n" + "\n".join(entries)
                )

            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            total_lines = len(lines)
            start = max(0, offset - 1)
            end = min(total_lines, start + limit)
            content = "".join(lines[start:end])

            result = (
                f"File: {path}\nLines {start + 1}-{end} of {total_lines}:\n\n{content}"
            )
            return ToolResult(True, content=result)
        except PermissionError:
            return ToolResult(
                False,
                error=f"Permission denied: {filePath}. The path may be a directory or access is restricted.",
            )
        except Exception as e:
            return ToolResult(False, error=f"Read error: {str(e)}")

    def write_file(self, filePath: str, content: str) -> ToolResult:
        """创建或覆盖文件"""
        try:
            if not filePath:
                return ToolResult(False, error="Missing required parameter: filePath")
            if content is None:
                content = ""

            path = self._resolve_path(filePath)
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            return ToolResult(True, content=f"File written: {path}")
        except Exception as e:
            return ToolResult(False, error=f"Write error: {str(e)}")

    def edit_file(
        self, filePath: str, oldString: str, newString: str, replaceAll: bool = False
    ) -> ToolResult:
        """通过精确字符串替换编辑文件"""
        try:
            if not filePath:
                return ToolResult(False, error="Missing required parameter: filePath")
            if oldString is None:
                oldString = ""
            if newString is None:
                newString = ""

            path = self._resolve_path(filePath)
            if not path.exists():
                return ToolResult(False, error=f"File not found: {filePath}")

            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            if replaceAll:
                if oldString not in content:
                    return ToolResult(False, error="String not found in file")
                new_content = content.replace(oldString, newString)
            else:
                if oldString not in content:
                    return ToolResult(False, error="String not found in file")
                new_content = content.replace(oldString, newString, 1)

            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return ToolResult(True, content=f"File edited: {path}")
        except Exception as e:
            return ToolResult(False, error=f"Edit error: {str(e)}")

    def grep_files(
        self, pattern: str, path: str = None, include: str = None
    ) -> ToolResult:
        """使用正则表达式搜索文件内容"""
        try:
            if not pattern:
                return ToolResult(False, error="Missing required parameter: pattern")

            search_path = self._resolve_path(path) if path else self.workdir
            if not search_path.exists():
                return ToolResult(
                    False, error=f"Path not found: {path or self.workdir}"
                )

            results = []
            regex = re.compile(pattern)

            for root, dirs, files in os.walk(search_path):
                if ".git" in root or "__pycache__" in root:
                    continue

                for filename in files:
                    if include and not fnmatch.fnmatch(filename, include):
                        continue
                    filepath = Path(root) / filename
                    try:
                        with open(
                            filepath, "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            for line_num, line in enumerate(f, 1):
                                if regex.search(line):
                                    rel_path = filepath.relative_to(self.workdir)
                                    results.append(
                                        f"{rel_path}:{line_num}: {line.rstrip()}"
                                    )
                    except Exception:
                        continue

            if not results:
                return ToolResult(True, content="No matches found")

            output = "\n".join(results[:500])
            return ToolResult(True, content=output)
        except Exception as e:
            return ToolResult(False, error=f"Grep error: {str(e)}")

    def glob_files(self, pattern: str, path: str = None) -> ToolResult:
        """通过模式匹配查找文件"""
        try:
            if not pattern:
                return ToolResult(False, error="Missing required parameter: pattern")

            search_path = self._resolve_path(path) if path else self.workdir
            if not search_path.exists():
                return ToolResult(
                    False, error=f"Path not found: {path or self.workdir}"
                )

            matches = list(search_path.glob(pattern))
            matches = [m for m in matches if m.is_file()]

            if not matches:
                return ToolResult(True, content="No matches found")

            results = [str(m.relative_to(self.workdir)) for m in matches[:100]]
            return ToolResult(True, content="\n".join(results))
        except TypeError as e:
            return ToolResult(
                False, error=f"Glob error: {str(e)}. Pattern may be invalid."
            )
        except Exception as e:
            return ToolResult(False, error=f"Glob error: {str(e)}")

    def list_directory(self, path: str = None) -> ToolResult:
        """列出目录内容"""
        try:
            target_path = self._resolve_path(path) if path else self.workdir
            if not target_path.exists():
                return ToolResult(
                    False, error=f"Path not found: {path or self.workdir}"
                )

            entries = []
            for item in sorted(target_path.iterdir()):
                rel_path = item.relative_to(target_path)
                entries.append(str(rel_path))

            if not entries:
                return ToolResult(True, content="Empty directory")

            return ToolResult(True, content="\n".join(entries))
        except Exception as e:
            return ToolResult(False, error=f"List error: {str(e)}")

    def apply_patch(self, filePath: str, patch_content: str) -> ToolResult:
        """对文件应用补丁"""
        try:
            path = self._resolve_path(filePath)
            if not path.exists():
                return ToolResult(False, error=f"File not found: {filePath}")

            with open(path, "r", encoding="utf-8") as f:
                original = f.read()

            patched = original
            patch_lines = patch_content.strip().split("\n")
            in_hunk = False
            hunk_start = 0
            hunk_lines = []

            for line in patch_lines:
                if line.startswith("@@"):
                    in_hunk = True
                    continue
                if in_hunk and line.startswith(("+", "-", " ")):
                    hunk_lines.append(line)

            if hunk_lines:
                for hunk_line in hunk_lines:
                    if hunk_line.startswith("+") and not hunk_line.startswith("+++"):
                        patched += hunk_line[1:] + "\n"
                    elif hunk_line.startswith("-") and not hunk_line.startswith("---"):
                        old_line = hunk_line[1:]
                        if old_line in patched:
                            patched = patched.replace(old_line, "", 1)

            with open(path, "w", encoding="utf-8") as f:
                f.write(patched)

            return ToolResult(True, content=f"Patch applied: {path}")
        except Exception as e:
            return ToolResult(False, error=f"Patch error: {str(e)}")

    def execute_bash(self, command: str, timeout: int = 120) -> ToolResult:
        """执行 shell 命令"""
        try:
            system = os.name
            if system == "nt":
                res = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    timeout=timeout,
                    cwd=str(self.workdir),
                )
            else:
                res = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    timeout=timeout,
                    cwd=str(self.workdir),
                )

            output = res.stdout.strip() if res.stdout else ""
            error_out = res.stderr.strip() if res.stderr else ""
            combined = "\n".join(filter(None, [output, error_out]))
            return ToolResult(
                True,
                content=combined if combined else "(command completed with no output)",
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, error="Command execution timeout")
        except Exception as e:
            return ToolResult(False, error=f"Execution error: {str(e)}")

    def fetch_web(self, url: str, format: str = "markdown") -> ToolResult:
        """获取网页内容"""
        try:
            import requests

            response = requests.get(url, timeout=30)
            response.raise_for_status()

            if format == "text":
                return ToolResult(True, content=response.text[:50000])
            elif format == "html":
                return ToolResult(True, content=response.text[:50000])
            else:
                text = response.text
                text = re.sub(
                    r"<script[^>]*>.*?</script>",
                    "",
                    text,
                    flags=re.DOTALL | re.IGNORECASE,
                )
                text = re.sub(
                    r"<style[^>]*>.*?</style>",
                    "",
                    text,
                    flags=re.DOTALL | re.IGNORECASE,
                )
                text = re.sub(r"<[^>]+>", "", text)
                text = re.sub(r"\s+", " ", text)
                return ToolResult(True, content=text[:50000])
        except ImportError:
            return ToolResult(False, error="requests library not installed")
        except Exception as e:
            return ToolResult(False, error=f"Fetch error: {str(e)}")

    def search_web(self, query: str, num_results: int = 10) -> ToolResult:
        """网络搜索"""
        try:
            import requests
            import os

            api_key = (
                os.environ.get("SERPAPI_KEY")
                or "42e2b2817bf48352d3caa227212ebb82d6f8839cdd39b304c68cf58b42961c27"
            )

            if api_key == "your-serpapi-key-here" or not api_key:
                return ToolResult(
                    False,
                    error="Please set SERPAPI_KEY environment variable or configure in settings",
                )

            proxies = None
            http_proxy = (
                os.environ.get("HTTP_PROXY")
                or os.environ.get("http_proxy")
                or os.environ.get("HTTPS_PROXY")
                or os.environ.get("https_proxy")
            )
            if http_proxy:
                proxies = {
                    "http": http_proxy,
                    "https": http_proxy,
                }

            params = {
                "engine": "duckduckgo",
                "q": query,
                "kl": "us-en",
                "api_key": api_key,
            }

            response = requests.get(
                "https://serpapi.com/search",
                params=params,
                proxies=proxies,
                timeout=30,
            )

            if response.status_code == 401:
                return ToolResult(False, error="Invalid SerpAPI key")
            if response.status_code == 403:
                return ToolResult(False, error="SerpAPI quota exceeded")

            response.raise_for_status()

            data = response.json()

            results = []
            organic = data.get("organic_results", [])

            for item in organic[:num_results]:
                title = item.get("title", "")
                link = item.get("link", "")
                snippet = item.get("snippet", "")

                if title and link:
                    results.append(f"- {title}\n  {link}\n  {snippet}")

            if not results:
                return ToolResult(True, content="No results found")

            return ToolResult(True, content="\n\n".join(results))

        except ImportError:
            return ToolResult(False, error="requests library not installed")
        except requests.exceptions.Timeout:
            return ToolResult(False, error="Search timeout, please try again")
        except requests.exceptions.RequestException as e:
            return ToolResult(False, error=f"Search request failed: {str(e)}")
        except Exception as e:
            return ToolResult(False, error=f"Search error: {str(e)}")

    def todo_write(self, todos: List[Dict]) -> ToolResult:
        """创建和更新待办事项列表"""
        try:
            self._todo_list = todos
            return ToolResult(True, content=f"Todo list updated: {len(todos)} items")
        except Exception as e:
            return ToolResult(False, error=f"Todo write error: {str(e)}")

    def todo_read(self) -> ToolResult:
        """读取当前待办事项列表"""
        try:
            if not self._todo_list:
                return ToolResult(True, content="No todos")

            lines = []
            for i, todo in enumerate(self._todo_list, 1):
                status = "✓" if todo.get("status") == "completed" else "○"
                content = todo.get("content", "")
                priority = todo.get("priority", "medium")
                lines.append(f"{i}. [{priority}] {status} {content}")

            return ToolResult(True, content="\n".join(lines))
        except Exception as e:
            return ToolResult(False, error=f"Todo read error: {str(e)}")

    def load_skill(self, name: str) -> ToolResult:
        """加载技能文档"""
        try:
            search_paths = [
                Path(__file__).parent.parent / "skills" /  name /  f"SKILL.md"
            ]
            for path in search_paths:
                if path.exists():
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                    self._loaded_skills[name] = content
                    return ToolResult(
                        True, content=f"Skill loaded: {name}\n\nSkill workspace: {str(path.parent)}\n\n{content}"
                    )

            return ToolResult(False, error=f"Skill not found: {name}")
        except Exception as e:
            return ToolResult(False, error=f"Load skill error: {str(e)}")

    def list_skills(self, query: str = "") -> ToolResult:
        """列出或搜索可用技能"""
        try:
            import yaml

            skills_dir = Path(__file__).parent.parent / "skills"
            results = []

            for skill_dir in skills_dir.iterdir():
                if not skill_dir.is_dir():
                    continue
                if skill_dir.name.startswith("_") or skill_dir.name.startswith("."):
                    continue

                skill_file = skill_dir / "SKILL.md"
                if not skill_file.exists():
                    skill_file = skill_dir / "skill.md"

                if not skill_file.exists():
                    continue

                content = skill_file.read_text(encoding="utf-8")
                name = skill_dir.name
                description = ""

                if content.startswith("---"):
                    try:
                        # 直接取 --- 之间的内容，不需要再分割
                        frontmatter = content.split("---", 2)[1]
                        meta = yaml.safe_load(frontmatter)
                        if meta:
                            name = meta.get("name", skill_dir.name)
                            description = meta.get("description", "")
                    except Exception:
                        pass

                if query:
                    query_lower = query.lower()
                    if (
                        query_lower not in name.lower()
                        and query_lower not in description.lower()
                    ):
                        continue

                results.append({"name": name, "description": description})

            return ToolResult(
                True, content=json.dumps(results, ensure_ascii=False, indent=2)
            )
        except Exception as e:
            return ToolResult(False, error=f"List skills error: {str(e)}")

    def ask_question(
        self, question: str, options: List[str] = None, multiple: bool = False
    ) -> ToolResult:
        """向用户提问（返回问题定义，由UI处理实际提问）"""
        return ToolResult(
            True,
            content={
                "question": question,
                "options": options or [],
                "multiple": multiple,
                "type": "question",
            },
        )

    def _resolve_path(self, path: str) -> Path:
        """解析路径为绝对路径"""
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
            return self.workdir


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
                "description": "列出或搜索可用技能。当用户询问你能做什么，或者询问是否有某个功能的技能时，使用此工具查询。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词（可选），不提供关键词返回所有技能列表。",
                        },
                    },
                },
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
    ]


def create_builtin_tools(homepage=None, workdir: str = None) -> BuiltinTools:
    """创建内置工具实例"""
    return BuiltinTools(homepage, workdir)
