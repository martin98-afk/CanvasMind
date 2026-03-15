import subprocess
from pathlib import Path
from typing import Optional

from loguru import logger
from app.widgets.side_dock_area.plugins.llm_chatter.tools.result import ToolResult


class GitTools:
    def __init__(self, workdir: Path):
        self.workdir = workdir

    def _resolve_path(self, path: Optional[str]) -> Path:
        if not path:
            return self.workdir
        p = Path(path)
        if p.is_absolute():
            return p.resolve()
        return (self.workdir / p).resolve()

    def git_status(self, path: Optional[str] = None) -> ToolResult:
        try:
            target = self._resolve_path(path)
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

    def git_log(self, path: Optional[str] = None, max_count: int = 10) -> ToolResult:
        try:
            target = self._resolve_path(path)
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
        self,
        ref1: Optional[str] = None,
        ref2: Optional[str] = None,
        path: Optional[str] = None,
    ) -> ToolResult:
        try:
            target = self._resolve_path(path)
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
