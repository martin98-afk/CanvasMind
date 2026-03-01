# -*- coding: utf-8 -*-
import os
import time

from app.nodes.executors.base import BaseExecutor
from app.templates.node_execute_script import _EXECUTION_SCRIPT_TEMPLATE


class IPythonExecutor(BaseExecutor):
    """IPython 执行器"""

    def can_execute(self, ctx) -> bool:
        return ctx.kernel_manager is not None

    def execute(self, ctx) -> dict:
        if ctx.log_file_path and os.path.exists(ctx.log_file_path):
            ctx.last_log_pos = os.path.getsize(ctx.log_file_path)

        local_comp_path = ctx.run_dir / "component.py"
        with open(local_comp_path, "w", encoding="utf-8") as f:
            f.write(ctx.component_code)

        env_inject_code = "\n".join(
            [f"os.environ['{k}'] = '{v}'" for k, v in ctx.zmq_env_vars.items()]
        )

        log_file_path = str(ctx.log_file_path) if ctx.log_file_path else ""

        # 只有 exec_mode = "ipython" 时才驻留
        # exec_mode = "subprocess" 且有 object_io 时不驻留
        exec_mode = getattr(ctx.node.view, "current_mode", None)
        is_memory_resident = exec_mode == "ipython"

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
                is_memory_resident=is_memory_resident,
            )
        )

        local_script_path = ctx.run_dir / "exec_script.py"
        with open(local_script_path, "w", encoding="utf-8") as f:
            f.write(script_content)

        with open(local_script_path, "r", encoding="utf-8") as f:
            code = f.read()

        ctx.kernel_manager.execute_code(code, hidden=True)

        start_time = time.time()
        while not (ctx.result_path.exists() or ctx.error_path.exists()):
            if ctx.check_cancel and ctx.check_cancel():
                if not ctx.kernel_manager.interrupt_kernel():
                    ctx.kernel_manager.restart_kernel()
                raise Exception("执行被用户取消")
            if ctx.timeout_enabled and time.time() - start_time > ctx.timeout_seconds:
                ctx.kernel_manager.interrupt_kernel()
                raise Exception(f"执行超时（{ctx.timeout_seconds}秒）")
            self.read_logs(ctx)
            time.sleep(0.05)

        self.read_logs(ctx)
        ctx.node._log_message(ctx.node.persistent_id, "✅ 节点在ipython环境执行完成")

        error_info = self.read_error(ctx)
        if error_info:
            raise Exception(error_info["traceback"])

        output = self.read_result(ctx)
        self.apply_outputs(ctx, output)
        return output
