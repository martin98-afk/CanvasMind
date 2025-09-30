import os
import sys
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Optional
import venv
import platform
import urllib.request
import zipfile
import shutil

from PyQt5.QtCore import pyqtSignal
from loguru import logger


class EnvironmentManager:
    """智能 Python 环境管理器"""

    def __init__(self, base_dir: str = "environments"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        self.environments_file = self.base_dir / "environments.json"
        self._load_environments()

        # ✅ 修复：只在主进程中自动发现环境
        if self._is_main_process():
            self._auto_discover_environments()

    def _is_main_process(self) -> bool:
        """判断是否为主进程（避免 PyInstaller 子进程递归启动）"""
        if getattr(sys, "frozen", False):  # 打包后的程序
            forbidden = ("pip", "conda", "-m")
            return not any(arg in sys.argv for arg in forbidden)
        return True

    def _auto_discover_environments(self):
        """自动发现环境（只在主进程中执行）"""
        if not self._is_main_process():
            return

        logger.info("🔍 正在自动发现环境...")
        self._discover_conda_environments()
        self._discover_venv_environments()
        self._discover_virtualenv_environments()

        self._save_environments()
        logger.info("✅ 环境发现完成")

    def _load_environments(self):
        """加载环境配置"""
        if self.environments_file.exists():
            try:
                with open(self.environments_file, 'r', encoding='utf-8') as f:
                    self.environments = json.load(f)
            except Exception as e:
                logger.error(f"加载环境配置失败: {e}")
                self.environments = {}
        else:
            self.environments = {}

        # 确保至少有一个默认环境
        if not self.environments:
            self._create_default_environment()
            self._save_environments()

    def _download_embedded_python(self) -> Optional[str]:
        """下载并解压 Windows 嵌入版 Python"""
        if platform.system() != "Windows":
            return None

        embed_dir = self.base_dir / "python_embed"
        embed_dir.mkdir(exist_ok=True)
        python_exe = embed_dir / "python.exe"
        if python_exe.exists():
            return str(python_exe)

        url = "https://www.python.org/ftp/python/3.12.6/python-3.12.6-embed-amd64.zip"
        zip_path = embed_dir / "python_embed.zip"
        try:
            logger.info(f"📥 正在下载嵌入式 Python: {url}")
            urllib.request.urlretrieve(url, str(zip_path))
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(embed_dir)
            logger.info(f"✅ 嵌入式 Python 已安装: {python_exe}")
            return str(python_exe)
        except Exception as e:
            logger.error(f"下载嵌入式 Python 失败: {e}")
            return None

    def _create_default_environment(self):
        """创建默认环境"""
        # 优先尝试真实 python 可执行文件
        python_exe = None

        if getattr(sys, "frozen", False) and hasattr(sys, "_base_executable"):
            python_exe = sys._base_executable
        else:
            python_exe = shutil.which("python") or shutil.which("python3")

        if not python_exe:
            logger.warning("⚠️ 未找到系统 Python，尝试下载嵌入式 Python...")
            python_exe = self._download_embedded_python()

        if not python_exe:
            logger.error("❌ 无法找到或下载 Python，默认环境创建失败")
            return

        version = self._get_python_version(python_exe)
        self.environments["system"] = {
            "path": str(Path(python_exe).parent),
            "name": "默认环境",
            "type": "system",
            "python_version": version,
            "packages": self._get_system_packages()
        }

        # 可选：同时创建一个本地虚拟环境
        try:
            local_env_path = self.create_environment("local", sys.version_info[:2])
            self.environments["local"] = {
                "path": local_env_path,
                "name": "本地环境",
                "type": "venv",
                "python_version": self._get_python_version(
                    self.get_python_executable("local")
                ),
                "packages": []
            }
        except Exception as e:
            logger.error(f"创建本地环境失败: {e}")

        logger.info(f"✅ 已创建默认环境: {python_exe}")

    def _save_environments(self):
        """保存环境配置"""
        try:
            with open(self.environments_file, 'w', encoding='utf-8') as f:
                json.dump(self.environments, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存环境配置失败: {e}")

    def _discover_conda_environments(self):
        """发现 conda 环境"""
        try:
            result = subprocess.run(
                ['conda', 'env', 'list', '--json'],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=os.getcwd()
            )
            if result.returncode == 0:
                conda_info = json.loads(result.stdout)
                for env_path in conda_info.get('envs', []):
                    env_name = os.path.basename(env_path)
                    if env_name not in self.environments:
                        python_exe = self._get_conda_python_executable(env_path)
                        if python_exe and os.path.exists(python_exe):
                            version = self._get_python_version(python_exe)
                            self.environments[env_name] = {
                                "path": env_path,
                                "name": f"Conda: {env_name}",
                                "type": "conda",
                                "python_version": version,
                                "packages": []
                            }
        except Exception as e:
            logger.error(f"⚠️ 发现 conda 环境失败（已忽略）: {e}")

    def _discover_venv_environments(self):
        """发现 venv 环境"""
        common_dirs = [
            Path.home() / ".virtualenvs",
            Path.cwd() / "venv",
            Path.cwd() / ".venv",
            Path.cwd() / "env"
        ]
        for dir_path in common_dirs:
            if dir_path.exists():
                for env_dir in dir_path.iterdir():
                    if env_dir.is_dir():
                        env_name = env_dir.name
                        if env_name not in self.environments:
                            python_exe = self._get_venv_python_executable(env_dir)
                            if python_exe and os.path.exists(python_exe):
                                version = self._get_python_version(python_exe)
                                self.environments[env_name] = {
                                    "path": str(env_dir),
                                    "name": f"Venv: {env_name}",
                                    "type": "venv",
                                    "python_version": version,
                                    "packages": []
                                }

    def _discover_virtualenv_environments(self):
        """发现 virtualenv 环境"""
        pass

    def _get_conda_python_executable(self, env_path: str) -> str:
        if platform.system() == "Windows":
            return os.path.join(env_path, "Scripts", "python.exe")
        else:
            return os.path.join(env_path, "bin", "python")

    def _get_venv_python_executable(self, env_path: Path) -> str:
        if platform.system() == "Windows":
            return str(env_path / "Scripts" / "python.exe")
        else:
            return str(env_path / "bin" / "python")

    def _get_python_version(self, python_exe: str) -> str:
        try:
            result = subprocess.run([python_exe, '--version'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.error(f"获取 Python 版本失败: {e}")
        return "Unknown"

    def _get_system_packages(self) -> List[Dict]:
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'list', '--format=json'],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                packages = json.loads(result.stdout)
                return [{"name": p["name"], "version": p["version"]} for p in packages]
        except Exception as e:
            logger.error(f"获取系统包列表失败: {e}")
        return []

    def create_environment(self, name: str, python_version: tuple = None) -> str:
        env_path = self.base_dir / name
        if env_path.exists():
            raise ValueError(f"环境 {name} 已存在")

        builder = venv.EnvBuilder(with_pip=True, system_site_packages=False)
        builder.create(env_path)

        python_exe = self._get_venv_python_executable(env_path)
        try:
            subprocess.run([python_exe, '-m', 'pip', 'install', '--upgrade', 'pip'],
                           capture_output=True, timeout=60)
        except Exception as e:
            logger.error(f"升级 pip 失败: {e}")
        return str(env_path)

    def remove_environment(self, name: str):
        if name in ["default", "system"]:
            raise ValueError("不能删除系统环境")
        if name in self.environments:
            env_path = Path(self.environments[name]["path"])
            if env_path.exists():
                shutil.rmtree(env_path)
            del self.environments[name]
            self._save_environments()

    def list_environments(self) -> List[Dict]:
        return list(self.environments.values())

    def get_environment(self, name: str) -> Optional[Dict]:
        return self.environments.get(name)

    def get_python_executable(self, env_name: str) -> str:
        env_info = self.get_environment(env_name)
        if not env_info:
            raise ValueError(f"环境 {env_name} 不存在")

        if getattr(sys, "frozen", False) and hasattr(sys, "_base_executable"):
            return sys._base_executable

        env_path = Path(env_info["path"])
        if env_info["type"] == "conda":
            return self._get_conda_python_executable(str(env_path))
        elif env_info["type"] == "venv":
            return self._get_venv_python_executable(env_path)
        else:
            return sys.executable

    # ---------------- Pip 操作 ---------------- #
    def install_package(self, progress_signal: pyqtSignal, env_name: str,
                        package: str, version: str = None) -> bool:
        python_exe = self.get_python_executable(env_name)
        cmd = [python_exe, "-m", "pip", "install"]
        cmd.append(f"{package}=={version}" if version else package)
        return self._run_pip_command(cmd, progress_signal, env_name)

    def uninstall_package(self, progress_signal, env_name: str, package: str) -> bool:
        python_exe = self.get_python_executable(env_name)
        cmd = [python_exe, "-m", "pip", "uninstall", package, "-y"]
        return self._run_pip_command(cmd, progress_signal, env_name)

    def update_package(self, progress_signal, env_name: str, package: str) -> bool:
        python_exe = self.get_python_executable(env_name)
        cmd = [python_exe, "-m", "pip", "install", "--upgrade", package]
        return self._run_pip_command(cmd, progress_signal, env_name)

    def list_packages(self, env_name: str) -> List[Dict]:
        python_exe = self.get_python_executable(env_name)
        cmd = [python_exe, "-m", "pip", "list", "--format=json"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                packages = json.loads(result.stdout)
                return [{"name": p["name"], "version": p["version"]} for p in packages]
        except Exception as e:
            logger.error(f"获取包列表失败: {e}")
        return []

    def _run_pip_command(self, cmd: List[str], progress_signal, env_name: str) -> bool:
        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, universal_newlines=True
            )
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    progress_signal.emit(output.strip())
            if process.poll() == 0:
                self._update_package_list(env_name)
                return True
        except Exception as e:
            logger.error(f"Pip 命令执行失败: {e}")
        return False

    def _update_package_list(self, env_name: str):
        if env_name in self.environments:
            self.environments[env_name]["packages"] = self.list_packages(env_name)
            self._save_environments()

    def export_requirements(self, env_name: str, filepath: str) -> bool:
        python_exe = self.get_python_executable(env_name)
        cmd = [python_exe, "-m", "pip", "freeze"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(result.stdout)
                return True
        except Exception as e:
            logger.error(f"导出错误: {e}")
        return False

    def import_requirements(self, env_name: str, filepath: str) -> bool:
        python_exe = self.get_python_executable(env_name)
        cmd = [python_exe, "-m", "pip", "install", "-r", filepath]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                self._update_package_list(env_name)
                return True
        except Exception as e:
            logger.error(f"导入错误: {e}")
        return False


env_manager = EnvironmentManager()