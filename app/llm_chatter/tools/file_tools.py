import fnmatch
import re
import time
from typing import Any, Dict, List, Optional, Callable
from pathlib import Path
import os

from PyQt5.QtCore import QObject, pyqtSignal, QThreadPool, QRunnable
from loguru import logger
from app.llm_chatter.tools.result import ToolResult

MAX_GREP_CONTENT_LENGTH = 15000

class GrepTask(QRunnable):
    """异步 Grep 任务，在子线程中执行"""
    
    class Signals(QObject):
        finished = pyqtSignal(object)  # ToolResult
    
    def __init__(self, pattern: str, path: str, include: str, workdir: Path, cancelled_ref: list):
        super().__init__()
        self.signals = self.Signals()
        self.pattern = pattern
        self.path = path
        self.include = include
        self.workdir = workdir
        self.cancelled_ref = cancelled_ref  # [bool] 引用，可被外部修改
    
    def run(self):
        """在子线程中执行 grep"""
        try:
            result = self._do_grep()
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.finished.emit(ToolResult(False, error=f"Grep error: {str(e)}"))
    
    def _do_grep(self) -> ToolResult:
        """实际的 grep 实现"""
        try:
            if not self.path:
                search_root = self.workdir
            else:
                search_root = self._resolve_path(self.path)
            
            regex = re.compile(self.pattern, re.IGNORECASE)
            results = []
            
            exclude_dirs = {'.mypy_cache', '.git', 'node_modules', '__pycache__', 'venv', '.venv',
                           'dist', 'build', '.idea', '.vscode'}
            
            for root, dirs, files in os.walk(search_root):
                # 定期检查取消标志
                if self.cancelled_ref and self.cancelled_ref[0]:
                    return ToolResult(False, error="搜索已取消")
                
                dirs[:] = [d for d in dirs if d not in exclude_dirs]
                
                for filename in files:
                    if self.cancelled_ref and self.cancelled_ref[0]:
                        return ToolResult(False, error="搜索已取消")
                    
                    if self.include and not fnmatch.fnmatch(filename, self.include):
                        continue
                    
                    file_path = Path(root) / filename
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            for i, line in enumerate(f, 1):
                                if self.cancelled_ref and self.cancelled_ref[0]:
                                    return ToolResult(False, error="搜索已取消")
                                if regex.search(line):
                                    try:
                                        rel_path = file_path.relative_to(self.workdir)
                                    except ValueError:
                                        rel_path = file_path
                                    results.append(f"{rel_path}:{i}: {line.strip()}")
                                    if len(results) >= 100:
                                        return ToolResult(True, content="\n".join(
                                            results) + "\n\n... (Too many matches, please refine your search pattern)")
                    except:
                        continue
            
            content = "\n".join(results) if results else "No matches found."
            if len(content) > MAX_GREP_CONTENT_LENGTH:
                content = content[:MAX_GREP_CONTENT_LENGTH] + f"\n\n... (Content truncated, exceeds {MAX_GREP_CONTENT_LENGTH} characters limit)"
            return ToolResult(True, content=content)
        except Exception as e:
            return ToolResult(False, error=f"Grep error: {str(e)}")
    
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
            logger.warning(f"[GrepTask] Failed to resolve path {path}: {e}")
            return self.workdir


class FileTools:
    def __init__(self, workdir: Path):
        self.workdir = workdir
        self._thread_pool: Optional[QThreadPool] = None
        self._current_grep_task: Optional[GrepTask] = None
        self._grep_cancelled = [False]  # 使用列表引用，可以在子线程中被检查
        # 文件修改时间追踪：{绝对路径: 修改时间戳}
        self._file_mtimes: Dict[str, float] = {}
    
    def _get_thread_pool(self) -> QThreadPool:
        """获取或创建线程池"""
        if self._thread_pool is None:
            self._thread_pool = QThreadPool.globalInstance()
        return self._thread_pool
    
    def cancel(self):
        """取消当前正在执行的操作"""
        self._grep_cancelled[0] = True
    
    def reset_cancelled(self):
        """重置取消标志"""
        self._grep_cancelled[0] = False
    
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

    def _check_file_modified(self, full_path: Path) -> Optional[ToolResult]:
        """
        检查文件是否被外部修改
        如果文件之前被读取过，且当前修改时间与记录不一致，返回警告
        """
        path_key = str(full_path)
        if path_key not in self._file_mtimes:
            # 文件没有被读取过，不检查
            return None

        try:
            current_mtime = full_path.stat().st_mtime
            recorded_mtime = self._file_mtimes[path_key]

            if current_mtime != recorded_mtime:
                return ToolResult(
                    False,
                    error=f"⚠️ 文件已被外部修改: {full_path.name}\n\n"
                          f"该文件在你读取后被其他人/进程修改过。\n"
                          f"你的编辑可能会覆盖他人的更改。\n\n"
                          f"建议: 请先重新读取文件(Read)确认最新内容后再进行编辑。"
                )
        except OSError:
            pass

        return None

    def read_file(self, path: str, offset: int = 1, limit: int = 500, show_line_numbers: bool = False) -> ToolResult:
        """
        读取文件内容

        Args:
            path: 文件路径
            offset: 起始行号（从1开始）
            limit: 最大读取行数
            show_line_numbers: 是否显示行号，默认 False（返回原文）

        读取时记录文件的修改时间，用于后续编辑时检测文件是否被外部修改
        """
        try:
            full_path = self._resolve_path(path)
            if not full_path.exists():
                return ToolResult(False, error=f"File not found: {path}")

            if full_path.is_dir():
                return self.list_directory(path)

            # 记录文件修改时间
            self._file_mtimes[str(full_path)] = full_path.stat().st_mtime

            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()

            total_lines = len(all_lines)
            start_idx = max(0, offset - 1)
            end_idx = min(total_lines, start_idx + limit)

            content_slice = all_lines[start_idx:end_idx]

            if show_line_numbers:
                # 带行号格式（AI 定位用）
                formatted_content = "".join(
                    f"{i + start_idx + 1:6d} | {line}" for i, line in enumerate(content_slice)
                )
                res_info = f"File: {path} (Lines {start_idx + 1}-{end_idx} of {total_lines})\n\n"
                return ToolResult(True, content=res_info + formatted_content)
            else:
                # 返回原文
                return ToolResult(True, content="".join(content_slice))
        except Exception as e:
            return ToolResult(False, error=f"Read error: {str(e)}")

    def write_file(self, path: str, content: str) -> ToolResult:
        """
        写入文件，自动创建中间目录
        写入前检查文件是否被外部修改
        """
        try:
            full_path = self._resolve_path(path)
            
            # 检查文件是否被外部修改
            check_result = self._check_file_modified(full_path)
            if check_result:
                return check_result
            
            full_path.parent.mkdir(parents=True, exist_ok=True)

            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content if content is not None else "")

            # 更新修改时间记录
            self._file_mtimes[str(full_path)] = full_path.stat().st_mtime

            return ToolResult(True, content=f"Successfully written to {path}")
        except Exception as e:
            return ToolResult(False, error=f"Write error: {str(e)}")

    def edit_file(self, path: str, oldString: str, newString: str, replaceAll: bool = False) -> ToolResult:
        """
        精确文本替换。包含唯一性校验，防止 AI 误改多处代码。
        写入前检查文件是否被外部修改
        """
        try:
            full_path = self._resolve_path(path)
            if not full_path.exists():
                return ToolResult(False, error=f"File not found: {path}")

            # 检查文件是否被外部修改
            check_result = self._check_file_modified(full_path)
            if check_result:
                return check_result

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

            # 更新修改时间记录
            self._file_mtimes[str(full_path)] = full_path.stat().st_mtime

            return ToolResult(True, content=f"Successfully edited {path}.")
        except Exception as e:
            return ToolResult(False, error=f"Edit error: {str(e)}")

    def grep_files(self, pattern: str, path: str = ".", include: str = None, 
                   callback: Optional[Callable[[ToolResult], None]] = None) -> Optional[ToolResult]:
        """
        高效搜索，排除干扰目录，限制返回行数
        
        如果提供 callback，则异步执行并返回 None
        否则同步执行并返回 ToolResult
        
        Args:
            pattern: 正则表达式模式
            path: 搜索路径，默认当前目录
            include: 文件名过滤模式
            callback: 异步完成后的回调函数
        
        Returns:
            同步执行时返回 ToolResult，异步执行时返回 None
        """
        # 每次调用前重置取消标志
        self._grep_cancelled[0] = False
        
        if callback is not None:
            # 异步执行
            self._run_grep_async(pattern, path, include, callback)
            return None
        else:
            # 同步执行（保持向后兼容）
            return self._run_grep_sync(pattern, path, include)
    
    def _run_grep_sync(self, pattern: str, path: str, include: str) -> ToolResult:
        """同步执行 grep"""
        try:
            search_root = self._resolve_path(path)
            regex = re.compile(pattern, re.IGNORECASE)
            results = []

            exclude_dirs = {'.mypy_cache', '.git', 'node_modules', '__pycache__', 'venv', '.venv',
                           'dist', 'build', '.idea', '.vscode'}

            for root, dirs, files in os.walk(search_root):
                dirs[:] = [d for d in dirs if d not in exclude_dirs]

                for filename in files:
                    if self._grep_cancelled[0]:
                        return ToolResult(False, error="搜索已取消")
                    
                    if include and not fnmatch.fnmatch(filename, include):
                        continue

                    file_path = Path(root) / filename
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            for i, line in enumerate(f, 1):
                                if self._grep_cancelled[0]:
                                    return ToolResult(False, error="搜索已取消")
                                if regex.search(line):
                                    try:
                                        rel_path = file_path.relative_to(self.workdir)
                                    except ValueError:
                                        rel_path = file_path
                                    results.append(f"{rel_path}:{i}: {line.strip()}")
                                    if len(results) >= 100:
                                        return ToolResult(True, content="\n".join(
                                            results) + "\n\n... (Too many matches, please refine your search pattern)")
                    except:
                        continue

            content = "\n".join(results) if results else "No matches found."
            if len(content) > MAX_GREP_CONTENT_LENGTH:
                content = content[:MAX_GREP_CONTENT_LENGTH] + f"\n\n... (Content truncated, exceeds {MAX_GREP_CONTENT_LENGTH} characters limit)"
            return ToolResult(True, content=content)
        except Exception as e:
            return ToolResult(False, error=f"Grep error: {str(e)}")
    
    def _run_grep_async(self, pattern: str, path: str, include: str, 
                        callback: Callable[[ToolResult], None]):
        """异步执行 grep"""
        task = GrepTask(pattern, path, include, self.workdir, self._grep_cancelled)
        self._current_grep_task = task
        
        def on_finished(result: ToolResult):
            self._current_grep_task = None
            callback(result)
        
        task.signals.finished.connect(on_finished)
        self._get_thread_pool().start(task)
        logger.info(f"[FileTools] Started async grep task, pattern={pattern}")

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
            matches = list(search_path.rglob(pattern))

            if not matches:
                return ToolResult(True, content="No files matched the pattern.")

            results = []
            for m in matches[:100]:
                if m.is_file():
                    try:
                        results.append(str(m.relative_to(self.workdir)))
                    except ValueError:
                        results.append(str(m))

            return ToolResult(True, content="\n".join(results))
        except Exception as e:
            return ToolResult(False, error=f"Glob error: {str(e)}")

    def apply_patch(self, path: str, patch_content: str) -> ToolResult:
        """
        应用 unified diff 格式的 patch 到指定文件。

        修正说明（原实现有多个 bug）：
        - context 匹配未考虑 '+' 行不占用文件行位置，导致 context 偏移错误
        - 先删后插的索引计算未处理删除导致的偏移
        - 重写为顺序逐行处理，与标准 patch 语义一致
        """
        try:
            full_path = self._resolve_path(path)
            if not full_path.exists():
                return ToolResult(False, error=f"File not found: {path}")

            check_result = self._check_file_modified(full_path)
            if check_result:
                return check_result

            with open(full_path, "r", encoding="utf-8") as f:
                original_lines = f.read().splitlines()

            processed_content = patch_content.strip()
            real_newlines = processed_content.count('\n')
            escaped_newlines = processed_content.count('\\n')
            if escaped_newlines > real_newlines:
                processed_content = processed_content.replace('\\n', '\n')

            patch_lines = processed_content.split('\n')
            hunks = self._parse_unified_diff(patch_lines)

            if not hunks:
                return ToolResult(False, error="No valid hunk found in patch")

            # 从后往前处理 hunk，避免索引偏移
            result = list(original_lines)
            for hunk in reversed(hunks):
                content = hunk['content']
                old_start = hunk['old_start']  # 1-based

                # ---------------------- 验证阶段 ----------------------
                # 逐行校验：context 行和 delete 行必须匹配文件内容
                # '+' 行不消耗文件行，所以 file_pos 只对 context/delete 递增
                file_pos = old_start - 1  # 转为 0-based
                for typ, text in content:
                    if typ in (' ', '-'):
                        if file_pos >= len(result):
                            return ToolResult(False,
                                error=f"❌ Patch context mismatch at line {file_pos + 1} (hunk @@ -{old_start},... @@):\n"
                                      f"  Patch expects: {repr(text)}\n"
                                      f"  File has:      <EOF>\n"
                                      f"  → The patch goes beyond the end of file.\n"
                                      f"  → Check if @@ -{old_start} line number is too large. "
                                      f"The file has {len(result)} line(s) in total.")
                        if result[file_pos] != text:
                            # 获取周围上下文帮助定位问题
                            prev_line = repr(result[file_pos - 1]) if file_pos > 0 else '<start>'
                            next_line = repr(result[file_pos + 1]) if file_pos + 1 < len(result) else '<EOF>'
                            return ToolResult(False,
                                error=f"❌ Patch context mismatch at line {file_pos + 1} (hunk @@ -{old_start},... @@):\n"
                                      f"  Patch expects:  {repr(text)}\n"
                                      f"  File has:       {repr(result[file_pos])}\n"
                                      f"  File line {file_pos}:     {prev_line}\n"
                                      f"  File line {file_pos + 2}: {next_line}\n"
                                      f"\n"
                                      f"Possible causes:\n"
                                      f"  1. @@ line number is wrong — the first context line '{content[0][1] if content else ''}' "
                                      f"actually starts at a different position\n"
                                      f"  2. Patch content doesn't exactly match the file (check indentation/spaces)\n"
                                      f"  3. The file has been modified since it was last read")
                        file_pos += 1
                    # '+' 行不消耗文件行，跳过

                # ---------------------- 应用阶段 ----------------------
                # 重新定位到 hunk 起始位置
                file_pos = old_start - 1
                replace_start = old_start - 1
                replace_end = file_pos  # 会被下面的遍历更新

                # 构建替换内容
                replacement = []
                for typ, text in content:
                    if typ == ' ':
                        # context 行：保留原文件行
                        replacement.append(result[file_pos])
                        file_pos += 1
                    elif typ == '-':
                        # delete 行：跳过原文件行，不加入替换结果
                        file_pos += 1
                    elif typ == '+':
                        # add 行：加入替换结果，不推进文件指针
                        replacement.append(text)
                replace_end = file_pos  # 更新结束位置

                # 执行替换
                result[replace_start:replace_end] = replacement

            with open(full_path, "w", encoding="utf-8") as f:
                f.write("\n".join(result) + "\n")

            self._file_mtimes[str(full_path)] = full_path.stat().st_mtime

            return ToolResult(True, content=f"Patch applied: {path}")
        except Exception as e:
            return ToolResult(False, error=f"Patch error: {str(e)}")

    def _parse_unified_diff(self, patch_lines: list) -> list:
        """
        解析 unified diff 格式，返回 hunks 列表

        每个 hunk 包含:
        - old_start: 旧文件起始行号（1-based）
        - old_count: 旧文件受影响行数（0 表示未知）
        - new_count: 新文件受影响行数（0 表示未知）
        - content: [(typ, text), ...] 其中 typ=' '/'-'/ '+'
        """
        hunks = []
        i = 0

        # 跳过头部
        while i < len(patch_lines) and not patch_lines[i].startswith("@@"):
            i += 1

        while i < len(patch_lines):
            line = patch_lines[i]
            if not line.startswith("@@"):
                i += 1
                continue

            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if not m:
                i += 1
                continue

            old_start = int(m.group(1))
            old_count = int(m.group(2)) if m.group(2) else 1  # 默认 1
            new_count = int(m.group(4)) if m.group(4) else 1  # 默认 1
            hunk_content = []

            i += 1
            while i < len(patch_lines):
                pl = patch_lines[i]
                if pl.startswith("@@") or (not pl and not pl.startswith((' ', '+', '-'))):
                    break

                if pl.startswith("+") and not pl.startswith("+++"):
                    hunk_content.append(('+', pl[1:]))
                elif pl.startswith("-") and not pl.startswith("---"):
                    hunk_content.append(('-', pl[1:]))
                elif pl.startswith(" "):
                    hunk_content.append((' ', pl[1:]))
                elif pl:
                    break
                i += 1

            if hunk_content:
                hunks.append({
                    'old_start': old_start,
                    'old_count': old_count,
                    'new_count': new_count,
                    'content': hunk_content
                })

        return hunks

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
