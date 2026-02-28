# -*- coding: utf-8 -*-
import os
import time

import paramiko

from app.nodes.executors.base import BaseExecutor
from app.templates.node_execute_script import _EXECUTION_SCRIPT_TEMPLATE
from app.utils.utils import sftp_download_dir, replace_remote_paths, sftp_upload_dir
from app.components.base import resource_path


class SSHExecutor(BaseExecutor):
    """SSH 远程执行器"""

    def can_execute(self, ctx) -> bool:
        return ctx.env_data.get("type") == "ssh"

    def prepare_environment(self, ctx) -> None:
        super().prepare_environment(ctx)
        ctx.remote_root = "/tmp/workspace"

    def execute(self, ctx) -> dict:
        if ctx.log_file_path and os.path.exists(ctx.log_file_path):
            ctx.last_log_pos = os.path.getsize(ctx.log_file_path)

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            ssh.connect(
                ctx.env_data["host"],
                int(ctx.env_data.get("port", 22)),
                ctx.env_data["user"],
                ctx.env_data["pwd"],
                timeout=15,
                compress=True,
            )
            sftp = ssh.open_sftp()

            remote_root = ctx.remote_root
            remote_id = ctx.node.persistent_id
            upload_dir = f"{remote_root}/{remote_id}/upload"
            result_dir = f"{remote_root}/{remote_id}/result"
            remote_run_dir = f"{remote_root}/{remote_id}/run_scripts"
            log_path = f"{remote_root}/node_logs/{remote_id}.log"
            local_node_workspace = ctx.cache_path / "workspace" / remote_id

            ssh.exec_command(
                f"mkdir -p {upload_dir} {result_dir} {remote_run_dir} {remote_root}/node_logs"
            )
            ssh.exec_command(f"rm -f {log_path}| touch {log_path}")

            env_inject_code = "\n".join(
                [f"os.environ['{k}'] = '{v}'" for k, v in ctx.zmq_env_vars.items()]
            )

            remote_script_content = (
                "import os\n"
                + env_inject_code
                + "\n"
                + _EXECUTION_SCRIPT_TEMPLATE.format(
                    class_name=ctx.class_name,
                    file_path=f"{remote_run_dir}/component.py",
                    params_path=f"{remote_run_dir}/params.pkl",
                    result_path=f"{remote_run_dir}/result.pkl",
                    error_path=f"{remote_run_dir}/error.pkl",
                    log_file_path=log_path,
                    node_id=ctx.node.persistent_id,
                    workflow_path="/tmp",
                    is_memory_resident=getattr(ctx.node.view, "current_mode", None)
                    == "ipython",
                )
            )

            with open(ctx.run_dir / "exec_script.py", "w", encoding="utf-8") as f:
                f.write(remote_script_content)

            local_comp_path = ctx.run_dir / "component.py"
            with open(local_comp_path, "w", encoding="utf-8") as f:
                f.write(ctx.component_code)

            local_upload_dir = local_node_workspace / "upload"
            if local_upload_dir.exists():
                sftp_upload_dir(sftp, local_upload_dir, upload_dir)

            node_uuid = getattr(ctx.node, "uuid", "")
            if node_uuid:
                sftp_upload_dir(
                    sftp,
                    resource_path(f"app/component_extensions/{node_uuid}"),
                    f"{remote_root}/{remote_id}",
                )

            sftp_upload_dir(sftp, ctx.run_dir, remote_run_dir)
            sftp.put(
                resource_path("app/components/base.py"),
                f"{remote_root}/{remote_id}/base.py",
            )

            last_log_pos = 0
            is_ipython_mode = getattr(ctx.node.view, "current_mode", None) == "ipython"

            if is_ipython_mode and ctx.kernel_manager:
                ctx.kernel_manager.execute_code(remote_script_content, hidden=True)
                start_time = time.time()
                remote_res = f"{remote_run_dir}/result.pkl"
                remote_err = f"{remote_run_dir}/error.pkl"

                while True:
                    if ctx.check_cancel and ctx.check_cancel():
                        ctx.kernel_manager.interrupt_kernel()
                        raise Exception("远程 IPython 执行被取消")

                    _, stdout, _ = ssh.exec_command(f"ls {remote_res} {remote_err}")
                    found = stdout.read().decode()

                    try:
                        with sftp.open(log_path, "r") as f:
                            f.seek(last_log_pos)
                            new_data = f.read().decode("utf-8", errors="ignore")
                            if new_data:
                                ctx.node._log_message(ctx.node.persistent_id, new_data)
                                last_log_pos = f.tell()
                    except:
                        pass

                    if remote_res in found or remote_err in found:
                        break
                    if (
                        ctx.timeout_enabled
                        and time.time() - start_time > ctx.timeout_seconds
                    ):
                        ctx.kernel_manager.interrupt_kernel()
                        raise Exception("远程 IPython 执行超时")
                    time.sleep(0.5)
            else:
                python_exe = ctx.env_data["path"]
                env_cmd = " ".join([f"{k}={v}" for k, v in ctx.zmq_env_vars.items()])
                cmd = f"export PYTHONPATH={remote_root}:$PYTHONPATH && export {env_cmd} && {python_exe} {remote_run_dir}/exec_script.py"
                stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
                stdout.channel.setblocking(0)
                start_time = time.time()

                while not stdout.channel.exit_status_ready():
                    if ctx.check_cancel and ctx.check_cancel():
                        ssh.exec_command(f"pkill -f {remote_run_dir}/exec_script.py")
                        ssh.close()
                        raise Exception("远程执行被用户取消")

                    try:
                        with sftp.open(log_path, "r") as f:
                            f.seek(last_log_pos)
                            new_data = f.read().decode("utf-8", errors="ignore")
                            if new_data:
                                ctx.node._log_message(ctx.node.persistent_id, new_data)
                                last_log_pos = f.tell()
                    except:
                        pass

                    if (
                        ctx.timeout_enabled
                        and time.time() - start_time > ctx.timeout_seconds
                    ):
                        ssh.exec_command(f"pkill -f {remote_run_dir}/exec_script.py")
                        ssh.close()
                        raise Exception("执行超时")
                    time.sleep(0.5)

            local_result_path = ctx.run_dir / "result.pkl"
            try:
                sftp.get(f"{remote_run_dir}/result.pkl", str(local_result_path))
                replace_remote_paths(
                    local_result_path,
                    f"{remote_root}/{remote_id}",
                    str(local_node_workspace),
                )
            except:
                if local_result_path.exists():
                    os.remove(local_result_path)

            try:
                sftp.get(f"{remote_run_dir}/error.pkl", str(ctx.error_path))
            except:
                if ctx.error_path.exists():
                    os.remove(ctx.error_path)

            local_res_dir = local_node_workspace / "result"
            local_res_dir.mkdir(parents=True, exist_ok=True)
            try:
                sftp_download_dir(sftp, result_dir, local_res_dir, ssh=ssh)
            except:
                pass

            ssh.exec_command(f"rm -rf {remote_run_dir}")
            with sftp.open(log_path, "r") as f:
                f.seek(last_log_pos)
                new_data = f.read().decode("utf-8", errors="ignore")
                if new_data:
                    ctx.node._log_message(ctx.node.persistent_id, new_data)

            ctx.node._log_message(
                ctx.node.persistent_id, "✅ 节点在ssh远程环境执行完成"
            )

            if not self.wait_for_result(ctx):
                raise Exception("执行结束，未发现结果")

            output = self.read_result(ctx)
            self.apply_outputs(ctx, output)
            return output

        finally:
            if "sftp" in locals():
                sftp.close()
            ssh.close()
