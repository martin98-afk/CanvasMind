import os

from PyQt5.QtCore import QThread, pyqtSignal
import paramiko

class SSHUploadAndExecThread(QThread):
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, env_data, local_paths, pip_action, is_requirements=False):
        super().__init__()
        self.env_data = env_data
        self.local_paths = local_paths  # 这是一个列表
        self.pip_action = pip_action    # 例如 "离线安装"
        self.is_requirements = is_requirements
        self.remote_temp_dir = "/tmp/pip_install_cache"

    def run(self):
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                hostname=self.env_data['host'],
                port=int(self.env_data.get('port', 22)),
                username=self.env_data['user'],
                password=self.env_data['pwd'],
                timeout=15
            )
            
            sftp = ssh.open_sftp()
            # 1. 创建远程临时目录
            ssh.exec_command(f"mkdir -p {self.remote_temp_dir}")
            
            remote_paths = []
            for lp in self.local_paths:
                self.output_signal.emit(f"> 正在上传: {os.path.basename(lp)} ...\n")
                # 强制转换为远程 Linux 路径
                rp = os.path.join(self.remote_temp_dir, os.path.basename(lp)).replace('\\', '/')
                
                if os.path.isdir(lp):
                    # 如果是目录，调用你已有的 sftp_upload_dir (需要稍作修改适配)
                    self._upload_dir_internal(sftp, lp, rp)
                    remote_paths.append(rp)
                else:
                    sftp.put(lp, rp)
                    remote_paths.append(rp)

            sftp.close()
            self.output_signal.emit("> 上传完成，开始安装...\n")

            # 2. 构造远程执行的 pip 命令
            # 假设远程 python 路径在 self.env_data['path']
            python_exe = self.env_data.get('path', 'python3')
            
            # 基础命令
            cmd_list = [python_exe, "-m", "pip", "install"]
            
            if self.is_requirements:
                cmd_list.extend(["-r", remote_paths[0]])
            else:
                if "离线" in self.pip_action:
                    cmd_list.append("--no-index")
                cmd_list.extend(remote_paths)

            full_cmd = " ".join(cmd_list)
            self.output_signal.emit(f"$ {full_cmd}\n")

            # 3. 执行安装
            stdin, stdout, stderr = ssh.exec_command(full_cmd, get_pty=True)
            for line in iter(stdout.readline, ""):
                self.output_signal.emit(line)
            
            ssh.close()
        except Exception as e:
            self.output_signal.emit(f"[错误] SSH操作失败: {str(e)}\n")
        finally:
            self.finished_signal.emit()

    def _upload_dir_internal(self, sftp, local_dir, remote_dir):
        # 简单的递归上传实现
        try:
            sftp.mkdir(remote_dir)
        except: pass
        for item in os.listdir(local_dir):
            l_path = os.path.join(local_dir, item)
            r_path = os.path.join(remote_dir, item).replace('\\', '/')
            if os.path.isdir(l_path):
                self._upload_dir_internal(sftp, l_path, r_path)
            else:
                sftp.put(l_path, r_path)