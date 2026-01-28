import json
import uuid
import paramiko
class MockDSSKey: pass
paramiko.DSSKey = MockDSSKey
from qtconsole.client import QtKernelClient
from sshtunnel import SSHTunnelForwarder  # 导入线程级隧道库
from loguru import logger
from PyQt5.QtCore import QThread, pyqtSignal


class RemoteConnectWorker(QThread):
    """
    异步连接工人：
    负责在后台线程执行 SSH 连接和内核启动逻辑。
    """
    # 信号定义
    # bool: 是否成功, str: 错误消息（如果失败）
    finished = pyqtSignal(bool, str)
    # str: 状态描述消息，用于实时显示在控制台界面
    status_update = pyqtSignal(str)

    def __init__(self, manager, env_data):
        super().__init__()
        self.manager = manager
        self.env_data = env_data

    def run(self):
        """线程入口：执行耗时的连接逻辑"""
        try:
            # 这里的 status_callback=self.status_update.emit
            # 是将 manager 内部的进度文字实时通过信号发给 GUI
            success = self.manager.start_remote_kernel(
                self.env_data,
                status_callback=self.status_update.emit
            )

            if success:
                self.finished.emit(True, "")
            else:
                self.finished.emit(False, "启动过程未预期结束")

        except Exception as e:
            # 捕获连接过程中产生的各种异常（如 SSH 失败、内存错误等）
            import traceback
            error_detail = traceback.format_exc()
            self.finished.emit(False, error_detail)


class RemoteIPythonKernelManager:
    """基于线程级隧道的远程 IPython 内核管理器"""

    def __init__(self):
        self.ssh_client = None
        self.kernel_client = None
        self.remote_connection_file = None
        self.tunnels = []  # 存储 SSHTunnelForwarder 实例

        # 适配 RichJupyterWidget
        self.kernel_manager = None

    def is_alive(self):
        return self.kernel_client is not None and self.ssh_client is not None

    def start_remote_kernel(self, env_data: dict, status_callback=None):
        try:
            # 1. 建立基础 SSH 连接 (用于指令交互)
            if status_callback: status_callback("正在建立 SSH 安全连接...")
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # 这里的参数优化非常重要，能显著提升 Windows 下的连接速度
            self.ssh_client.connect(
                hostname=env_data['host'],
                port=int(env_data.get('port', 22)),
                username=env_data['user'],
                password=env_data.get('pwd'),
                key_filename=env_data.get('key_file'),
                timeout=10,
                look_for_keys=False,
                allow_agent=False,
                compress=True
            )

            # 2. 物理清理残留进程 (防止远程 MemoryError)
            self.ssh_client.exec_command("pkill -u $(whoami) -f ipykernel_launcher || true")

            # 3. 启动远程内核并获取配置
            kernel_id = uuid.uuid4().hex
            # 1. 准备路径
            remote_log = f"/tmp/kernel_{kernel_id}.log"
            self.remote_connection_file = f"/tmp/kernel_{kernel_id}.json"
            python_path = env_data.get('path', 'python')

            # 2. 极其严苛的远程脚本
            # 增加 sync 强制刷盘，增加 python 路径检测
.
0.0timeout_seconds = 300
            remote_script = (
                f"if [ ! -x '{python_path}' ]; then echo 'PYTHON_NOT_FOUND: {python_path}'; exit 1; fi; "
                f"export PYTHONUNBUFFERED=1; "
                f"nohup {python_path} -m ipykernel_launcher "
                f"--f={self.remote_connection_file} "
                f"--ip=127.0.0.1 "
                f"--KernelApp.shutdown_no_activity_timeout={timeout_seconds} "  # 核心参数
                f"> {remote_log} 2>&1 & "
                f"PID=$!; sleep 1; "
                f"for i in {{1..30}}; do "
                f"  if [ -f {self.remote_connection_file} ]; then cat {self.remote_connection_file}; exit 0; fi; "
                f"  if ! kill -0 $PID 2>/dev/null; then "
                f"    echo 'PROCESS_CRASHED_PID_'$PID; "
                f"    sync; cat {remote_log}; exit 1; "
                f"  fi; "
                f"  sleep 1; "
                f"done; "
                f"echo 'TIMEOUT_REACHED'; sync; cat {remote_log}; exit 1"
            )

            if status_callback: status_callback("正在尝试远程启动...")

            # 使用 get_pty=True 强制远程分配伪终端，这能解决很多环境变量不加载的问题
            stdin, stdout, stderr = self.ssh_client.exec_command(remote_script, get_pty=True)

            # 重要：读取顺序优化
            output = stdout.read().decode('utf-8', errors='ignore').strip()
            err_output = stderr.read().decode('utf-8', errors='ignore').strip()

            # 合并输出
            combined_log = (output + "\n" + err_output).strip()

            if combined_log.startswith('{'):
                # 成功情况：提取第一个 JSON 对象（防止后面带了杂质）
                import re
                json_match = re.search(r'\{.*\}', combined_log, re.DOTALL)
                if json_match:
                    connection_info = json.loads(json_match.group())
                else:
                    raise RuntimeError("匹配 JSON 失败")
            else:
                # 失败情况：如果 combined_log 还是空的，尝试直接读那个 log 文件
                if not combined_log:
                    _, log_out, _ = self.ssh_client.exec_command(
                        f"sync; [ -f {remote_log} ] && cat {remote_log} || echo 'Log file not found'")
                    combined_log = log_out.read().decode().strip()

                raise RuntimeError(f"远程内核启动失败。详细诊断信息:\n{combined_log}")

            # 4. 初始化 Qt 客户端
            self.kernel_client = QtKernelClient()
            self.kernel_client.load_connection_info(connection_info)

            # 5. 【核心改进】建立线程级 SSH 隧道
            if status_callback: status_callback("正在建立线程级安全隧道...")

            # 准备隧道通用参数
            ssh_host = env_data['host']
            ssh_port = int(env_data.get('port', 22))
            ssh_user = env_data['user']
            ssh_pass = env_data.get('pwd')
            ssh_key = env_data.get('key_file')

            self.tunnels = []
            port_names = ['shell_port', 'iopub_port', 'stdin_port', 'hb_port', 'control_port']

            for name in port_names:
                remote_port = connection_info[name]

                # 创建隧道实例：sshtunnel 在当前进程开线程，不启动新进程
                tunnel = SSHTunnelForwarder(
                    (ssh_host, ssh_port),
                    ssh_username=ssh_user,
                    ssh_password=ssh_pass,
                    ssh_pkey=ssh_key,
                    remote_bind_address=('127.0.0.1', remote_port),
                    local_bind_address=('127.0.0.1', 0),  # 自动分配本地可用端口
                    set_keepalive=30
                )
                tunnel.start()
                self.tunnels.append(tunnel)

                # 将隧道映射的本地端口告知 kernel_client
                setattr(self.kernel_client, name, tunnel.local_bind_port)
                logger.debug(f"已建立隧道: {name} -> 本地 {tunnel.local_bind_port}")

            # 6. 启动通道
            self.kernel_client.start_channels()

            # 增加心跳容错，防止网络抖动导致 died
            if hasattr(self.kernel_client, 'hb_channel'):
                self.kernel_client.hb_channel.time_to_dead = 10.0

            return True

        except Exception as e:
            logger.exception("连接远程内核失败")
            self.shutdown_kernel()
            raise e

    def shutdown_kernel(self):
        """清理所有资源"""
        logger.info("正在关闭远程内核及隧道...")
        if self.kernel_client:
            try:
                self.kernel_client.stop_channels()
            except:
                pass
            self.kernel_client = None

        # 关闭所有线程级隧道
        for t in self.tunnels:
            try:
                t.stop()
            except:
                pass
        self.tunnels = []

        if self.ssh_client:
            try:
                if self.remote_connection_file:
                    self.ssh_client.exec_command(f"rm -f {self.remote_connection_file}")
                self.ssh_client.close()
            except:
                pass
            self.ssh_client = None

    def execute_code(self, code, hidden=False):
        if self.kernel_client:
            return self.kernel_client.execute(code, silent=hidden)
        return None