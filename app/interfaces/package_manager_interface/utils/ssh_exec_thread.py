# -*- coding: utf-8 -*-

import paramiko
from PyQt5.QtCore import QThread, pyqtSignal


class SSHExecThread(QThread):
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    # 建议增加一个错误信号
    error_signal = pyqtSignal(str)

    def __init__(self, env_data, cmd, is_raw=False):
        super().__init__()
        self.env_data = env_data
        self.cmd = cmd
        self.is_raw = is_raw  # 新增开关：是否直接执行原始命令

    def run(self):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            # 增加 timeout 防止连接死等卡死 UI
            ssh.connect(
                hostname=self.env_data['host'],
                port=int(self.env_data.get('port', 22)),
                username=self.env_data['user'],
                password=self.env_data['pwd'],
                timeout=10
            )

            # --- 核心修复：根据类型处理命令 ---
            if self.is_raw:
                # 扫描环境时用这个：直接执行 cmd
                full_cmd = self.cmd
            else:
                # 执行 pip 任务时用这个：拼上 python 路径
                # 并且判断 cmd 是列表还是字符串
                cmd_str = " ".join(self.cmd) if isinstance(self.cmd, list) else self.cmd
                full_cmd = f"{self.env_data['path']} {cmd_str}"

            # 执行命令
            stdin, stdout, stderr = ssh.exec_command(full_cmd, get_pty=True)

            # 读取输出
            for line in iter(stdout.readline, ""):
                if line:
                    self.output_signal.emit(line)

            ssh.close()
        except Exception as e:
            err_msg = f"SSH 执行失败: {str(e)}"
            if hasattr(self, 'error_signal'):
                self.error_signal.emit(err_msg)
            else:
                self.output_signal.emit(err_msg)

        self.finished_signal.emit()
