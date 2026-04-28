import subprocess
from pathlib import Path

from app.llm_chatter.tools.result import ToolResult


class TerminalTools:
    def __init__(self, workdir: Path):
        self.workdir = workdir

    def execute_bash(self, command: str, timeout: int = 120) -> ToolResult:
        try:
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

    def run_verify(self, command: str = "", timeout: int = 120) -> ToolResult:
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
                False, error=f"[verify] command: {verify_command}\n{result.error}"
            )
        except Exception as e:
            return ToolResult(False, error=f"run_verify error: {str(e)}")
