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
import time
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
import fnmatch

from PyQt5.QtCore import QEventLoop, QTimer
from loguru import logger

from app.utils.config import Settings


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
        self._skill_workspaces: Dict[str, str] = {}
        self._sub_agent_manager = None

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

            try:
                results = [str(m.relative_to(search_path)) for m in matches[:100]]
            except ValueError:
                results = [str(m) for m in matches[:100]]
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

    def diff_files(
        self, file1: str, file2: str = None, use_git: bool = False
    ) -> ToolResult:
        """对比两个文件或文件与git版本的差异"""
        try:
            path1 = self._resolve_path(file1)
            if not path1.exists():
                return ToolResult(False, error=f"File not found: {file1}")

            if use_git:
                result = subprocess.run(
                    ["git", "diff", str(path1)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    cwd=str(self.workdir),
                )
                if result.returncode != 0 and "not a git repository" in result.stderr:
                    return ToolResult(False, error="Not a git repository")
                diff_output = result.stdout or result.stderr
                if not diff_output:
                    return ToolResult(
                        True, content=f"No changes in {file1} (compared to git)"
                    )
                return ToolResult(True, content=diff_output)

            if file2:
                path2 = self._resolve_path(file2)
                if not path2.exists():
                    return ToolResult(False, error=f"File not found: {file2}")
                result = subprocess.run(
                    ["diff", "-u", str(path1), str(path2)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                )
            else:
                result = subprocess.run(
                    ["git", "diff", "HEAD", str(path1)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    cwd=str(self.workdir),
                )
                if result.returncode != 0 and "not a git repository" in result.stderr:
                    return ToolResult(
                        False, error="Not a git repository and no second file provided"
                    )
                return ToolResult(
                    True,
                    content=result.stdout
                    if result.stdout
                    else f"No changes in {file1} (compared to git HEAD)",
                )

            if not result.stdout:
                return ToolResult(True, content="Files are identical")
            return ToolResult(True, content=result.stdout)
        except Exception as e:
            return ToolResult(False, error=f"Diff error: {str(e)}")

    def multi_edit(self, filePath: str, edits: List[Dict]) -> ToolResult:
        """一次性执行多个编辑操作"""
        try:
            if not filePath:
                return ToolResult(False, error="Missing required parameter: filePath")
            if not edits:
                return ToolResult(False, error="Missing required parameter: edits")

            path = self._resolve_path(filePath)
            if not path.exists():
                return ToolResult(False, error=f"File not found: {filePath}")

            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            original_content = content
            applied_edits = []
            errors = []

            for idx, edit in enumerate(edits):
                old_string = edit.get("oldString", "")
                new_string = edit.get("newString", "")
                replace_all = edit.get("replaceAll", False)

                if not old_string:
                    errors.append(f"Edit {idx + 1}: missing oldString")
                    continue

                if old_string not in content:
                    errors.append(f"Edit {idx + 1}: string not found")
                    continue

                if replace_all:
                    content = content.replace(old_string, new_string)
                else:
                    content = content.replace(old_string, new_string, 1)
                applied_edits.append(idx + 1)

            if not applied_edits:
                return ToolResult(False, error=f"No edits applied: {'; '.join(errors)}")

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            msg = f"Applied {len(applied_edits)} edits to {path}"
            if errors:
                msg += f"\nWarnings: {'; '.join(errors)}"
            return ToolResult(True, content=msg)
        except Exception as e:
            return ToolResult(False, error=f"Multi-edit error: {str(e)}")

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

    def git_status(self, path: str = None) -> ToolResult:
        """查看 Git 仓库状态"""
        try:
            target = self._resolve_path(path) if path else self.workdir
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                cwd=str(target),
            )
            if result.returncode != 0:
                if "not a git repository" in result.stderr:
                    return ToolResult(False, error="Not a git repository")
                return ToolResult(False, error=result.stderr)
            output = result.stdout.strip()
            if not output:
                return ToolResult(True, content="Working tree clean")
            lines = output.split("\n")
            formatted = []
            for line in lines:
                if line.startswith("M "):
                    formatted.append(f"[修改] {line[3:]}")
                elif line.startswith("A "):
                    formatted.append(f"[新增] {line[3:]}")
                elif line.startswith("D "):
                    formatted.append(f"[删除] {line[3:]}")
                elif line.startswith("? "):
                    formatted.append(f"[未跟踪] {line[2:]}")
                elif line.startswith("!! "):
                    formatted.append(f"[忽略] {line[3:]}")
                else:
                    formatted.append(line)
            return ToolResult(True, content="Git Status:\n" + "\n".join(formatted))
        except Exception as e:
            return ToolResult(False, error=f"Git status error: {str(e)}")

    def git_log(self, path: str = None, max_count: int = 10) -> ToolResult:
        """查看 Git 提交历史"""
        try:
            target = self._resolve_path(path) if path else self.workdir
            result = subprocess.run(
                ["git", "log", f"--max-count={max_count}", "--oneline", "--decorate"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                cwd=str(target),
            )
            if result.returncode != 0:
                if "not a git repository" in result.stderr:
                    return ToolResult(False, error="Not a git repository")
                return ToolResult(False, error=result.stderr)
            output = result.stdout.strip()
            if not output:
                return ToolResult(True, content="No commit history")
            return ToolResult(
                True, content=f"Git Log (last {max_count} commits):\n{output}"
            )
        except Exception as e:
            return ToolResult(False, error=f"Git log error: {str(e)}")

    def git_diff(
        self, ref1: str = None, ref2: str = None, path: str = None
    ) -> ToolResult:
        """对比 Git 提交或分支差异"""
        try:
            target = self._resolve_path(path) if path else self.workdir
            cmd = ["git", "diff", "--no-color"]
            if ref1:
                cmd.append(ref1)
            if ref2:
                cmd.append(ref2)
            elif ref1 and not ref2:
                cmd[2] = f"{ref1}..HEAD"
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                cwd=str(target),
            )
            if result.returncode != 0:
                if "not a git repository" in result.stderr:
                    return ToolResult(False, error="Not a git repository")
                return ToolResult(False, error=result.stderr)
            output = result.stdout.strip()
            if not output:
                return ToolResult(True, content="No differences")
            return ToolResult(True, content=output)
        except Exception as e:
            return ToolResult(False, error=f"Git diff error: {str(e)}")

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
                or Settings.get_instance().SERPAPI_KEY.value
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

    def todo_clear(self) -> None:
        """清空待办事项列表"""
        self._todo_list = []

    def todo_read(self) -> ToolResult:
        """读取当前待办事项列表"""
        try:
            if not self._todo_list:
                return ToolResult(True, content="No todos")

            lines = []
            for i, todo in enumerate(self._todo_list, 1):
                status = todo.get("status", "")
                if status == "completed":
                    status_icon = "✓"
                elif status == "in_progress":
                    status_icon = "▶"
                else:
                    status_icon = "○"
                content = todo.get("content", "")
                priority = todo.get("priority", "medium")
                lines.append(f"{i}. [{priority}] {status_icon} {content}")

            return ToolResult(True, content="\n".join(lines))
        except Exception as e:
            return ToolResult(False, error=f"Todo read error: {str(e)}")

    def task_execute(
        self, agent: str, description: str, context: str = ""
    ) -> ToolResult:
        """分发任务给子智能体"""
        try:
            if not hasattr(self, "_sub_agent_manager") or not self._sub_agent_manager:
                return ToolResult(False, error="子智能体管理器未初始化")

            import uuid

            task_id = str(uuid.uuid4())
            result_container = {"result": None, "error": None}
            executor_ref = {"executor": None}

            logger.info(f"[Task] Starting task {task_id}, agent={agent}")
            success = self._sub_agent_manager.execute_task(
                task_id=task_id,
                agent_name=agent,
                task_description=description,
                parent_context=context or "",
                on_finished=None,
                on_error=None,
                executor_ref=executor_ref,
            )

            if not success:
                return ToolResult(False, error="Failed to start sub-agent task")

            executor = executor_ref.get("executor")
            if not executor:
                return ToolResult(False, error="Failed to get executor")

            logger.info(f"[Task] Waiting for task {task_id} to complete...")
            timeout = 1800
            start_time = time.time()
            while not executor.isFinished():
                if time.time() - start_time > timeout:
                    logger.warning(f"[Task] Wait timeout after {timeout}s")
                    executor.cancel()
                    return ToolResult(False, error="Task execution timeout")
                time.sleep(0.1)

            result = executor._last_result if hasattr(executor, "_last_result") else ""
            logger.info(f"[Task] Task completed, result: {str(result)[:200]}...")

            if hasattr(executor, "_execution_error") and executor._execution_error:
                return ToolResult(False, error=executor._execution_error)

            return ToolResult(True, content=result)

        except Exception as e:
            logger.error(f"[Task] Exception: {e}")
            return ToolResult(False, error=f"Task execution error: {str(e)}")

    def load_skill(self, name: str) -> ToolResult:
        """加载技能文档"""
        try:
            if name in self._loaded_skills:
                existing_content = self._loaded_skills[name]
                workspace = self._skill_workspaces.get(name, "N/A")
                return ToolResult(
                    True,
                    content=f"Skill already loaded: {name}\n\nSkill workspace: {workspace}\n\n{existing_content[:500]}...\n\n(已加载，内容如上)",
                )

            search_paths = [
                Path(__file__).parent.parent / "skills" / name / f"SKILL.md",
                Path("canvas_files") / "skills" / name / f"SKILL.md",
                Path.home() / ".agents" / "skills" / name / f"SKILL.md",
            ]
            found_path = None
            for path in search_paths:
                if path.exists():
                    found_path = path
                    break

            if not found_path:
                return ToolResult(False, error=f"Skill not found: {name}")

            with open(found_path, "r", encoding="utf-8") as f:
                content = f.read()

            self._loaded_skills[name] = content
            self._skill_workspaces[name] = str(found_path.parent.resolve())

            return ToolResult(
                True,
                content=f"Skill loaded: {name}\n\nSkill workspace: {str(found_path.parent.resolve())}\n\n{content}",
            )
        except Exception as e:
            return ToolResult(False, error=f"Load skill error: {str(e)}")

    def list_skills(self) -> ToolResult:
        """列出所有可用技能"""
        try:
            import yaml

            skills_dirs = [
                Path(__file__).parent.parent / "skills",
                Path("canvas_files") / "skills",
                Path.home() / ".agents" / "skills",
            ]
            results = []

            skills_intro = ""
            main_skills_dir = Path(__file__).parent.parent / "skills"
            skills_readme = main_skills_dir / "SKILLS.md"
            if skills_readme.exists():
                content = skills_readme.read_text(encoding="utf-8")
                skills_intro = content + "\n\n"

            for skills_dir in skills_dirs:
                if not skills_dir.exists():
                    continue
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
                            frontmatter = content.split("---", 2)[1]
                            meta = yaml.safe_load(frontmatter)
                            if meta:
                                name = meta.get("name", skill_dir.name)
                                description = meta.get("description", "")
                        except Exception:
                            pass

                    results.append({"name": name, "description": description})

            skills_xml = "<available_skills>\n"
            for skill in results:
                skills_xml += f"  <skill>\n    <name>{skill['name']}</name>\n    <description>{skill['description']}</description>\n  </skill>\n"
            skills_xml += "</available_skills>"
            return ToolResult(True, content=skills_intro + skills_xml)
        except Exception as e:
            return ToolResult(False, error=f"List skills error: {str(e)}")

    def scan_repo(self, path: str = None, max_depth: int = 2) -> ToolResult:
        """扫描仓库结构并返回紧凑摘要。"""
        try:
            target_path = self._resolve_path(path) if path else self.workdir
            if not target_path.exists():
                return ToolResult(False, error=f"Path not found: {target_path}")

            lines = [f"Repository scan: {target_path}"]
            root_depth = len(target_path.parts)

            for root, dirs, files in os.walk(target_path):
                rel_depth = len(Path(root).parts) - root_depth
                if rel_depth > max_depth:
                    dirs[:] = []
                    continue

                dirs[:] = [
                    d
                    for d in dirs
                    if d not in {".git", "__pycache__", "env", "venv", "envs"}
                ]
                rel_root = Path(root).relative_to(target_path)
                display_root = "." if str(rel_root) == "." else str(rel_root)
                lines.append(f"\n[{display_root}]")

                sample_dirs = sorted(dirs)[:8]
                sample_files = sorted(files)[:12]
                if sample_dirs:
                    lines.append("dirs: " + ", ".join(sample_dirs))
                if sample_files:
                    lines.append("files: " + ", ".join(sample_files))

            return ToolResult(True, content="\n".join(lines[:200]))
        except Exception as e:
            return ToolResult(False, error=f"scan_repo error: {str(e)}")

    def stage_files(self, files: List[str]) -> ToolResult:
        """记录当前任务相关文件集合。"""
        try:
            staged = []
            for file_path in files or []:
                if not file_path:
                    continue
                resolved = self._resolve_path(file_path)
                staged.append(str(resolved))
            if not staged:
                return ToolResult(True, content="No files staged")
            return ToolResult(True, content="Staged files:\n" + "\n".join(staged))
        except Exception as e:
            return ToolResult(False, error=f"stage_files error: {str(e)}")

    def run_verify(self, command: str = "", timeout: int = 120) -> ToolResult:
        """运行验证命令，默认尝试项目测试。"""
        try:
            verify_command = (command or "").strip()
            if not verify_command:
                if (self.workdir / "pytest.ini").exists() or list(
                    self.workdir.glob("test_*.py")
                ):
                    verify_command = "pytest -q"
                elif (self.workdir / "main.py").exists():
                    verify_command = "python -m py_compile main.py"
                else:
                    verify_command = "python -m py_compile ."

            result = self.execute_bash(verify_command, timeout=timeout)
            if result.success:
                return ToolResult(
                    True,
                    content=f"[verify] command: {verify_command}\n{result.content}",
                )
            return ToolResult(
                False,
                error=f"[verify] command: {verify_command}\n{result.error}",
            )
        except Exception as e:
            return ToolResult(False, error=f"run_verify error: {str(e)}")

    def summarize_changes(self, text: str, limit: int = 1200) -> ToolResult:
        """压缩工具输出，便于继续回灌上下文。"""
        try:
            raw = (text or "").strip()
            if not raw:
                return ToolResult(True, content="No summary content")
            normalized = re.sub(r"\n{3,}", "\n\n", raw)
            if len(normalized) <= limit:
                return ToolResult(True, content=normalized)
            head = normalized[: limit // 2]
            tail = normalized[-limit // 2 :]
            summary = head.rstrip() + "\n...\n" + tail.lstrip()
            return ToolResult(True, content=summary)
        except Exception as e:
            return ToolResult(False, error=f"summarize_changes error: {str(e)}")

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
        # {
        #     "type": "function",
        #     "function": {
        #         "name": "summarize_changes",
        #         "description": "压缩长工具输出或变更说明，便于继续回灌上下文",
        #         "parameters": {
        #             "type": "object",
        #             "properties": {
        #                 "text": {"type": "string", "description": "需要压缩的文本"},
        #                 "limit": {"type": "integer", "description": "摘要最大长度"},
        #             },
        #             "required": ["text"],
        #         },
        #     },
        # },
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
                "parameters": {
                    "type": "object",
                    "properties": {},
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
