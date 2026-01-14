# -*- coding: utf-8 -*-
import paramiko

from PyQt5.QtCore import QThread, pyqtSignal


class RemoteInstallThread(QThread):
    """专门用于依赖检查工具的远程安装线程"""
    finished_signal = pyqtSignal(bool, str)
    # 1. 添加缺失的信号定义
    line_received = pyqtSignal(str)

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

            # 组装命令
            full_cmd = f"{self.env_data['path']} " + " ".join(self.cmd)

            # 2. 执行命令
            # get_pty=True 可以让某些需要交互或实时刷新的命令输出更顺畅
            stdin, stdout, stderr = ssh.exec_command(full_cmd, get_pty=True)

            # 3. 实时读取输出并发送信号
            # 使用 iter 逐行读取 stdout
            for line in iter(stdout.readline, ""):
                if line:
                    self.line_received.emit(line.strip() + "\n")
                else:
                    break

            # 4. 获取最终状态
            exit_status = stdout.channel.recv_exit_status()

            if exit_status == 0:
                self.finished_signal.emit(True, "安装成功")
            else:
                # 如果失败，尝试读取错误信息
                err_msg = stderr.read().decode(errors='ignore')
                # 如果 stderr 为空（有时 get_pty 会把错误也定向到 stdout），给个通用提示
                if not err_msg:
                    err_msg = f"安装失败，退出码: {exit_status}"
                self.finished_signal.emit(False, err_msg)

            ssh.close()
        except Exception as e:
            self.finished_signal.emit(False, str(e))