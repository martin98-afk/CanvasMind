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

    def read_file(
        self, filePath: str, offset: int = 1, limit: int = 2000
    ) -> ToolResult:
        logger.info(
            f"[FileTools.read_file] filePath={filePath}, offset={offset}, limit={limit}"
        )
        try:
            if not filePath:
                return ToolResult(False, error="Missing required parameter: filePath")

            path = self._resolve_path(filePath)
            logger.info(f"[FileTools.read_file] resolved path: {path}")
            if not path.exists():
                logger.warning(f"[FileTools.read_file] File not found: {filePath}")
                return ToolResult(False, error=f"File not found: {filePath}")

            if path.is_dir():
                logger.info(
                    f"[FileTools.read_file] Path is a directory, listing contents: {filePath}"
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
        try:
            if not pattern:
                return ToolResult(False, error="Missing required parameter: pattern")

            import re
            import fnmatch
            import os as _os

            search_path = self._resolve_path(path) if path else self.workdir
            if not search_path.exists():
                return ToolResult(
                    False, error=f"Path not found: {path or self.workdir}"
                )

            results = []
            regex = re.compile(pattern)

            for root, dirs, files in _os.walk(search_path):
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
        try:
            path = self._resolve_path(filePath)
            if not path.exists():
                return ToolResult(False, error=f"File not found: {filePath}")

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

    def multi_edit(self, filePath: str, edits: List[Dict]) -> ToolResult:
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
