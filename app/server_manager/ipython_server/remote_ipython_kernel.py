import json
import uuid
import time
import paramiko
from qtconsole.client import QtKernelClient
from jupyter_client.ssh.tunnel import open_tunnel
from loguru import logger
from PyQt5.QtCore import QThread, pyqtSignal


class RemoteConnectWorker(QThread):
    """异步连接工人"""
    finished = pyqtSignal(bool, str)
    status_update = pyqtSignal(str)

    def __init__(self, manager, env_data):
        super().__init__()
        self.manager = manager
        self.env_data = env_data

    def run(self):
        try:
            success = self.manager.start_remote_kernel(
                self.env_data,
                status_callback=self.status_update.emit
            )
            self.finished.emit(success, "")
        except Exception as e:
            self.finished.emit(False, str(e))


class RemoteIPythonKernelManager:
    """高性能远程 IPython 内核管理器"""

    def __init__(self):
        self.ssh_client = None
        self.kernel_client = None
        self.remote_connection_file = None
        self.tunnels = []

        # 兼容性属性：适配 RichJupyterWidget
        self.kernel_manager = None

    def is_alive(self):
        """检查内核和 SSH 是否依然活跃"""
        return self.kernel_client is not None and self.ssh_client is not None

    def _prepare_ssh_client(self, env_data):
        """创建优化的 SSH 客户端"""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # 性能优化：禁用 look_for_keys 和 allow_agent (Windows 下扫描磁盘极其缓慢)
        client.connect(
            hostname=env_data['host'],
            port=int(env_data.get('port', 22)),
            username=env_data['user'],
            password=env_data.get('pwd'),
            key_filename=env_data.get('key_file'),
            timeout=10,
            look_for_keys=False,
            allow_agent=False,
            compress=True  # 开启数据压缩
        )
        return client

    def start_remote_kernel(self, env_data: dict, status_callback=None):
        """
        启动远程内核 (建议在 QThread 中调用)
        """
        try:
            if status_callback: status_callback("正在建立 SSH 安全连接...")
            self.ssh_client = self._prepare_ssh_client(env_data)

            # 1. 物理清理：释放内存，防止 MemoryError
            if status_callback: status_callback("正在清理残留资源...")
            self.ssh_client.exec_command("pkill -u $(whoami) -f ipykernel_launcher || true")

            # 2. 合并指令：启动 + 轮询等待 + 读取 JSON，减少 RTT 网络往返
            kernel_id = uuid.uuid4().hex
            self.remote_connection_file = f"/tmp/kernel_{kernel_id}.json"
            python_path = env_data.get('path', 'python')

            # 复合 Shell 脚本：在服务器端阻塞，避免本地 Python 轮询导致的卡顿
            remote_script = (
                f"nohup {python_path} -m ipykernel_launcher --f={self.remote_connection_file} --ip=127.0.0.1 > /dev/null 2>&1 & "
                f"PID=$!; "
                f"for i in {{1..40}}; do "
                f"  if [ -f {self.remote_connection_file} ]; then cat {self.remote_connection_file}; exit 0; fi; "
                f"  if ! kill -0 $PID 2>/dev/null; then exit 1; fi; "
                f"  sleep 0.4; "
                f"done; exit 1"
            )

            if status_callback: status_callback("正在启动远程 Python 内核...")
            stdin, stdout, stderr = self.ssh_client.exec_command(remote_script)

            config_json = stdout.read().decode().strip()
            if not config_json or not config_json.startswith('{'):
                error_log = stderr.read().decode()
                raise RuntimeError(f"内核启动失败或超时。错误详情: {error_log}")

            connection_info = json.loads(config_json)

            # 3. 初始化 Qt 客户端
            self.kernel_client = QtKernelClient()
            self.kernel_client.load_connection_info(connection_info)

            # 4. 批量建立隧道
            if status_callback: status_callback("正在建立安全通信隧道...")
            ssh_server = f"{env_data['user']}@{env_data['host']}:{env_data.get('port', 22)}"
            password = env_data.get('pwd')

            port_names = ['shell_port', 'iopub_port', 'stdin_port', 'hb_port', 'control_port']
            for name in port_names:
                remote_port = connection_info[name]
                # 本地随机映射
                new_url, tunnel = open_tunnel(
                    f"tcp://127.0.0.1:{remote_port}",
                    ssh_server,
                    password=password,
                    keyfile=env_data.get('key_file')
                )
                self.tunnels.append(tunnel)
                local_port = int(new_url.split(':')[-1])
                setattr(self.kernel_client, name, local_port)

            # 5. 启动通道并进行就绪检查
            self.kernel_client.start_channels()
            return True

        except Exception as e:
            logger.exception("启动远程内核失败")
            self.shutdown_kernel()
            raise e

    def execute_code(self, code, hidden=False):
        """非阻塞发送执行指令"""
        if self.kernel_client:
            return self.kernel_client.execute(code, silent=hidden, stop_on_error=True)
        return None

    def interrupt_kernel(self):
        """中断当前执行"""
        if self.kernel_client:
            try:
                self.kernel_client.control_channel.execute("interrupt")
                return True
            except:
                return False
        return False

    def shutdown_kernel(self):
        """彻底清理所有资源"""
        logger.info("正在关闭远程连接并释放资源...")
        # 1. 关闭 Client 通道
        if self.kernel_client:
            try:
                self.kernel_client.stop_channels()
            except:
                pass
            self.kernel_client = None

        # 2. 关闭所有隧道 (必须在 SSH 关闭前)
        for t in self.tunnels:
            try:
                t.close()
            except:
                pass
        self.tunnels = []

        # 3. 清理远程进程及连接
        if self.ssh_client:
            try:
                if self.remote_connection_file:
                    cmd = f"pkill -f {self.remote_connection_file}; rm -f {self.remote_connection_file}"
                    self.ssh_client.exec_command(cmd)
                self.ssh_client.close()
            except:
                pass
            self.ssh_client = None