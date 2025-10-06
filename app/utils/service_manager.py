# -*- coding: utf-8 -*-
import json
import os
import socket
import subprocess
from typing import Optional

import psutil

# 全局已用端口集合（避免冲突）
USED_PORTS = set()


def find_available_port(start=8000, end=9000):
    """查找可用端口"""
    for port in range(start, end + 1):
        if port not in USED_PORTS:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("0.0.0.0", port))
                USED_PORTS.add(port)
                return port
            except OSError:
                continue
    raise RuntimeError(f"无法在 {start}-{end} 范围内找到可用端口")


def release_port(port):
    """释放端口"""
    USED_PORTS.discard(port)


class MicroserviceManager:
    def __init__(self):
        self.services = {}
        self._restore_services()

    def start_service(self, project_path: str) -> str:
        if project_path in self.services:
            return self.services[project_path]["url"]

        service_script = os.path.join(project_path, "api_server.py")
        if not os.path.exists(service_script):
            raise FileNotFoundError("未找到微服务代码 (api_server.py)")

        port = find_available_port()
        url = f"http://0.0.0.0:{port}/run"
        log_file = os.path.join(project_path, "service.log")

        workflow_path = os.path.join(project_path, "model.workflow.json")
        with open(workflow_path, 'r', encoding='utf-8') as f:
            python_exe = json.load(f).get("runtime", {}).get("environment_exe")
            if not python_exe:
                raise ValueError("未指定 Python 解释器路径")

        cmd = [python_exe, "api_server.py", "--port", str(port)]
        with open(log_file, 'w', encoding='utf-8') as log_f:
            process = subprocess.Popen(
                cmd,
                cwd=project_path,
                stdout=log_f,
                stderr=subprocess.STDOUT,  # 合并 stderr 到 stdout
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                encoding='utf-8'
            )

        self.services[project_path] = {
            "process": process,
            "port": port,
            "url": url,
            "log_file": log_file  # 注意：现在 log_file 可能不存在！
        }
        return url

    def _restore_services(self):
        if not os.path.exists("projects"):
            return

        for item in os.listdir("projects"):
            project_path = os.path.join("projects", item)
            if not os.path.isdir(project_path):
                continue

            log_file = os.path.join(project_path, "service.log")
            workflow_file = os.path.join(project_path, "model.workflow.json")
            if not (os.path.exists(log_file) and os.path.exists(workflow_file)):
                continue

            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    log_content = f.read()
                if "Uvicorn running on" not in log_content:
                    continue

                import re
                port_match = re.search(r"Uvicorn running on http://[^:]+:(\d+)", log_content)
                if not port_match:
                    continue
                port = int(port_match.group(1))

                if not self._is_port_in_use(port):
                    continue

                is_our_service = False
                for proc in psutil.process_iter(['pid', 'cmdline']):
                    try:
                        cmdline = proc.info['cmdline']
                        if cmdline and 'api_server.py' in ' '.join(cmdline) and f'--port {port}' in ' '.join(cmdline) and project_path in ' '.join(cmdline):
                            is_our_service = True
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue

                if is_our_service:
                    url = f"http://0.0.0.0:{port}/run"
                    self.services[project_path] = {
                        "process": None,  # 无法获取原进程对象
                        "port": port,
                        "url": url,
                        "log_file": log_file
                    }
                    USED_PORTS.add(port)
            except Exception as e:
                print(f"恢复服务失败 {project_path}: {e}")

    def _is_port_in_use(self, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('0.0.0.0', port)) == 0

    def stop_service(self, project_path: str):
        if project_path not in self.services:
            return

        service = self.services[project_path]
        process = service["process"]
        port = service["port"]

        try:
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        except Exception:
            pass

        release_port(port)
        del self.services[project_path]

    def is_running(self, project_path: str) -> bool:
        return project_path in self.services

    def get_url(self, project_path: str) -> Optional[str]:
        return self.services.get(project_path, {}).get("url").replace("0.0.0.0", "127.0.0.1")


SERVICE_MANAGER = MicroserviceManager()
