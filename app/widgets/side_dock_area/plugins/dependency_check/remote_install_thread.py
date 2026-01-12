# -*- coding: utf-8 -*-
import paramiko

from PyQt5.QtCore import QThread, pyqtSignal


class RemoteInstallThread(QThread):
    """专门用于依赖检查工具的远程安装线程"""
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, env_data, cmd_list):
        super().__init__()
        self.env_data = env_data
        self.cmd = cmd_list

    def run(self):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(
                hostname=self.env_data['host'],
                port=int(self.env_data.get('port', 22)),
                username=self.env_data['user'],
                password=self.env_data['pwd'],
                timeout=30
            )
            # 组装命令，加入环境变量
            full_cmd = f"{self.env_data['path']} " + " ".join(self.cmd)
            stdin, stdout, stderr = ssh.exec_command(full_cmd)

            # 等待执行结束
            exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0:
                self.finished_signal.emit(True, "安装成功")
            else:
                err_msg = stderr.read().decode(errors='ignore')
                self.finished_signal.emit(False, err_msg)
            ssh.close()
        except Exception as e:
            self.finished_signal.emit(False, str(e))