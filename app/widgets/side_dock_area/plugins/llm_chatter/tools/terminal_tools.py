import subprocess
import os
import signal
from pathlib import Path
from typing import Optional, Callable

from PyQt5.QtCore import QObject, pyqtSignal, QThreadPool, QRunnable
from loguru import logger
from app.widgets.side_dock_area.plugins.llm_chatter.tools.result import ToolResult


class BashProcessManager:
    """管理正在运行的 Bash 进程，支持真正中止"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = BashProcessManager()
        return cls._instance
    
    def __init__(self):
        self._running_processes: dict = {}  # task_id -> Popen process
    
    def register(self, task_id: str, process: subprocess.Popen):
        self._running_processes[task_id] = process
        logger.debug(f"[BashProcessManager] Registered process: {task_id}")
    
    def unregister(self, task_id: str):
        if task_id in self._running_processes:
            del self._running_processes[task_id]
            logger.debug(f"[BashProcessManager] Unregistered process: {task_id}")
    
    def terminate(self, task_id: str, force: bool = False) -> bool:
        """尝试终止指定任务对应的进程"""
        if task_id not in self._running_processes:
            return False
        
        process = self._running_processes[task_id]
        if process.poll() is not None:
            # 进程已结束，自动清理
            self.unregister(task_id)
            return True
        
        try:
            if force:
                # 强制杀死进程树
                logger.warning(f"[BashProcessManager] Force killing process: {task_id}")
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
            else:
                # 优雅终止
                logger.info(f"[BashProcessManager] Terminating process: {task_id}")
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
            return True
        except Exception as e:
            logger.error(f"[BashProcessManager] Failed to terminate {task_id}: {e}")
            return False
    
    def terminate_all(self, force: bool = False):
        """终止所有正在运行的进程"""
        task_ids = list(self._running_processes.keys())
        for task_id in task_ids:
            self.terminate(task_id, force=force)
        logger.info(f"[BashProcessManager] Terminated {len(task_ids)} processes")
    
    def cleanup_finished(self):
        """清理已结束的进程记录"""
        finished = [
            tid for tid, proc in self._running_processes.items()
            if proc.poll() is not None
        ]
        for tid in finished:
            self.unregister(tid)


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
        self._process: Optional[subprocess.Popen] = None
        self._task_id = id(self)
    
    def run(self):
        """在子线程中执行 bash"""
        try:
            result = self._do_bash()
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.finished.emit(ToolResult(False, error=f"Bash error: {str(e)}"))
        finally:
            BashProcessManager.get_instance().unregister(str(self._task_id))
    
    def _do_bash(self) -> ToolResult:
        """实际的 bash 执行实现，使用 Popen 支持真正中止"""
        try:
            # 检查是否已被取消
            if self.cancelled_ref and self.cancelled_ref[0]:
                return ToolResult(False, error="用户中止")
            
            # 创建进程，使用 start_new_session=True 在 Unix 上创建新进程组
            # 这样可以方便地杀死整个进程树
            self._process = subprocess.Popen(
                self.command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="ignore",
                cwd=str(self.workdir),
                preexec_fn=os.setsid if os.name != 'nt' else None,
            )
            
            # 注册到进程管理器
            BashProcessManager.get_instance().register(str(self._task_id), self._process)
            
            # 分段读取输出，避免在等待时无法响应取消
            stdout_data = []
            stderr_data = []
            read_size = 1024
            
            while True:
                # 检查取消标志（轮询方式）
                if self.cancelled_ref and self.cancelled_ref[0]:
                    self._terminate_process()
                    return ToolResult(False, error="用户中止")
                
                # 使用 poll 检查进程是否结束
                poll_result = self._process.poll()
                if poll_result is not None:
                    # 进程已结束，读取剩余输出
                    stdout_remaining, stderr_remaining = self._process.communicate()
                    if stdout_remaining:
                        stdout_data.append(stdout_remaining)
                    if stderr_remaining:
                        stderr_data.append(stderr_remaining)
                    break
                
                # 尝试读取当前已有的输出（不阻塞）
                try:
                    import select
                    # 非阻塞读取 - 在 Windows 上使用不同方法
                    if os.name == 'nt':
                        import msvcrt
                        if msvcrt.kbhit():
                            char = msvcrt.getch()
                            # Windows 处理
                    else:
                        # Unix 系统使用 select
                        ready, _, _ = select.select([self._process.stdout, self._process.stderr], [], [], 0.1)
                        for fd in ready:
                            if fd == self._process.stdout:
                                chunk = self._process.stdout.read(read_size)
                                if chunk:
                                    stdout_data.append(chunk)
                            elif fd == self._process.stderr:
                                chunk = self._process.stderr.read(read_size)
                                if chunk:
                                    stderr_data.append(chunk)
                except (ImportError, AttributeError):
                    # select 不可用，使用 time.sleep 轮询
                    import time
                    time.sleep(0.1)
                
                # 检查超时
                # 超时由外部 timeout 参数处理，这里不做额外处理
            
            # 获取最终结果
            stdout = "".join(stdout_data)
            stderr = "".join(stderr_data)
            
            output = stdout.strip() if stdout else ""
            error_out = stderr.strip() if stderr else ""
            combined = "\n".join(filter(None, [output, error_out]))
            
            return ToolResult(
                True,
                content=combined if combined else "(command completed with no output)",
            )
        except subprocess.TimeoutExpired:
            self._terminate_process()
            return ToolResult(False, error="Command execution timeout")
        except Exception as e:
            self._terminate_process()
            return ToolResult(False, error=f"Execution error: {str(e)}")
    
    def _terminate_process(self):
        """终止当前进程及其子进程"""
        if self._process is None:
            return
        
        try:
            # 在 Unix 上杀死整个进程组
            if os.name != 'nt':
                try:
                    os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
            else:
                # Windows 终止进程树
                try:
                    self._process.terminate()
                except ProcessLookupError:
                    pass
        except Exception as e:
            logger.debug(f"[BashTask] Failed to terminate process: {e}")
        
        # 确保进程被清理
        try:
            self._process.kill()
        except:
            pass


class TerminalTools:
    def __init__(self, workdir: Path):
        self.workdir = workdir
        self._thread_pool: Optional[QThreadPool] = None
        self._current_bash_task: Optional[BashTask] = None
        self._bash_cancelled = [False]
        self._process_manager = BashProcessManager.get_instance()

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
        logger.info("[TerminalTools] Cancelling bash task")
        
        # 标记取消标志
        self._bash_cancelled[0] = True
        
        # 如果有正在运行的任务，尝试终止其进程
        if self._current_bash_task:
            task_id = str(self._current_bash_task._task_id)
            self._process_manager.terminate(task_id, force=True)
        
        # 终止所有正在运行的 bash 进程
        self._process_manager.terminate_all(force=True)
    
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
