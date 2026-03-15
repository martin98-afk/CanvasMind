# -*- coding: utf-8 -*-
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

from app.nodes.executors.base import BaseExecutor
from app.templates.node_execute_script import _EXECUTION_SCRIPT_TEMPLATE
from app.utils.utils import kill_proc_tree, resource_path


class SubprocessExecutor(BaseExecutor):
    """子进程执行器"""

    def can_execute(self, ctx) -> bool:
        return ctx.env_data.get("type") != "ssh"

    def prepare_environment(self, ctx) -> None:
        super().prepare_environment(ctx)
        shutil.copyfile(
            resource_path("app/components/base.py"), str(ctx.run_dir.parent / "base.py")
        )

        extension_dir = Path(resource_path("app/component_extensions")) / getattr(
            ctx.node, "uuid", ""
        )
        if extension_dir.exists():
            workspace_dir = ctx.cache_path / "workspace" / ctx.node.persistent_id
            shutil.copytree(extension_dir, workspace_dir, dirs_exist_ok=True)

    def execute(self, ctx) -> dict:
        if ctx.log_file_path and os.path.exists(ctx.log_file_path):
            ctx.last_log_pos = os.path.getsize(ctx.log_file_path)

        python_exe = ctx.python_executable or ctx.env_data.get("path", "python")

        env_inject_code = "\n".join(
            [f"os.environ['{k}'] = '{v}'" for k, v in ctx.zmq_env_vars.items()]
        )

        local_comp_path = ctx.run_dir / "component.py"
        with open(local_comp_path, "w", encoding="utf-8") as f:
            f.write(ctx.component_code)

        log_file_path = str(ctx.log_file_path) if ctx.log_file_path else ""

        script_content = (
            "import os\n"
            + env_inject_code
            + "\n"
            + _EXECUTION_SCRIPT_TEMPLATE.format(
                class_name=ctx.class_name,
                file_path=str(local_comp_path.resolve()),
                params_path=str(ctx.params_path.resolve()),
                result_path=str(ctx.result_path.resolve()),
                error_path=str(ctx.error_path.resolve()),
                log_file_path=log_file_path,
                node_id=ctx.node.persistent_id,
                workflow_path=str(ctx.cache_path),
                is_memory_resident=False,
            )
        )

        local_script_path = ctx.run_dir / "exec_script.py"
        with open(local_script_path, "w", encoding="utf-8") as f:
            f.write(script_content)

        kwargs = {}
        if platform.system() == "Windows":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        proc = subprocess.Popen(
            [python_exe, str(local_script_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
            **kwargs,
        )

        start_time = time.time()
        while proc.poll() is None:
            if ctx.check_cancel and ctx.check_cancel():
                kill_proc_tree(proc.pid)
                raise Exception("执行已被用户取消")
            if ctx.timeout_enabled and time.time() - start_time > ctx.timeout_seconds:
                kill_proc_tree(proc.pid)
                raise Exception(f"执行超时（{ctx.timeout_seconds}秒）")
            self.read_logs(ctx)
            time.sleep(0.1)

        self.read_logs(ctx)
        ctx.node._log_message(ctx.node.persistent_id, "✅ 节点在独立环境执行完成")

        # 检查是否有错误
        error_info = self.read_error(ctx)
        if error_info:
            ctx.node._log_message(
                ctx.node.persistent_id, error_info.get("traceback", "")
            )
            raise Exception(error_info.get("traceback", "未知错误"))

        # 等待结果，有结果就读取，没有结果但进程正常退出也视为成功
        output = self.read_result(ctx)
        self.apply_outputs(ctx, output)
        return output

        output = self.read_result(ctx)
        self.apply_outputs(ctx, output)
        return output
