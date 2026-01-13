# -*- coding: utf-8 -*-

import paramiko
from PyQt5.QtCore import QThread, pyqtSignal


class SSHExecThread(QThread):
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

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
                password=self.env_data['pwd']
            )
            full_cmd = f"{self.env_data['path']} " + " ".join(self.cmd)
            stdin, stdout, stderr = ssh.exec_command(full_cmd, get_pty=True)
            for line in iter(stdout.readline, ""):
                self.output_signal.emit(line)
            ssh.close()
        except Exception as e:
            self.output_signal.emit(f"\n[错误] SSH 执行失败: {str(e)}")
        self.finished_signal.emit()
