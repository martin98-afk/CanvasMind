# -*- coding: utf-8 -*-
import json
import platform
import re
import shutil
import traceback
from pathlib import Path
from PyQt5.QtCore import QObject, pyqtSignal, QProcess, QTimer, QUrl
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
from loguru import logger


class EnvironmentManager(QObject):
    """使用Miniconda管理Python环境"""

    # 信号
    log_signal = pyqtSignal(str)
    install_finished = pyqtSignal()  # 传递结果或异常
    miniconda_install_finished = pyqtSignal(object)
    remove_finished = pyqtSignal(object)

    ENV_DIR = Path(__file__).parent.parent.parent / "envs"
    META_FILE = ENV_DIR / "environments.json"

    # Miniconda安装包下载链接（已去除多余空格）
    MINICONDA_URLS = {
        "3.9": "https://repo.anaconda.com/miniconda/Miniconda3-py39_23.11.0-2-Windows-x86_64.exe",
        "3.10": "https://repo.anaconda.com/miniconda/Miniconda3-py310_23.11.0-2-Windows-x86_64.exe",
        "3.11": "https://repo.anaconda.com/miniconda/Miniconda3-py311_23.11.0-2-Windows-x86_64.exe",
        "3.12": "https://repo.anaconda.com/miniconda/Miniconda3-py312_23.11.0-2-Windows-x86_64.exe",
        "3.13": "https://repo.anaconda.com/miniconda/Miniconda3-py313_23.11.0-2-Windows-x86_64.exe",
        "3.14": "https://repo.anaconda.com/miniconda/Miniconda3-py314_23.11.0-2-Windows-x86_64.exe",
    }

    # 默认要安装的包列表
    DEFAULT_PACKAGES = ["loguru", "pydantic", "pandas", "Pillow", "fastapi", "uvicorn", "jedi", "asteval"]

    def __init__(self):
        super().__init__()
        self.ENV_DIR.mkdir(exist_ok=True)
        if not self.META_FILE.exists():
            self._save_meta({})
        # 检查是否已安装Miniconda
        self.miniconda_path = self.ENV_DIR / "miniconda"
        logger.info(f"检查Miniconda安装状态: {self.miniconda_path}")
        self.meta = self._load_meta()
        self._scan_envs()

        # 网络管理器（用于异步下载）
        self._network_manager = QNetworkAccessManager(self)
        self._network_manager.finished.connect(self._on_download_finished)

        # 当前操作状态
        self._current_log_callback = None
        self._installer_path = None
        self._process = None
        self._pending_env_creation = None  # (version, env_name, log_callback)

    def _load_meta(self):
        try:
            return json.loads(self.META_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_meta(self, data):
        self.META_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _scan_envs(self):
        """只扫描 self.miniconda_path 下的环境"""
        new_meta = {}

        miniconda_envs_dir = self.miniconda_path / "envs"
        if miniconda_envs_dir.exists():
            for d in miniconda_envs_dir.iterdir():
                if d.is_dir() and (d / "python.exe").exists():
                    new_meta[d.name] = str(d)
        self.meta = new_meta
        self._save_meta(self.meta)

    def _is_miniconda_installed(self):
        """检查Miniconda是否已安装"""
        return (self.miniconda_path / "Scripts" / "conda.exe").exists()

    def install_miniconda(self, log_callback=None):
        """安装Miniconda（异步下载 + 静默安装）"""
        if self._is_miniconda_installed():
            if log_callback:
                log_callback("Miniconda已安装")
            self.miniconda_install_finished.emit("success")
            return

        if log_callback:
            log_callback("正在准备安装Miniconda...")

        self._current_log_callback = log_callback
        url = self.MINICONDA_URLS["3.11"]  # 默认安装Python 3.11版本
        self._installer_path = self.ENV_DIR / url.split("/")[-1]

        # ✅ 先检查本地是否已有安装包
        if self._installer_path.exists():
            if log_callback:
                log_callback("本地已存在Miniconda安装包，跳过下载")
            self._start_miniconda_install()
        else:
            if log_callback:
                log_callback(f"正在下载Miniconda安装包...")
            # ✅ 异步下载（不阻塞主线程）
            request = QNetworkRequest(QUrl(url))
            self._network_manager.get(request)

    def _on_download_finished(self, reply):
        """Miniconda安装包下载完成回调"""
        try:
            if reply.error():
                error_msg = f"Miniconda下载失败: {reply.errorString()}"
                if self._current_log_callback:
                    self._current_log_callback(error_msg)
                self.miniconda_install_finished.emit(RuntimeError(error_msg))
                return

            # 保存安装包
            data = reply.readAll()
            with open(self._installer_path, "wb") as f:
                f.write(data)

            if self._current_log_callback:
                self._current_log_callback("Miniconda下载完成，开始安装...")

            self._start_miniconda_install()
        except Exception as e:
            self.miniconda_install_finished.emit(e)
        finally:
            reply.deleteLater()

    def _start_miniconda_install(self):
        """启动Miniconda静默安装进程"""
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_process_output)
        self._process.finished.connect(self._on_miniconda_install_finished)

        if platform.system() == "Windows":
            self._process.setProcessEnvironment(self._get_hidden_window_environment())

        # 启动安装
        self._process.start(str(self._installer_path), [
            "/S",  # 静默安装
            f"/D={str(self.miniconda_path)}"  # 指定安装路径
        ])

    def _on_miniconda_install_finished(self, exit_code, exit_status):
        """Miniconda安装完成回调"""
        try:
            conda_exe = self.miniconda_path / "Scripts" / "conda.exe"
            if not conda_exe.exists():
                error_msg = "Miniconda安装失败：未找到 conda.exe"
                if self._current_log_callback:
                    self._current_log_callback(error_msg)
                self.miniconda_install_finished.emit(RuntimeError(error_msg))
                return

            if self._current_log_callback:
                self._current_log_callback("Miniconda安装完成")

            # 清理安装包
            if self._installer_path and self._installer_path.exists():
                self._installer_path.unlink()

            # 更新环境列表
            self._scan_envs()

            self.miniconda_install_finished.emit("success")

            # 如果有待创建的环境，现在执行
            if self._pending_env_creation:
                version, env_name, log_cb = self._pending_env_creation
                self._pending_env_creation = None
                QTimer.singleShot(1000, lambda: self._create_env_with_qprocess(version, env_name, log_cb))

        except Exception as e:
            self.miniconda_install_finished.emit(e)

    def download_and_install(self, version, env_name=None, log_callback=None):
        """创建指定版本的Python环境"""
        if not self._is_miniconda_installed():
            if log_callback:
                log_callback("Miniconda未安装，正在安装...")
            # 记录待创建的环境
            self._pending_env_creation = (version, env_name, log_callback)
            self.install_miniconda(log_callback)
            return

        self._create_env_with_qprocess(version, env_name, log_callback)

    def _create_env_with_qprocess(self, version, env_name=None, log_callback=None):
        """使用QProcess创建环境"""
        # 提取主要版本号
        major_version = ".".join(version.split(".")[:2])
        if major_version not in ["3.9", "3.10", "3.11", "3.12", "3.13", "3.14"]:
            major_version = "3.11"

        if env_name is None:
            env_name = version

        # 检查环境是否已存在
        existing_envs = self.list_envs()
        if env_name in existing_envs:
            if log_callback:
                log_callback(f"环境 {env_name} 已存在")
            python_exe = self.get_python_exe(env_name)
            env_path = python_exe.parent
            self.meta[env_name] = str(env_path)
            self._save_meta(self.meta)
            self.install_finished.emit(env_path)
            return

        if log_callback:
            log_callback(f"正在创建Python {version}环境，环境名为: {env_name}...")

        self._current_log_callback = log_callback
        conda_exe = self.miniconda_path / "Scripts" / "conda.exe"

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_process_output)
        if platform.system() == "Windows":
            self._process.setProcessEnvironment(self._get_hidden_window_environment())
        self._process.finished.connect(
            lambda ec, es: self._on_create_env_finished(ec, es, env_name)
        )

        self._process.start(str(conda_exe), [
            "create",
            "--name", env_name,
            f"python={version}",
            "-y"
        ])

    def clone_env(self, source_env, target_env, log_callback=None):
        """克隆已有环境"""
        if source_env not in self.list_envs():
            error_msg = f"源环境 {source_env} 不存在"
            if log_callback:
                log_callback(error_msg)
            self.install_finished.emit(RuntimeError(error_msg))
            return

        if target_env in self.list_envs():
            if log_callback:
                log_callback(f"目标环境 {target_env} 已存在")
            python_exe = self.get_python_exe(target_env)
            env_path = python_exe.parent
            self.meta[target_env] = str(env_path)
            self._save_meta(self.meta)
            self.install_finished.emit(env_path)
            return

        if log_callback:
            log_callback(f"正在克隆环境 {source_env} 到 {target_env}...")

        self._current_log_callback = log_callback
        conda_exe = self.miniconda_path / "Scripts" / "conda.exe"

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_process_output)
        if platform.system() == "Windows":
            self._process.setProcessEnvironment(self._get_hidden_window_environment())
        self._process.finished.connect(
            lambda ec, es: self._on_clone_env_finished(ec, es, target_env)
        )

        self._process.start(str(conda_exe), [
            "create",
            "--name", target_env,
            "--clone", source_env,
            "-y"
        ])

    def _on_clone_env_finished(self, exit_code, exit_status, env_name):
        try:
            if exit_code != 0:
                error_msg = f"环境 {env_name} 克隆失败，退出码: {exit_code}"
                if self._current_log_callback:
                    self._current_log_callback(error_msg)
                self.install_finished.emit(RuntimeError(error_msg))
                return

            python_exe = self.get_python_exe(env_name)
            if not python_exe.exists():
                error_msg = f"环境 {env_name} 克隆失败，未找到 python.exe"
                if self._current_log_callback:
                    self._current_log_callback(error_msg)
                self.install_finished.emit(RuntimeError(error_msg))
                return

            env_path = python_exe.parent
            self.meta[env_name] = str(env_path)
            self._save_meta(self.meta)
            self._scan_envs()
            if self._current_log_callback:
                self._current_log_callback(f"环境 {env_name} 克隆完成 ✅")

            QTimer.singleShot(1000, lambda: self._install_default_packages(env_name, python_exe))
        except Exception as e:
            self.install_finished.emit(e)

    def _on_create_env_finished(self, exit_code, exit_status, env_name):
        try:
            if exit_code != 0:
                error_msg = f"环境 {env_name} 创建失败，退出码: {exit_code}"
                if self._current_log_callback:
                    self._current_log_callback(error_msg)
                self.install_finished.emit(RuntimeError(error_msg))
                return

            python_exe = self.get_python_exe(env_name)
            if not python_exe.exists():
                error_msg = f"环境 {env_name} 创建失败，未找到 python.exe"
                if self._current_log_callback:
                    self._current_log_callback(error_msg)
                self.install_finished.emit(RuntimeError(error_msg))
                return

            env_path = python_exe.parent
            self.meta[env_name] = str(env_path)
            self._save_meta(self.meta)
            self._scan_envs()
            if self._current_log_callback:
                self._current_log_callback(f"Python {env_name} 环境创建完成 ✅")

            QTimer.singleShot(1000, lambda: self._install_default_packages(env_name, python_exe))
        except Exception as e:
            print(traceback.format_exc())

    def _install_default_packages(self, env_name, python_exe):
        if self._current_log_callback:
            self._current_log_callback(f"正在安装默认包: {', '.join(self.DEFAULT_PACKAGES)}")
        self._install_next_package(python_exe, list(self.DEFAULT_PACKAGES))

    def _install_next_package(self, python_exe, remaining_packages):
        if not remaining_packages:
            if self._current_log_callback:
                self._current_log_callback("默认包安装完成 ✅")
            self.install_finished.emit()
            return

        package = remaining_packages[0]
        if self._current_log_callback:
            self._current_log_callback(f"正在安装 {package}...")

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_process_output)
        if platform.system() == "Windows":
            self._process.setProcessEnvironment(self._get_hidden_window_environment())
        self._process.finished.connect(
            lambda ec, es: self._on_package_installed(ec, es, python_exe, remaining_packages[1:])
        )
        self._process.start(str(python_exe), ["-m", "pip", "install", package])

    def _on_package_installed(self, exit_code, exit_status, python_exe, remaining_packages):
        if exit_code != 0:
            if self._current_log_callback:
                self._current_log_callback(f"包安装失败，继续安装下一个包")
        else:
            if self._current_log_callback:
                self._current_log_callback("✅ 包安装完成")
        QTimer.singleShot(500, lambda: self._install_next_package(python_exe, remaining_packages))

    def remove_env(self, env_name, log_callback=None):
        if env_name not in self.meta and env_name not in self.list_envs():
            error_msg = f"环境 {env_name} 不存在"
            if log_callback:
                log_callback(error_msg)
            self.remove_finished.emit(RuntimeError(error_msg))
            return

        if log_callback:
            log_callback(f"正在删除环境 {env_name}...")

        self._current_log_callback = log_callback
        conda_exe = self.miniconda_path / "Scripts" / "conda.exe"

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_process_output)
        if platform.system() == "Windows":
            self._process.setProcessEnvironment(self._get_hidden_window_environment())
        self._process.finished.connect(
            lambda ec, es: self._on_remove_env_finished(ec, es, env_name)
        )
        self._process.start(str(conda_exe), ["env", "remove", "--name", env_name, "-y"])

    def _on_remove_env_finished(self, exit_code, exit_status, env_name):
        try:
            if exit_code != 0:
                env_path = self.miniconda_path / "envs" / env_name
                if env_path.exists():
                    import time
                    time.sleep(1)
                    shutil.rmtree(env_path, ignore_errors=True)

            if env_name in self.meta:
                del self.meta[env_name]
            self._save_meta(self.meta)
            self._scan_envs()

            if self._current_log_callback:
                self._current_log_callback(f"环境 {env_name} 删除完成")
            self.remove_finished.emit("success")
        except Exception as e:
            self.remove_finished.emit(e)

    def _on_process_output(self):
        if self._process:
            data = self._process.readAllStandardOutput().data().decode("utf-8", errors="ignore")
            if data.strip() and self._current_log_callback:
                clean_data = self._clean_ansi_codes(data.strip())
                self._current_log_callback(clean_data)

    def list_envs(self):
        self._scan_envs()
        return list(self.meta.keys())

    def get_python_exe(self, env_name: str) -> Path:
        if env_name is None:
            return None
        env_path = self.miniconda_path / "envs" / env_name
        python_exe = env_path / "python.exe"
        if python_exe.exists():
            self.meta[env_name] = str(env_path)
            self._save_meta(self.meta)
            return python_exe
        if env_name == "miniconda":
            base_exe = self.miniconda_path / "python.exe"
            if base_exe.exists():
                return base_exe
        raise RuntimeError(f"环境 {env_name} 不存在于 {self.miniconda_path / 'envs'}")

    def _clean_ansi_codes(self, text):
        ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
        return ansi_escape.sub('', text)

    def ensure_pip(self, python_exe: str, log_callback=None) -> bool:
        proc = QProcess()
        if platform.system() == "Windows":
            proc.setProcessEnvironment(self._get_hidden_window_environment())
        proc.start(python_exe, ["-m", "pip", "--version"])
        proc.waitForFinished()
        if proc.exitCode() == 0:
            log_callback and log_callback("pip 已存在 ✅")
            return True
        else:
            log_callback and log_callback("pip 不存在，正在安装 ensurepip...")
            try:
                ensurepip_proc = QProcess()
                if platform.system() == "Windows":
                    ensurepip_proc.setProcessEnvironment(self._get_hidden_window_environment())
                ensurepip_proc.start(python_exe, ["-m", "ensurepip"])
                ensurepip_proc.waitForFinished()
                if ensurepip_proc.exitCode() == 0:
                    pip_upgrade_proc = QProcess()
                    if platform.system() == "Windows":
                        pip_upgrade_proc.setProcessEnvironment(self._get_hidden_window_environment())
                    pip_upgrade_proc.start(python_exe, ["-m", "pip", "install", "--upgrade", "pip"])
                    pip_upgrade_proc.waitForFinished()
                    if pip_upgrade_proc.exitCode() == 0:
                        log_callback and log_callback("pip 安装完成 ✅")
                        return True
                log_callback and log_callback("pip 安装失败")
                return False
            except Exception as e:
                log_callback and log_callback(f"安装 pip 失败: {e}")
                return False

    def _get_hidden_window_environment(self):
        from PyQt5.QtCore import QProcessEnvironment
        env = QProcessEnvironment.systemEnvironment()
        return env