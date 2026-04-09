import fnmatch
import re
from typing import Any, Dict, List, Optional
from pathlib import Path
import os

from loguru import logger
from app.widgets.side_dock_area.plugins.llm_chatter.tools.result import ToolResult


class FileTools:
    def __init__(self, workdir: Path):
        self.workdir = workdir

    def _resolve_path(self, path: str) -> Path:
        if not path:
            return self.workdir
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
            logger.warning(f"[FileTools] Failed to resolve path {path}: {e}")
            return self.workdir

    def read_file(self, path: str, offset: int = 1, limit: int = 500) -> ToolResult:
        """
        读取文件，返回带行号的内容，方便 AI 定位
        """
        try:
            full_path = self._resolve_path(path)
            if not full_path.exists():
                return ToolResult(False, error=f"File not found: {path}")

            if full_path.is_dir():
                return self.list_directory(path)

            # 使用 errors='replace' 防止因编码问题直接崩溃
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()

            total_lines = len(all_lines)
            start_idx = max(0, offset - 1)
            end_idx = min(total_lines, start_idx + limit)

            content_slice = all_lines[start_idx:end_idx]
            # 格式化输出：行号 | 内容
            formatted_content = "".join(
                f"{i + start_idx + 1:6d} | {line}" for i, line in enumerate(content_slice)
            )

            res_info = f"File: {path} (Lines {start_idx + 1}-{end_idx} of {total_lines})\n\n"
            return ToolResult(True, content=res_info + formatted_content)
        except Exception as e:
            return ToolResult(False, error=f"Read error: {str(e)}")

    def write_file(self, path: str, content: str) -> ToolResult:
        """
        写入文件，自动创建中间目录
        """
        try:
            full_path = self._resolve_path(path)
            full_path.parent.mkdir(parents=True, exist_ok=True)

            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content if content is not None else "")

            return ToolResult(True, content=f"Successfully written to {path}")
        except Exception as e:
            return ToolResult(False, error=f"Write error: {str(e)}")

    def edit_file(self, path: str, oldString: str, newString: str, replaceAll: bool = False) -> ToolResult:
        """
        精确文本替换。包含唯一性校验，防止 AI 误改多处代码。
        """
        try:
            full_path = self._resolve_path(path)
            if not full_path.exists():
                return ToolResult(False, error=f"File not found: {path}")

            content = full_path.read_text(encoding="utf-8", errors="replace")

            count = content.count(oldString)
            if count == 0:
                return ToolResult(False,
                                  error="The specified 'oldString' was not found in the file. Ensure exact match including whitespace.")

            if count > 1 and not replaceAll:
                return ToolResult(False,
                                  error=f"The 'oldString' appears {count} times. Please provide a more specific code block to ensure uniqueness, or set replaceAll=True.")

            new_content = content.replace(oldString, newString, -1 if replaceAll else 1)
            full_path.write_text(new_content, encoding="utf-8")

            return ToolResult(True, content=f"Successfully edited {path}.")
        except Exception as e:
            return ToolResult(False, error=f"Edit error: {str(e)}")

    def grep_files(self, pattern: str, path: str = ".", include: str = None) -> ToolResult:
        """
        高效搜索，排除干扰目录，限制返回行数
        """
        try:
            search_root = self._resolve_path(path)
            regex = re.compile(pattern, re.IGNORECASE)
            results = []

            # 常见的排除目录，提升性能并减少 Token 浪费
            exclude_dirs = {'.git', 'node_modules', '__pycache__', 'venv', '.venv', 'dist', 'build', '.idea', '.vscode'}

            for root, dirs, files in os.walk(search_root):
                dirs[:] = [d for d in dirs if d not in exclude_dirs]

                for filename in files:
                    if include and not fnmatch.fnmatch(filename, include):
                        continue

                    file_path = Path(root) / filename
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            for i, line in enumerate(f, 1):
                                if regex.search(line):
                                    rel_path = file_path.relative_to(self.workdir)
                                    results.append(f"{rel_path}:{i}: {line.strip()}")
                                    if len(results) >= 100:
                                        return ToolResult(True, content="\n".join(
                                            results) + "\n\n... (Too many matches, please refine your search pattern)")
                    except:
                        continue

            return ToolResult(True, content="\n".join(results) if results else "No matches found.")
        except Exception as e:
            return ToolResult(False, error=f"Grep error: {str(e)}")

    def list_directory(self, path: str = ".") -> ToolResult:
        """
        列出目录，增加 [DIR] 标识
        """
        try:
            target_path = self._resolve_path(path)
            if not target_path.exists():
                return ToolResult(False, error=f"Path not found: {path}")

            entries = []
            for item in sorted(target_path.iterdir()):
                prefix = "[DIR] " if item.is_dir() else "      "
                entries.append(f"{prefix}{item.name}")

            output = f"Contents of {path}:\n" + ("\n".join(entries) if entries else "(Empty directory)")
            return ToolResult(True, content=output)
        except Exception as e:
            return ToolResult(False, error=f"List error: {str(e)}")

    def multi_edit(self, path: str, edits: List[Dict]) -> ToolResult:
        """
        批量编辑同一文件，减少文件 I/O 次数
        """
        try:
            full_path = self._resolve_path(path)
            if not full_path.exists():
                return ToolResult(False, error=f"File not found: {path}")

            content = full_path.read_text(encoding="utf-8", errors="replace")

            applied_count = 0
            for edit in edits:
                old = edit.get("oldString")
                new = edit.get("newString")
                if old in content:
                    content = content.replace(old, new, 1)
                    applied_count += 1
                else:
                    logger.warning(f"Multi-edit: block not found in {path}")

            full_path.write_text(content, encoding="utf-8")
            return ToolResult(True, content=f"Applied {applied_count}/{len(edits)} edits to {path}")
        except Exception as e:
            return ToolResult(False, error=f"Multi-edit error: {str(e)}")

    def glob_files(self, pattern: str, path: str = ".") -> ToolResult:
        """
        通过通配符查找文件
        """
        try:
            search_path = self._resolve_path(path)
            # rglob 进行递归查找
            matches = list(search_path.rglob(pattern))

            if not matches:
                return ToolResult(True, content="No files matched the pattern.")

            # 仅返回文件，并转化为相对工作目录的路径
            results = []
            for m in matches[:100]:  # 限制返回数量
                if m.is_file():
                    try:
                        results.append(str(m.relative_to(self.workdir)))
                    except ValueError:
                        results.append(str(m))

            return ToolResult(True, content="\n".join(results))
        except Exception as e:
            return ToolResult(False, error=f"Glob error: {str(e)}")

    def apply_patch(self, path: str, patch_content: str) -> ToolResult:
        try:
            path = self._resolve_path(path)
            if not path.exists():
                return ToolResult(False, error=f"File not found: {path}")

            with open(path, "r", encoding="utf-8") as f:
                original = f.read()

            patched = original
            patch_lines = patch_content.strip().split("\n")
            in_hunk = False
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
        import subprocess

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