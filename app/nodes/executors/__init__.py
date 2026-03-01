# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from app.nodes.executors.base import BaseExecutor
from app.nodes.executors.subprocess_executor import SubprocessExecutor
from app.nodes.executors.ipython_executor import IPythonExecutor
from app.nodes.executors.ssh_executor import SSHExecutor


@dataclass
class ExecutionContext:
    """节点执行上下文 - 封装执行所需的所有信息"""

    node: Any
    comp_obj: Any
    params: Dict[str, Any] = field(default_factory=dict)
    inputs: Dict[str, Any] = field(default_factory=dict)
    global_variable: Dict[str, Any] = field(default_factory=dict)

    run_id: str = ""
    run_dir: Optional[Path] = None
    cache_path: Optional[Path] = None

    log_file_path: str = ""
    result_path: Optional[Path] = None
    error_path: Optional[Path] = None
    params_path: Optional[Path] = None

    last_log_pos: int = 0
    timeout_enabled: bool = False
    timeout_seconds: int = 60

    zmq_env_vars: Dict[str, str] = field(default_factory=dict)
    remote_ip: Optional[str] = None
    remote_root: Optional[str] = None

    kernel_manager: Any = None
    check_cancel: Any = None

    env_data: Dict[str, Any] = field(default_factory=dict)
    component_code: str = ""
    class_name: str = ""
    python_executable: str = ""

    def __post_init__(self):
        if not self.run_id:
            self.run_id = f"run_{self.node.persistent_id}"
        if not self.cache_path:
            self.cache_path = getattr(self.node, "CACHE_PATH", Path.cwd())
        if self.run_dir is None and self.cache_path:
            self.run_dir = self.cache_path / "run_scripts" / self.run_id


class ExecutorRegistry:
    """执行器注册表 - 管理所有可用的执行器"""

    _instance = None

    def __init__(self):
        self._executors: Dict[str, BaseExecutor] = {}
        self._register_default_executors()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _register_default_executors(self):
        self.register("subprocess", SubprocessExecutor())
        self.register("ipython", IPythonExecutor())
        self.register("ssh", SSHExecutor())

    def register(self, name: str, executor: BaseExecutor) -> None:
        self._executors[name] = executor

    def get(self, name: str) -> Optional[BaseExecutor]:
        return self._executors.get(name)

    def get_all(self) -> Dict[str, BaseExecutor]:
        return self._executors.copy()

    def select_executor(self, ctx: ExecutionContext) -> Optional[BaseExecutor]:
        """根据上下文选择合适的执行器"""
        if ctx.env_data.get("type") == "ssh":
            return self.get("ssh")

        exec_mode = getattr(ctx.node.view, "current_mode", None)
        has_object_io = getattr(ctx.node, "object_io", False)

        # exec_mode = "ipython" → IPython 执行器（启用驻留）
        # exec_mode = "subprocess" 且有 object_io → IPython 执行器（不驻留）
        # exec_mode = "subprocess" 且无 object_io → Subprocess 执行器
        if exec_mode == "ipython" or (exec_mode == "subprocess" and has_object_io):
            return self.get("ipython")

        return self.get("subprocess")


__all__ = [
    "BaseExecutor",
    "SubprocessExecutor",
    "IPythonExecutor",
    "SSHExecutor",
    "ExecutorRegistry",
    "ExecutionContext",
]
