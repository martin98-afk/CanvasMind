# -*- coding: utf-8 -*-
import json
import platform
import re
import shutil
import traceback
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from PyQt5.QtCore import QObject, pyqtSignal, QProcess, QTimer, QUrl, QByteArray
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from loguru import logger

from app.utils.config import Settings


class EnvironmentManager(QObject):
    """使用Miniconda管理Python环境 (修复ToS验证错误 + 增强安装稳定性)"""

    # 信号
    log_signal = pyqtSignal(str)
    install_finished = pyqtSignal(str)  # 传递结果或异常
    miniconda_install_finished = pyqtSignal(object)
    remove_finished = pyqtSignal(object)

    ENV_DIR = Path(__file__).parent.parent.parent / "envs"
    META_FILE = ENV_DIR / "environments.json"

    # --- 1. 定义 Miniconda 下载源 (优先清华/北外，解决下载慢/失败) ---
    MIRROR_TEMPLATES = [
        "https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py{py_ver}_{ver}-2-Windows-x86_64.exe",
        "https://mirrors.bfsu.edu.cn/anaconda/miniconda/Miniconda3-py{py_ver}_{ver}-2-Windows-x86_64.exe",
        "https://repo.anaconda.com/miniconda/Miniconda3-py{py_ver}_{ver}-2-Windows-x86_64.exe"
    ]

    # --- 2. 定义 Conda 频道源 (绕过 Anaconda ToS 验证的关键) ---
    # 使用这些镜像源替代默认的 'defaults'，即可避开 ToS 错误
    CONDA_CHANNELS = [
        "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main",
        "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free",
        "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/r",
        "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/msys2",
        "https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/pytorch"
    ]

    def __init__(self):
        super().__init__()
        self.config = Settings.get_instance()
        self.refresh_env_config()
        self.ENV_DIR.mkdir(exist_ok=True, parents=True)
        if not self.META_FILE.exists():
            self._save_meta({})

        self.miniconda_path = self.ENV_DIR / "miniconda"
        logger.info(f"检查Miniconda安装状态: {self.miniconda_path}")
        self.meta = self._load_meta()
        self._scan_envs()

        self._network_manager = QNetworkAccessManager(self)
        self._network_manager.finished.connect(self._on_download_finished)

        # 状态变量
        self._current_log_callback = None
        self._installer_path = None
        self._process = None
        self._pending_env_creation = None
        self._download_queue = []
        self._current_download_reply = None

    def refresh_env_config(self):
        self.DEFAULT_PACKAGES = self.config.default_packages.value
        self.miniconda_version = self.config.miniconda_version.value

    def _load_meta(self):
        try:
            return json.loads(self.META_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_meta(self, data):
        self.META_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _scan_envs(self):
        new_meta = {}
        miniconda_envs_dir = self.miniconda_path / "envs"
        if miniconda_envs_dir.exists():
            for d in miniconda_envs_dir.iterdir():
                if d.is_dir() and (d / "python.exe").exists():
                    new_meta[d.name] = str(d)
        self.meta = new_meta
        self._save_meta(self.meta)

    def _is_miniconda_installed(self):
        return (self.miniconda_path / "Scripts" / "conda.exe").exists()

    # ==========================
    # 下载与安装 Miniconda 核心逻辑
    # ==========================
    def install_miniconda(self, log_callback=None):
        """安装Miniconda（自动切换源 + 校验文件）"""
        if self._is_miniconda_installed():
            if log_callback: log_callback("Miniconda已安装")
            self.miniconda_install_finished.emit("success")
            return

        self._current_log_callback = log_callback

        # 推荐使用 Python 3.11 版本作为 Miniconda 基座，兼容性最好
        py_version_short = "311"

        self._download_queue = []
        for template in self.MIRROR_TEMPLATES:
            url = template.format(py_ver=py_version_short, ver=self.miniconda_version)
            self._download_queue.append(url)

        filename = self._download_queue[0].split("/")[-1]
        self._installer_path = self.ENV_DIR / filename

        # 检查本地是否有有效安装包
        if self._installer_path.exists():
            if self._validate_installer(self._installer_path):
                if log_callback: log_callback("检测到本地安装包有效，跳过下载")
                self._start_miniconda_install()
                return
            else:
                if log_callback: log_callback("本地安装包损坏，准备重新下载...")
                try:
                    self._installer_path.unlink()
                except:
                    pass

        self._try_next_download_source()

    def _try_next_download_source(self):
        if not self._download_queue:
            error_msg = "Miniconda下载失败：所有镜像源均不可用。"
            if self._current_log_callback: self._current_log_callback(error_msg)
            self.miniconda_install_finished.emit(RuntimeError(error_msg))
            return

        url = self._download_queue.pop(0)
        if self._current_log_callback:
            domain = urlparse(url).netloc
            self._current_log_callback(f"正在下载Miniconda (源: {domain})...")

        request = QNetworkRequest(QUrl(url))
        request.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        self._current_download_reply = self._network_manager.get(request)

    def _validate_installer(self, file_path: Path) -> bool:
        """校验安装包完整性 (防止下载了404页面导致安装失败)"""
        try:
            # 大小校验 (>30MB)
            if file_path.stat().st_size < 30 * 1024 * 1024:
                return False
            # 文件头校验 (MZ)
            with open(file_path, "rb") as f:
                if f.read(2) != b'MZ':
                    return False
            return True
        except Exception:
            return False

    def _on_download_finished(self, reply):
        if reply != self._current_download_reply:
            reply.deleteLater()
            return
        self._current_download_reply = None

        if reply.error() != QNetworkReply.NoError:
            logger.warning(f"下载失败: {reply.errorString()}")
            reply.deleteLater()
            self._try_next_download_source()
            return

        try:
            data = reply.readAll()
            with open(self._installer_path, "wb") as f:
                f.write(data)
            reply.deleteLater()

            if self._validate_installer(self._installer_path):
                if self._current_log_callback: self._current_log_callback("下载校验通过，开始安装...")
                self._start_miniconda_install()
            else:
                try:
                    self._installer_path.unlink()
                except:
                    pass
                self._try_next_download_source()
        except Exception as e:
            logger.error(f"Write error: {e}")
            self._try_next_download_source()

    def _start_miniconda_install(self):
        """修复 Exit Code 2：强制清理残留目录，使用正确参数"""
        if self.miniconda_path.exists():
            if self._current_log_callback: self._current_log_callback("清理旧的Miniconda残留...")
            try:
                # 重命名后删除，防止文件锁
                temp_trash = self.ENV_DIR / f"trash_{int(time.time())}"
                self.miniconda_path.rename(temp_trash)
                shutil.rmtree(temp_trash, ignore_errors=True)
            except Exception as e:
                # 尝试强制删除
                shutil.rmtree(self.miniconda_path, ignore_errors=True)

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.setWorkingDirectory(str(self.ENV_DIR))

        if platform.system() == "Windows":
            self._process.setProcessEnvironment(self._get_hidden_window_environment())

        self._process.readyReadStandardOutput.connect(self._on_process_output)
        self._process.finished.connect(self._on_miniconda_install_finished)

        # 注意路径分隔符
        install_path_str = str(self.miniconda_path).replace("/", "\\")

        args = [
            "/S",
            "/InstallationType=JustMe",
            "/AddToPath=0",
            "/RegisterPython=0",
            f"/D={install_path_str}"
        ]
        self._process.start(str(self._installer_path), args)

    def _on_miniconda_install_finished(self, exit_code, exit_status):
        conda_exe = self.miniconda_path / "Scripts" / "conda.exe"
        if exit_code == 0 and conda_exe.exists():
            if self._current_log_callback: self._current_log_callback("Miniconda安装成功！")
            if self._installer_path and self._installer_path.exists():
                try:
                    self._installer_path.unlink()
                except:
                    pass

            # 安装成功后，初始化 .condarc 以确保全局使用镜像源 (双重保险)
            self._init_condarc()

            self._scan_envs()
            self.miniconda_install_finished.emit("success")

            if self._pending_env_creation:
                version, env_name, log_cb = self._pending_env_creation
                self._pending_env_creation = None
                QTimer.singleShot(1000, lambda: self._create_env_with_qprocess(version, env_name, log_cb))
        else:
            err = f"Miniconda安装失败 (Code: {exit_code})。请检查杀毒软件或目录权限。"
            if exit_code == 2:
                # Exit Code 2 通常意味着文件损坏，自动清理以便重试
                if self._installer_path.exists():
                    self._installer_path.unlink()
                err += " (已自动清理损坏的安装包，请重试)"

            if self._current_log_callback: self._current_log_callback(err)
            self.miniconda_install_finished.emit(RuntimeError(err))

    def _init_condarc(self):
        """(可选) 初始化 .condarc 文件，配置清华源"""
        try:
            condarc_path = Path.home() / ".condarc"
            # 只有当文件不存在时才创建，避免覆盖用户配置
            # 或者你可以选择强制覆盖
            content = (
                "channels:\n"
                "  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/\n"
                "  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free/\n"
                "  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/pytorch/\n"
                "show_channel_urls: true\n"
                "ssl_verify: true\n"
            )
            # condarc_path.write_text(content, encoding='utf-8')
            # 暂时注释掉，通过命令行参数控制更安全，不污染用户全局配置
            pass
        except Exception:
            pass

    # ==========================
    # 创建环境 (ToS 修复核心)
    # ==========================
    def download_and_install(self, version, env_name=None, log_callback=None):
        if not self._is_miniconda_installed():
            if log_callback: log_callback("Miniconda缺失，正在初始化...")
            self._pending_env_creation = (version, env_name, log_callback)
            self.install_miniconda(log_callback)
            return
        self._create_env_with_qprocess(version, env_name, log_callback)

    def _create_env_with_qprocess(self, version, env_name=None, log_callback=None):
        """创建环境 - 显式指定镜像源以绕过 ToS"""
        if env_name is None: env_name = version
        if env_name in self.list_envs():
            if log_callback: log_callback(f"环境 {env_name} 已存在")
            self.install_finished.emit(str(self.get_python_exe(env_name).parent))
            return

        if log_callback: log_callback(f"正在创建环境 {env_name} (Py{version})...")
        self._current_log_callback = log_callback

        conda_exe = self.miniconda_path / "Scripts" / "conda.exe"

        # --- 关键修改：添加镜像源参数 ---
        args = ["create", "--name", env_name, f"python={version}", "-y"]

        # 添加镜像源
        for channel in self.CONDA_CHANNELS:
            args.extend(["-c", channel])

        # 强制覆盖频道配置（必须！否则 conda 仍会尝试连接 defaults）
        args.append("--override-channels")

        self._start_conda_process(conda_exe, args, lambda ec, es: self._on_create_env_finished(ec, es, env_name))

    def _start_conda_process(self, exe, args, finished_slot):
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_process_output)
        if platform.system() == "Windows":
            self._process.setProcessEnvironment(self._get_hidden_window_environment())
        self._process.finished.connect(finished_slot)

        # 记录一下执行的命令，方便调试
        cmd_log = f"{exe} {' '.join(args)}"
        logger.debug(f"Executing: {cmd_log}")

        self._process.start(str(exe), args)

    def _on_create_env_finished(self, exit_code, exit_status, env_name):
        if exit_code != 0:
            error_msg = f"环境创建失败 (Code {exit_code})。请检查网络或配置。"
            # 如果是 ToS 错误，提示信息会包含在输出中
            if self._current_log_callback: self._current_log_callback(error_msg)
            self.install_finished.emit(error_msg)
            return

        # 验证环境健康 (防止空文件夹)
        is_healthy, msg = self._validate_env_health(env_name)
        if not is_healthy:
            self.remove_env(env_name)
            error_msg = f"环境自检失败 ({msg})，已回滚。"
            if self._current_log_callback: self._current_log_callback(error_msg)
            self.install_finished.emit(error_msg)
            return

        python_exe = self.get_python_exe(env_name)
        self.meta[env_name] = str(python_exe.parent)
        self._save_meta(self.meta)
        self._scan_envs()

        if self._current_log_callback: self._current_log_callback(f"环境 {env_name} 创建成功 ✅")
        QTimer.singleShot(1000, lambda: self._install_default_packages(env_name, python_exe))

    def _validate_env_health(self, env_name):
        """简单验证 Python 是否能运行"""
        python_exe = self.get_python_exe(env_name)
        if not python_exe.exists(): return False, "Executable missing"

        proc = QProcess()
        env = self._get_hidden_window_environment()
        env.remove("PYTHONPATH")
        proc.setProcessEnvironment(env)
        proc.start(str(python_exe), ["-c", "print('ok')"])
        proc.waitForFinished(5000)
        return (proc.exitCode() == 0), "Runtime check failed"

    # ==========================
    # 其他辅助方法 (克隆、删除、包管理)
    # ==========================
    def clone_env(self, source_env, target_env, log_callback=None):
        if target_env in self.list_envs(): return
        if log_callback: log_callback(f"正在克隆 {source_env} -> {target_env}...")
        self._current_log_callback = log_callback

        conda_exe = self.miniconda_path / "Scripts" / "conda.exe"

        # 克隆时同样加入 override，防止解析依赖时去连 defaults
        args = ["create", "--name", target_env, "--clone", source_env, "-y"]
        for channel in self.CONDA_CHANNELS:
            args.extend(["-c", channel])
        args.append("--override-channels")

        self._start_conda_process(conda_exe, args, lambda ec, es: self._on_clone_finished(ec, es, target_env))

    def _on_clone_finished(self, ec, es, env_name):
        if ec == 0:
            self.meta[env_name] = str(self.miniconda_path / "envs" / env_name)
            self._save_meta(self.meta)
            self._scan_envs()
            if self._current_log_callback: self._current_log_callback(f"克隆完成 ✅")
            self.install_finished.emit("success")
        else:
            self.install_finished.emit(f"克隆失败 Code {ec}")

    def remove_env(self, env_name, log_callback=None):
        if log_callback: self._current_log_callback = log_callback
        conda_exe = self.miniconda_path / "Scripts" / "conda.exe"
        # 删除不需要联网，所以不需要镜像源参数
        self._start_conda_process(conda_exe, ["env", "remove", "--name", env_name, "-y"],
                                  lambda ec, es: self._on_remove_finished_wrapper(env_name))

    def _on_remove_finished_wrapper(self, env_name):
        env_path = self.miniconda_path / "envs" / env_name
        if env_path.exists():
            try:
                shutil.rmtree(env_path, ignore_errors=True)
            except:
                pass

        if env_name in self.meta: del self.meta[env_name]
        self._save_meta(self.meta)
        self._scan_envs()
        if self._current_log_callback: self._current_log_callback(f"环境已删除")
        self.remove_finished.emit("success")

    def _on_process_output(self):
        if self._process:
            data = self._process.readAllStandardOutput()
            try:
                text = data.data().decode("gbk")
            except:
                text = data.data().decode("utf-8", errors="ignore")
            if text.strip() and self._current_log_callback:
                self._current_log_callback(self._clean_ansi_codes(text.strip()))

    def _install_default_packages(self, env_name, python_exe):
        self._install_next_package(python_exe, list(self.DEFAULT_PACKAGES))

    def _install_next_package(self, python_exe, remaining):
        if not remaining:
            if self._current_log_callback: self._current_log_callback("默认包安装完成 ✅")
            self.install_finished.emit("success")
            return

        pkg = remaining[0]
        if self._current_log_callback: self._current_log_callback(f"安装包: {pkg}...")

        # PIP 安装同样需要使用镜像
        cmd = ["-m", "pip", "install", pkg]
        mirrors = self.config.mirrors.value
        if mirrors:
            for m in mirrors:
                cmd.extend(["--extra-index-url", m, "--trusted-host", urlparse(m).hostname])

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_process_output)
        if platform.system() == "Windows":
            self._process.setProcessEnvironment(self._get_hidden_window_environment())
        self._process.finished.connect(lambda ec, es: self._install_next_package(python_exe, remaining[1:]))
        self._process.start(str(python_exe), cmd)

    def ensure_pip(self, python_exe: str, log_callback=None) -> bool:
        # 简单检查 pip
        proc = QProcess()
        if platform.system() == "Windows":
            proc.setProcessEnvironment(self._get_hidden_window_environment())
        proc.start(str(python_exe), ["-m", "pip", "--version"])
        proc.waitForFinished()
        return proc.exitCode() == 0

    def list_envs(self):
        self._scan_envs()
        return list(self.meta.keys())

    def get_python_exe(self, env_name):
        if env_name is None:
            return None
        if env_name in self.meta:
            return Path(self.meta[env_name]) / "python.exe"
        p = self.miniconda_path / "envs" / env_name / "python.exe"
        if p.exists():
            return p
        if env_name == "miniconda":
            return self.miniconda_path / "python.exe"
        return Path("non_existent")

    def _clean_ansi_codes(self, text):
        return re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])').sub('', text)

    def _get_hidden_window_environment(self):
        from PyQt5.QtCore import QProcessEnvironment
        env = QProcessEnvironment.systemEnvironment()
        env.insert("CONDA_ALWAYS_YES", "true")  # 确保非交互
        if not env.contains("SystemRoot"):
            env.insert("SystemRoot", os.environ.get("SystemRoot", "C:\\Windows"))
        return env
