import json
import re
import shutil
from pathlib import Path
from urllib.request import urlopen
from PyQt5.QtCore import QObject, pyqtSignal, QProcess, QTimer


class EnvironmentManager(QObject):
    """使用Miniconda管理Python环境"""

    # 信号
    log_signal = pyqtSignal(str)
    install_finished = pyqtSignal(object)  # 传递结果或异常
    miniconda_install_finished = pyqtSignal(object)
    remove_finished = pyqtSignal(object)

    ENV_DIR = Path(__file__).parent.parent.parent / "envs"
    META_FILE = ENV_DIR / "environments.json"

    # Miniconda安装包下载链接
    MINICONDA_URLS = {
        "3.9": "https://repo.anaconda.com/miniconda/Miniconda3-py39_23.11.0-2-Windows-x86_64.exe",
        "3.10": "https://repo.anaconda.com/miniconda/Miniconda3-py310_23.11.0-2-Windows-x86_64.exe",
        "3.11": "https://repo.anaconda.com/miniconda/Miniconda3-py311_23.11.0-2-Windows-x86_64.exe",
    }

    # 默认要安装的包列表
    DEFAULT_PACKAGES = ["loguru", "pydantic", "pandas"]

    def __init__(self):
        super().__init__()
        self.ENV_DIR.mkdir(exist_ok=True)
        if not self.META_FILE.exists():
            self._save_meta({})
        # 检查是否已安装Miniconda
        self.miniconda_path = self.ENV_DIR / "miniconda"
        self.meta = self._load_meta()
        self._scan_envs()

        # QProcess实例
        self.process = None
        self.current_operation = None
        self.current_log_callback = None
        self.installer_path = None
        self.current_env_name = None  # 记录当前正在操作的环境名

    def _load_meta(self):
        try:
            return json.loads(self.META_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_meta(self, data):
        self.META_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _scan_envs(self):
        """扫描 envs/ 下的环境"""
        # 清理旧 meta 中不存在的项
        new_meta = {}
        for d in self.ENV_DIR.iterdir():
            if d.is_dir() and (d / "python.exe").exists():
                new_meta[d.name] = str(d)
        # 扫描Miniconda环境目录
        miniconda_envs_dir = self.ENV_DIR / "miniconda" / "envs"
        if miniconda_envs_dir.exists():
            for d in miniconda_envs_dir.iterdir():
                if d.is_dir() and (d / "python.exe").exists():
                    new_meta[d.name] = str(d)
        # 保留已经记录但在 envs 以外手动加入的（兼容之前的 meta）
        for k, v in self.meta.items():
            if k not in new_meta and Path(v).exists() and (Path(v) / "python.exe").exists():
                new_meta[k] = v
        self.meta = new_meta
        self._save_meta(self.meta)

    def _is_miniconda_installed(self):
        """检查Miniconda是否已安装"""
        return (self.miniconda_path / "Scripts" / "conda.exe").exists()

    def install_miniconda(self, log_callback=None):
        """安装Miniconda（使用QProcess）"""
        if self._is_miniconda_installed():
            if log_callback:
                log_callback("Miniconda已安装")
            self.miniconda_install_finished.emit("success")
            return

        if log_callback:
            log_callback("正在安装Miniconda...")

        self.current_log_callback = log_callback
        self.current_operation = "install_miniconda"

        # 下载Miniconda安装包
        url = self.MINICONDA_URLS["3.11"]  # 默认安装Python 3.11版本
        self.installer_path = self.ENV_DIR / "miniconda_installer.exe"

        try:
            if log_callback:
                log_callback(f"下载Miniconda安装包...")
            with urlopen(url) as resp, open(self.installer_path, "wb") as f:
                f.write(resp.read())

            if log_callback:
                log_callback("开始安装Miniconda...")

            # 静默安装Miniconda
            self.process = QProcess(self)
            self.process.setProcessChannelMode(QProcess.MergedChannels)
            self.process.readyReadStandardOutput.connect(self._on_process_output)
            self.process.finished.connect(self._on_miniconda_install_finished)

            # 启动安装进程
            self.process.start(str(self.installer_path), [
                "/S",  # 静默安装
                f"/D={str(self.miniconda_path)}"  # 指定安装路径
            ])

        except Exception as e:
            if log_callback:
                log_callback(f"Miniconda安装失败: {e}")
            self.miniconda_install_finished.emit(e)

    def _on_miniconda_install_finished(self, exit_code, exit_status):
        """Miniconda安装完成回调"""
        try:
            # 验证安装
            conda_exe = self.miniconda_path / "Scripts" / "conda.exe"
            if not conda_exe.exists():
                error_msg = "Miniconda安装失败"
                if self.current_log_callback:
                    self.current_log_callback(error_msg)
                self.miniconda_install_finished.emit(RuntimeError(error_msg))
                return

            if self.current_log_callback:
                self.current_log_callback("Miniconda安装完成")

            # 清理安装包
            if self.installer_path and self.installer_path.exists():
                self.installer_path.unlink()

            # 重新扫描环境以更新meta文件
            self._scan_envs()

            self.miniconda_install_finished.emit("success")
        except Exception as e:
            self.miniconda_install_finished.emit(e)

    def download_and_install(self, version, log_callback=None):
        """创建指定版本的Python环境（使用QProcess）"""
        if not self._is_miniconda_installed():
            if log_callback:
                log_callback("Miniconda未安装，正在安装...")
            # 先安装Miniconda
            self.install_miniconda(log_callback)
            # 安装完成后延迟执行环境创建
            QTimer.singleShot(3000, lambda: self._create_env_after_miniconda(version, log_callback))
            return

        self._create_env_with_qprocess(version, log_callback)

    def _create_env_after_miniconda(self, version, log_callback):
        """Miniconda安装后创建环境"""
        if self._is_miniconda_installed():
            self._create_env_with_qprocess(version, log_callback)
        else:
            if log_callback:
                log_callback("Miniconda安装失败，无法创建环境")
            self.install_finished.emit(RuntimeError("Miniconda安装失败"))

    def _create_env_with_qprocess(self, version, log_callback=None):
        """使用QProcess创建环境"""
        # 提取主要版本号
        major_version = version.split('.')[0] + '.' + version.split('.')[1]
        if major_version not in ["3.9", "3.10", "3.11"]:
            # 如果不是支持的版本，使用最接近的版本
            major_version = "3.11"

        env_name = version  # 使用完整版本号作为环境名

        # 检查环境是否已存在
        existing_envs = self.list_envs()
        if env_name in existing_envs:
            if log_callback:
                log_callback(f"环境 {env_name} 已存在")
            # 获取环境路径并更新元数据
            python_exe = self.get_python_exe(env_name)
            env_path = python_exe.parent
            self.meta[env_name] = str(env_path)
            self._save_meta(self.meta)
            self.install_finished.emit(env_path)
            return

        if log_callback:
            log_callback(f"正在创建Python {version}环境...")

        self.current_log_callback = log_callback
        self.current_operation = "create_env"
        self.current_env_name = env_name  # 记录当前环境名

        conda_exe = self.miniconda_path / "Scripts" / "conda.exe"

        # 创建新环境
        cmd = [
            str(conda_exe),
            "create",
            "--name", env_name,
            f"python={version}",
            "-y"  # 自动确认
        ]

        if log_callback:
            log_callback(f"执行命令: {' '.join(cmd)}")

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_process_output)
        self.process.finished.connect(
            lambda exit_code, exit_status:
            self._on_create_env_finished(exit_code, exit_status, env_name)
        )

        # 启动conda进程
        self.process.start(str(conda_exe), [
            "create",
            "--name", env_name,
            f"python={version}",
            "-y"
        ])

    def _on_create_env_finished(self, exit_code, exit_status, env_name):
        """环境创建完成回调"""
        try:
            if exit_code != 0:
                error_msg = f"环境 {env_name} 创建失败，退出码: {exit_code}"
                if self.current_log_callback:
                    self.current_log_callback(error_msg)
                self.install_finished.emit(RuntimeError(error_msg))
                return

            # 验证环境是否创建成功
            python_exe = self.get_python_exe(env_name)
            if not python_exe.exists():
                error_msg = f"环境 {env_name} 创建失败，未找到 python.exe"
                if self.current_log_callback:
                    self.current_log_callback(error_msg)
                self.install_finished.emit(RuntimeError(error_msg))
                return

            # 更新元数据 - 使用conda获取的正确路径
            env_path = python_exe.parent
            self.meta[env_name] = str(env_path)
            self._save_meta(self.meta)
            # 重新扫描环境以确保meta文件是最新的
            self._scan_envs()
            if self.current_log_callback:
                self.current_log_callback(f"Python {env_name} 环境创建完成 ✅")

            # 安装默认包
            QTimer.singleShot(1000, lambda: self._install_default_packages(env_name, python_exe))

        except Exception as e:
            self.install_finished.emit(e)

    def _install_default_packages(self, env_name, python_exe):
        """安装默认包"""
        if self.current_log_callback:
            self.current_log_callback(f"正在安装默认包: {', '.join(self.DEFAULT_PACKAGES)}")

        self.current_operation = "install_default_packages"
        self.current_env_name = env_name

        # 使用QProcess安装每个包
        self._install_next_package(python_exe, self.DEFAULT_PACKAGES[:])

    def _install_next_package(self, python_exe, remaining_packages):
        """递归安装下一个包"""
        if not remaining_packages:
            # 所有包都安装完成
            if self.current_log_callback:
                self.current_log_callback("默认包安装完成 ✅")
            self.install_finished.emit(self.meta.get(self.current_env_name))
            return

        package = remaining_packages[0]
        remaining = remaining_packages[1:]

        if self.current_log_callback:
            self.current_log_callback(f"正在安装 {package}...")

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_process_output)
        self.process.finished.connect(lambda exit_code, exit_status:
                                    self._on_package_installed(exit_code, exit_status, python_exe, remaining))

        # 启动pip安装进程
        self.process.start(str(python_exe), ["-m", "pip", "install", package])

    def _on_package_installed(self, exit_code, exit_status, python_exe, remaining_packages):
        """包安装完成回调"""
        if exit_code != 0:
            if self.current_log_callback:
                self.current_log_callback(f"包安装失败，继续安装下一个包")
        else:
            if self.current_log_callback:
                self.current_log_callback("✅ 包安装完成")

        # 安装下一个包
        QTimer.singleShot(500, lambda: self._install_next_package(python_exe, remaining_packages))

    def remove_env(self, env_name, log_callback=None):
        """删除指定环境（使用QProcess）"""
        if env_name not in self.meta and env_name not in self.list_envs():
            error_msg = f"环境 {env_name} 不存在"
            if log_callback:
                log_callback(error_msg)
            self.remove_finished.emit(RuntimeError(error_msg))
            return

        if log_callback:
            log_callback(f"正在删除环境 {env_name}...")

        self.current_log_callback = log_callback
        self.current_operation = "remove_env"

        conda_exe = self.miniconda_path / "Scripts" / "conda.exe"

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_process_output)
        self.process.finished.connect(lambda exit_code, exit_status:
                                      self._on_remove_env_finished(exit_code, exit_status, env_name))

        # 启动删除环境进程
        self.process.start(str(conda_exe), [
            "env", "remove",
            "--name", env_name,
            "-y"  # 自动确认
        ])

    def _on_remove_env_finished(self, exit_code, exit_status, env_name):
        """环境删除完成回调"""
        try:
            if exit_code != 0:
                # 如果conda删除失败，尝试手动删除
                env_path = self.miniconda_path / "envs" / env_name
                if env_path.exists():
                    import time
                    time.sleep(1)
                    shutil.rmtree(env_path, ignore_errors=True)

            # 从元数据中移除
            if env_name in self.meta:
                del self.meta[env_name]
            self._save_meta(self.meta)

            # 重新扫描环境
            self._scan_envs()

            if self.current_log_callback:
                self.current_log_callback(f"环境 {env_name} 删除完成")

            self.remove_finished.emit("success")
        except Exception as e:
            self.remove_finished.emit(e)

    def _on_process_output(self):
        """处理进程输出"""
        if self.process:
            data = self.process.readAllStandardOutput().data().decode("utf-8", errors="ignore")
            if data and self.current_log_callback:
                self.current_log_callback(data.strip())

    def list_envs(self):
        """列出所有环境"""
        # 重新扫描环境以确保获取最新数据
        self._scan_envs()
        return list(self.meta.keys())

    def get_python_exe(self, env_name: str) -> Path:
        """获取指定环境的Python解释器路径"""
        # 检查是否是已知环境
        if env_name in self.meta:
            path = Path(self.meta[env_name])
            exe_path = path / "python.exe"
            if exe_path.exists():
                return exe_path

        # 通过conda获取环境路径 - Miniconda环境在envs子目录下
        try:
            conda_exe = self.miniconda_path / "Scripts" / "conda.exe"
            process = QProcess()
            process.start(str(conda_exe), ["info", "--envs", "--json"])
            process.waitForFinished()

            output = process.readAllStandardOutput().data().decode("utf-8")
            # 清理ANSI颜色代码
            output = self._clean_ansi_codes(output)
            envs_info = json.loads(output)
            for env_path in envs_info.get("envs", []):
                if Path(env_path).name == env_name:
                    exe_path = Path(env_path) / "python.exe"
                    if exe_path.exists():
                        # 更新元数据缓存
                        self.meta[env_name] = str(Path(env_path))
                        self._save_meta(self.meta)
                        return exe_path
        except Exception as e:
            if self.current_log_callback:
                self.current_log_callback(f"获取环境路径失败: {e}")
            pass

        raise RuntimeError(f"环境 {env_name} 不存在或缺少 python.exe")

    def _clean_ansi_codes(self, text):
        """清理ANSI颜色代码"""
        ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
        return ansi_escape.sub('', text)

    def ensure_pip(self, python_exe: str, log_callback=None) -> bool:
        """确保指定 Python 环境中有 pip"""
        # 检查pip是否存在
        process = QProcess()
        process.start(python_exe, ["-m", "pip", "--version"])
        process.waitForFinished()

        if process.exitCode() == 0:
            if log_callback:
                log_callback("pip 已存在 ✅")
            return True
        else:
            if log_callback:
                log_callback("pip 不存在，正在安装 ensurepip...")
            try:
                # 安装pip
                ensurepip_process = QProcess()
                ensurepip_process.start(python_exe, ["-m", "ensurepip"])
                ensurepip_process.waitForFinished()

                if ensurepip_process.exitCode() == 0:
                    # 升级pip
                    pip_upgrade_process = QProcess()
                    pip_upgrade_process.start(python_exe, ["-m", "pip", "install", "--upgrade", "pip"])
                    pip_upgrade_process.waitForFinished()

                    if pip_upgrade_process.exitCode() == 0:
                        if log_callback:
                            log_callback("pip 安装完成 ✅")
                        return True
                    else:
                        if log_callback:
                            log_callback(f"pip 升级失败")
                        return False
                else:
                    if log_callback:
                        log_callback(f"ensurepip 安装失败")
                    return False
            except Exception as e:
                if log_callback:
                    log_callback(f"安装 pip 失败: {e}")
                return False