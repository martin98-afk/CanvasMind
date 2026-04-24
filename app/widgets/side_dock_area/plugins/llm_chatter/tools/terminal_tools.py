import subprocess
import os
from pathlib import Path
from typing import Optional, Callable

from PyQt5.QtCore import QObject, pyqtSignal, QThreadPool, QRunnable
from loguru import logger
from app.widgets.side_dock_area.plugins.llm_chatter.tools.result import ToolResult


class BashTask(QRunnable):
    """异步 Bash 任务，在子线程中执行"""
    
    class Signals(QObject):
        finished = pyqtSignal(object)  # ToolResult
    
    def __init__(self, command: str, timeout: int, workdir: Path, cancelled_ref: list):
        super().__init__()
        self.signals = self.Signals()
        self.command = command
        self.timeout = timeout
        self.workdir = workdir
        self.cancelled_ref = cancelled_ref  # [bool] 引用，可被外部修改
    
    def run(self):
        """在子线程中执行 bash"""
        try:
            result = self._do_bash()
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.finished.emit(ToolResult(False, error=f"Bash error: {str(e)}"))
    
    def _do_bash(self) -> ToolResult:
        """实际的 bash 执行实现"""
        try:
            res = subprocess.run(
                self.command,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=self.timeout,
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


class TerminalTools:
    def __init__(self, workdir: Path):
        self.workdir = workdir
        self._thread_pool: Optional[QThreadPool] = None
        self._current_bash_task: Optional[BashTask] = None
        self._bash_cancelled = [False]

    def execute_bash(self, command: str, timeout: int = 120,
                    callback: Callable[[ToolResult], None] = None,
                    cancelled_ref: list = None) -> Optional[ToolResult]:
        """
        执行 bash 命令
        
        如果提供 callback，则异步执行并返回 None
        否则同步执行并返回 ToolResult
        """
        if callback is not None:
            self._run_bash_async(command, timeout, callback, cancelled_ref)
            return None
        else:
            return self._execute_bash_sync(command, timeout)
    
    def _run_bash_async(self, command: str, timeout: int,
                        callback: Callable[[ToolResult], None],
                        cancelled_ref: list = None):
        """异步执行 bash"""
        task = BashTask(command, timeout, self.workdir, cancelled_ref or [False])
        self._current_bash_task = task
        
        def on_finished(result: ToolResult):
            self._current_bash_task = None
            callback(result)
        
        task.signals.finished.connect(on_finished)
        self._get_thread_pool().start(task)
        logger.info(f"[TerminalTools] Started async bash task, command={command[:50]}...")
    
    def cancel_bash(self):
        """尝试取消当前正在执行的 bash 命令"""
        if self._current_bash_task:
            logger.info("[TerminalTools] Cancelling bash task")
            # 注意：subprocess 无法直接杀死子进程，这里只是设置标志
            self._bash_cancelled[0] = True
    
    def _get_thread_pool(self) -> QThreadPool:
        """获取或创建线程池"""
        if self._thread_pool is None:
            self._thread_pool = QThreadPool.globalInstance()
        return self._thread_pool
    
    def _execute_bash_sync(self, command: str, timeout: int) -> ToolResult:
        """同步执行 bash（向后兼容）"""
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
