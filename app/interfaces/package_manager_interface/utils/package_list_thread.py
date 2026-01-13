# -*- coding: utf-8 -*-
import platform
import subprocess

import paramiko
from PyQt5.QtCore import QThread, pyqtSignal


class PackageListThread(QThread):
    packages_loaded = pyqtSignal(str, str)
    error_occurred = pyqtSignal(Exception)

    def __init__(self, env_data, parent=None):
        super().__init__(parent)
        self.env_data = env_data

    def run(self):
        if isinstance(self.env_data, dict) and self.env_data.get("type") == "ssh":
            self._run_ssh()
        else:
            python_exe = self.env_data if isinstance(self.env_data, str) else self.env_data['path']
            self._run_local(python_exe)

    def _run_local(self, python_exe):
        kwargs = {}
        if platform.system() == "Windows":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            version_res = subprocess.run(
                [python_exe, "--version"],
                capture_output=True, text=True, check=True, **kwargs
            )
            py_version = version_res.stdout.strip()
            result = subprocess.run(
                [python_exe, "-m", "pip", "list", "--format=json", "--disable-pip-version-check"],
                capture_output=True, text=True, check=True, timeout=20, **kwargs
            )
            self.packages_loaded.emit(py_version, result.stdout.strip())
        except Exception as e:
            self.error_occurred.emit(e)

    def _run_ssh(self):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(
                hostname=self.env_data['host'],
                port=int(self.env_data.get('port', 22)),
                username=self.env_data['user'],
                password=self.env_data['pwd'],
                timeout=15
            )
            _, stdout, _ = ssh.exec_command(f"{self.env_data['path']} --version")
            py_version = stdout.read().decode().strip()
            _, stdout, _ = ssh.exec_command(f"{self.env_data['path']} -m pip list --format=json")
            pkg_json = stdout.read().decode().strip()
            ssh.close()
            self.packages_loaded.emit(py_version, pkg_json)
        except Exception as e:
            self.error_occurred.emit(e)