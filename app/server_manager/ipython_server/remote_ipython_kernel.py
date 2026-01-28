import json
import uuid
import time
import paramiko
from qtconsole.client import QtKernelClient  # 必须使用这个
from jupyter_client.ssh.tunnel import open_tunnel
from loguru import logger


from PyQt5.QtCore import QThread, pyqtSignal

class RemoteKernelThread(QThread):
    """专门用于连接远程内核的后台线程"""
    finished = pyqtSignal(bool, str)  # 成功标志, 错误消息
    status_msg = pyqtSignal(str)      # 状态更新信号

    def __init__(self, manager, env_data):
        super().__init__()
        self.manager = manager
        self.env_data = env_data

    def run(self):
        try:
            self.status_msg.emit("正在建立 SSH 连接...")
            success = self.manager._do_start_remote_kernel(self.env_data, self.status_msg.emit)
            if success:
                self.finished.emit(True, "")
            else:
                self.finished.emit(False, "启动内核失败")
        except Exception as e:
            self.finished.emit(False, str(e))


class RemoteIPythonKernelManager:
    """远程 IPython 内核管理器"""

    def __init__(self):
        self.ssh_client = None
        self.kernel_client = None
        self.kernel_manager = None  # 占位适配接口
        self.remote_connection_file = None
        self.tunnels = []

    def _do_start_remote_kernel(self, env_data: dict, status_callback=None):
        """真正的连接逻辑，在后台线程中运行"""
        try:
            # 1. 优化 SSH 连接速度
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # 禁用 look_for_keys 和 allow_agent 可以加快纯密码连接的速度
            self.ssh_client.connect(
                hostname=env_data['host'],
                port=int(env_data.get('port', 22)),
                username=env_data['user'],
                password=env_data.get('pwd'),
                timeout=10,
                look_for_keys=False,  # 禁止搜索本地私钥，大幅加速
                allow_agent=False,  # 禁止 SSH Agent，加速
                compress=True,  # 开启压缩
            )

            # 2. 优化远程启动命令
            # 技巧：不再在 Python 层写循环，而是在远程用一个 Shell 命令完成“启动+等待+读取”
            # 这样只需一次 SSH 往返
            kernel_id = uuid.uuid4().hex
            self.remote_connection_file = f"/tmp/kernel_{kernel_id}.json"
            python_path = env_data.get('path', 'python')

            # 这是一个复合命令：后台启动 ipykernel -> 循环检测文件 -> cat 内容并删除临时标志
            remote_cmd = (
                f"nohup {python_path} -m ipykernel_launcher --f={self.remote_connection_file} --ip=127.0.0.1 > /dev/null 2>&1 & "
                f"for i in {{1..20}}; do if [ -f {self.remote_connection_file} ]; then cat {self.remote_connection_file}; break; fi; sleep 0.5; done"
            )

            if status_callback: status_callback("正在远程启动内核并获取配置...")
            stdin, stdout, stderr = self.ssh_client.exec_command(remote_cmd)

            # 读取复合命令的输出（即 json 内容）
            config_json = stdout.read().decode().strip()
            if not config_json or not config_json.startswith('{'):
                raise RuntimeError(f"内核启动超时或失败: {stderr.read().decode()}")

            connection_info = json.loads(config_json)

            # 3. 创建客户端
            self.kernel_client = QtKernelClient()
            self.kernel_client.load_connection_info(connection_info)

            # 4. 建立隧道
            if status_callback: status_callback("正在建立端口转发隧道...")
            ssh_server = f"{env_data['user']}@{env_data['host']}:{env_data.get('port', 22)}"

            port_names = ['shell_port', 'iopub_port', 'stdin_port', 'hb_port', 'control_port']
            for name in port_names:
                remote_port = connection_info[name]
                # open_tunnel 本身比较耗时，因为它涉及到本地 Socket 绑定
                new_url, tunnel = open_tunnel(
                    f"tcp://127.0.0.1:{remote_port}",
                    ssh_server,
                    password=env_data.get('pwd')
                )
                self.tunnels.append(tunnel)
                local_port = int(new_url.split(':')[-1])
                setattr(self.kernel_client, name, local_port)

            self.kernel_client.start_channels()
            return True

        except Exception as e:
            logger.error(f"远程启动失败: {e}")
            self.shutdown_kernel()
            raise e

    def is_alive(self):
        """适配接口：判断内核是否连接"""
        return self.kernel_client is not None and self.ssh_client is not None

    def shutdown_kernel(self):
        if self.kernel_client:
            self.kernel_client.stop_channels()
            self.kernel_client = None
        for t in self.tunnels:
            try: t.close()
            except: pass
        self.tunnels = []
        if self.ssh_client:
            if self.remote_connection_file:
                self.ssh_client.exec_command(f"pkill -f {self.remote_connection_file} && rm {self.remote_connection_file}")
            self.ssh_client.close()
            self.ssh_client = None

    def execute_code(self, code, hidden=False):
        """
        向远程内核发送执行请求
        :param code: 要执行的 Python 代码字符串
        :param hidden: 是否为隐藏执行（如果为 True，控制台通常不显示输出，且不计数）
        :return: msg_id (消息 ID)
        """
        if not self.kernel_client:
            logger.error("远程内核客户端未连接，无法执行代码")
            return None

        # 使用 QtKernelClient 发送执行请求
        # silent=hidden 确保如果是后台清理代码，不会增加提示符计数(In [1])
        # stop_on_error=True 遇到错误停止执行
        msg_id = self.kernel_client.execute(code, silent=hidden, stop_on_error=True)

        logger.debug(f"已发送远程执行请求，Msg ID: {msg_id}")
        return msg_id

    def interrupt_kernel(self):
        """中断内核"""
        if self.kernel_client:
            # 发送 SIGINT 信号到远程进程其实比较复杂
            # 这里尝试通过控制通道发送中断请求 (依赖内核支持)
            try:
                self.kernel_client.control_channel.execute("interrupt")
                return True
            except:
                return False
        return False