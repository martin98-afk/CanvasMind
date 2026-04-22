# -*- coding: utf-8 -*-
import json
import os
import platform
import re
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from PyQt5.QtCore import QObject, pyqtSignal, QProcess, QTimer, QUrl
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

    @property
    def ENV_DIR(self):
        """获取 envs 目录路径，确保在用户可写的位置"""
        return Path(__file__).parent.parent.parent / "envs"

    @property
    def META_FILE(self):
        return self.ENV_DIR / "environments.json"

    # --- 1. 定义 Miniconda 下载源 (优先清华/北外，解决下载慢/失败) ---
    # 模板会在运行时按平台生成

    # --- 2. 定义 Conda 频道源 (绕过 Anaconda ToS 验证的关键) ---
    # 使用这些镜像源替代默认的 'defaults'，即可避开 ToS 错误
    CONDA_CHANNELS = [
        "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main",
        "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free",
        "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/r",
        "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/msys2",
        "https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/pytorch",
    ]

    def __init__(self):
        super().__init__()
        # 平台信息（先初始化，避免后续方法访问未定义）
        self._system = platform.system()
        self._is_windows = self._system == "Windows"
        self._is_macos = self._system == "Darwin"
        self._is_linux = self._system == "Linux"

        self.config = Settings.get_instance()
        self.refresh_env_config()
        self.ENV_DIR.mkdir(exist_ok=True, parents=True)
        if not self.META_FILE.exists():
            self._save_meta({})

        self.miniconda_path = self.ENV_DIR / "miniconda" if (self.ENV_DIR / "miniconda").exists() else self._find_system_miniconda()
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

    # ==========================
    # 平台与路径辅助
    # ==========================
    def _get_python_exe_name(self):
        return "python.exe" if self._is_windows else "python"

    def _get_conda_exe_path(self):
        return (
            self.miniconda_path / "Scripts" / "conda.exe"
            if self._is_windows
            else self.miniconda_path / "bin" / "conda"
        )

    def _env_python_from_env_dir(self, env_dir: Path):
        if self._is_windows:
            return env_dir / "python.exe"
        return env_dir / "bin" / "python"

    def _get_mirror_templates(self):
        """按平台生成 Miniconda 下载模板"""
        if self._is_windows:
            suffix = "Windows-x86_64.exe"
        elif self._is_macos:
            arch = (
                "arm64"
                if platform.machine().lower() in ("arm64", "aarch64")
                else "x86_64"
            )
            suffix = f"MacOSX-{arch}.sh"
        else:
            suffix = "Linux-x86_64.sh"

        return [
            f"https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py{{py_ver}}_{{ver}}{{build}}-{suffix}",
            f"https://mirrors.bfsu.edu.cn/anaconda/miniconda/Miniconda3-py{{py_ver}}_{{ver}}{{build}}-{suffix}",
            f"https://repo.anaconda.com/miniconda/Miniconda3-py{{py_ver}}_{{ver}}{{build}}-{suffix}",
        ]

    def refresh_env_config(self):
        self.DEFAULT_PACKAGES = self.config.default_packages.value
        self.miniconda_version = self.config.miniconda_version.value

    def _load_meta(self):
        try:
            return json.loads(self.META_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_meta(self, data):
        self.META_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _scan_envs(self):
        new_meta = {}
        if self.miniconda_path is None:
            return
        miniconda_envs_dir = self.miniconda_path / "envs"
        if miniconda_envs_dir.exists():
            for d in miniconda_envs_dir.iterdir():
                if d.is_dir() and self._env_python_from_env_dir(d).exists():
                    new_meta[d.name] = str(d)
        # 合并已有 meta（新扫到的 + 之前保存但当前未检测到的）
        for name, path in self.meta.items():
            if name not in new_meta:
                p = Path(path)
                if p.exists() and self._env_python_from_env_dir(p).exists():
                    new_meta[name] = path
        self.meta = new_meta
        self._save_meta(self.meta)

    def _find_system_miniconda(self):
        """搜索系统中已安装的 Miniconda"""
        search_paths = [
            Path.home() / "miniconda3",
            Path.home() / "AppData" / "Local" / "miniconda3",
            Path("C:/miniconda3"),
            Path("C:/ProgramData/miniconda3"),
        ]

        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            search_paths.append(Path(f"{letter}:/miniconda3"))
            search_paths.append(Path(f"{letter}:/ProgramData/miniconda3"))

        for path in search_paths:
            if path.exists():
                conda_exe = (
                    path / "Scripts" / "conda.exe"
                    if self._is_windows
                    else path / "bin" / "conda"
                )
                if conda_exe.exists():
                    logger.info(f"发现系统Miniconda: {path}")
                    return path
        return None

    def _is_miniconda_installed(self):
        if self._get_conda_exe_path().exists():
            return True
        system_miniconda = self._find_system_miniconda()
        if system_miniconda:
            self.miniconda_path = system_miniconda
            return True
        return False

    # ==========================
    # 下载与安装 Miniconda 核心逻辑
    # ==========================
    def install_miniconda(self, log_callback=None):
        """安装Miniconda（自动切换源 + 校验文件）"""
        if self._is_miniconda_installed():
            if log_callback:
                log_callback("Miniconda已安装")
            self.miniconda_install_finished.emit("success")
            return

        self._current_log_callback = log_callback

        # 推荐使用 Python 3.11 版本作为 Miniconda 基座，兼容性最好
        py_version_short = "311"

        self._download_queue = []
        templates = self._get_mirror_templates()
        for template in templates:
            for build in ["-2", "-1", "-0"]:
                url = template.format(
                    py_ver=py_version_short, ver=self.miniconda_version, build=build
                )
                self._download_queue.append(url)

        filename = self._download_queue[0].split("/")[-1]
        self._installer_path = self.ENV_DIR / filename

        # 检查本地是否有有效安装包
        if self._installer_path.exists():
            if self._validate_installer(self._installer_path):
                if log_callback:
                    log_callback("检测到本地安装包有效，跳过下载")
                self._start_miniconda_install()
                return
            else:
                if log_callback:
                    log_callback("本地安装包损坏，准备重新下载...")
                try:
                    self._installer_path.unlink()
                except:
                    pass

        self._try_next_download_source()

    def _try_next_download_source(self):
        if not self._download_queue:
            error_msg = "Miniconda下载失败：所有镜像源均不可用。"
            if self._current_log_callback:
                self._current_log_callback(error_msg)
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
            # 大小校验 (>5MB)
            if file_path.stat().st_size < 5 * 1024 * 1024:
                return False
            # 文件头校验 (Windows exe 为 MZ，mac/linux 为脚本)
            with open(file_path, "rb") as f:
                header = f.read(2)
                if file_path.suffix.lower() == ".exe" and header != b"MZ":
                    return False
                if file_path.suffix.lower() == ".sh" and header != b"#!":
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
                if self._current_log_callback:
                    self._current_log_callback("下载校验通过，开始安装...")
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

    def _start_miniconda_install(self, silent=True):
        """安装 Miniconda

        Args:
            silent: True 静默安装，False 非静默安装（交互式）
        """
        if self.miniconda_path.exists():
            if self._current_log_callback:
                self._current_log_callback("清理旧的Miniconda残留...")
            try:
                temp_trash = self.ENV_DIR / f"trash_{int(time.time())}"
                self.miniconda_path.rename(temp_trash)
                shutil.rmtree(temp_trash, ignore_errors=True)
            except Exception as e:
                shutil.rmtree(self.miniconda_path, ignore_errors=True)

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.setWorkingDirectory(str(self.ENV_DIR))
        self._silent_install = silent

        if self._is_windows:
            self._process.setProcessEnvironment(self._get_process_environment())

        self._process.readyReadStandardOutput.connect(self._on_process_output)
        self._process.finished.connect(self._on_miniconda_install_finished)

        if self._is_windows:
            install_path_str = str(self.miniconda_path).replace("/", "\\")
            if silent:
                args = [
                    "/S",
                    "/InstallationType=JustMe",
                    "/AddToPath=0",
                    "/RegisterPython=0",
                    f"/D={install_path_str}",
                ]
            else:
                args = [
                    "/InstallationType=JustMe",
                    "/AddToPath=0",
                    "/RegisterPython=0",
                    f"/D={install_path_str}",
                ]
            self._process.start(str(self._installer_path), args)
        else:
            if silent:
                args = [str(self._installer_path), "-b", "-p", str(self.miniconda_path)]
            else:
                args = [str(self._installer_path), "-p", str(self.miniconda_path)]
            self._process.start("/bin/bash", args)

    def _on_miniconda_install_finished(self, exit_code, exit_status):
        conda_exe = self._get_conda_exe_path()
        if exit_code == 0 and conda_exe.exists():
            if self._current_log_callback:
                self._current_log_callback("Miniconda安装成功！")
            if self._installer_path and self._installer_path.exists():
                try:
                    self._installer_path.unlink()
                except:
                    pass

            self._init_condarc()

            self._scan_envs()
            self.miniconda_install_finished.emit("success")

            if self._pending_env_creation:
                version, env_name, log_cb = self._pending_env_creation
                self._pending_env_creation = None
                QTimer.singleShot(
                    1000,
                    lambda: self._create_env_with_qprocess(version, env_name, log_cb),
                )
        elif exit_code == 0:
            system_miniconda = self._find_system_miniconda()
            if system_miniconda:
                self.miniconda_path = system_miniconda
                if self._current_log_callback:
                    self._current_log_callback(
                        f"检测到系统Miniconda: {system_miniconda}"
                    )
                self._scan_envs()
                self.miniconda_install_finished.emit("success")
                if self._pending_env_creation:
                    version, env_name, log_cb = self._pending_env_creation
                    self._pending_env_creation = None
                    QTimer.singleShot(
                        1000,
                        lambda: self._create_env_with_qprocess(
                            version, env_name, log_cb
                        ),
                    )
                return
        else:
            silent_failed = getattr(self, "_silent_install", True)

            if silent_failed and self._installer_path and self._installer_path.exists():
                err = (
                    f"Miniconda静默安装失败 (Code: {exit_code})，正在尝试交互式安装..."
                )
                if self._current_log_callback:
                    self._current_log_callback(err)
                QTimer.singleShot(
                    500, lambda: self._start_miniconda_install(silent=False)
                )
                return

            err = f"Miniconda安装失败 (Code: {exit_code})。请检查杀毒软件或目录权限。"
            if exit_code == 2:
                if self._installer_path.exists():
                    self._installer_path.unlink()
                err += " (已自动清理损坏的安装包，请重试)"

            if self._current_log_callback:
                self._current_log_callback(err)
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
            if log_callback:
                log_callback("Miniconda缺失，正在初始化...")
            self._pending_env_creation = (version, env_name, log_callback)
            self.install_miniconda(log_callback)
            return
        self._create_env_with_qprocess(version, env_name, log_callback)

    def _create_env_with_qprocess(self, version, env_name=None, log_callback=None):
        """创建环境 - 显式指定镜像源以绕过 ToS"""
        if env_name is None:
            env_name = version
        if env_name in self.list_envs():
            if log_callback:
                log_callback(f"环境 {env_name} 已存在")
            env_path = self.miniconda_path / "envs" / env_name
            self.install_finished.emit(str(env_path))
            return

        if log_callback:
            log_callback(f"正在创建环境 {env_name} (Py{version})...")
        self._current_log_callback = log_callback

        conda_exe = self._get_conda_exe_path()

        # --- 关键修改：添加镜像源参数 ---
        args = ["create", "--name", env_name, f"python={version}", "-y"]

        # 添加镜像源
        for channel in self.CONDA_CHANNELS:
            args.extend(["-c", channel])

        # 强制覆盖频道配置（必须！否则 conda 仍会尝试连接 defaults）
        args.append("--override-channels")

        self._start_conda_process(
            conda_exe,
            args,
            lambda ec, es: self._on_create_env_finished(ec, es, env_name),
        )

    def _start_conda_process(self, exe, args, finished_slot):
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_process_output)
        if self._is_windows:
            self._process.setProcessEnvironment(self._get_process_environment())
        self._process.finished.connect(finished_slot)

        # 记录一下执行的命令，方便调试
        cmd_log = f"{exe} {' '.join(args)}"
        logger.debug(f"Executing: {cmd_log}")

        self._process.start(str(exe), args)

    def _on_create_env_finished(self, exit_code, exit_status, env_name):
        if exit_code != 0:
            error_msg = f"环境创建失败 (Code {exit_code})。请检查网络或配置。"
            # 如果是 ToS 错误，提示信息会包含在输出中
            if self._current_log_callback:
                self._current_log_callback(error_msg)
            self.install_finished.emit(error_msg)
            return

        # 验证环境健康 (防止空文件夹)
        is_healthy, msg = self._validate_env_health(env_name)
        if not is_healthy:
            self.remove_env(env_name)
            error_msg = f"环境自检失败 ({msg})，已回滚。"
            if self._current_log_callback:
                self._current_log_callback(error_msg)
            self.install_finished.emit(error_msg)
            return

        python_exe = self.get_python_exe(env_name)
        env_path = self.miniconda_path / "envs" / env_name
        self.meta[env_name] = str(env_path)
        self._save_meta(self.meta)
        self._scan_envs()

        if self._current_log_callback:
            self._current_log_callback(f"环境 {env_name} 创建成功 ✅")
        self.install_finished.emit("success")
        # QTimer.singleShot(1000, lambda: self._install_default_packages(env_name, python_exe))

    def _validate_env_health(self, env_name):
        """简单验证 Python 是否能运行"""
        python_exe = self.get_python_exe(env_name)
        if not python_exe.exists():
            return False, "Executable missing"

        proc = QProcess()
        env = self._get_process_environment()
        if env.contains("PYTHONPATH"):
            env.remove("PYTHONPATH")
        proc.setProcessEnvironment(env)
        proc.start(str(python_exe), ["-c", "print('ok')"])
        proc.waitForFinished(5000)
        return (proc.exitCode() == 0), "Runtime check failed"

    # ==========================
    # 其他辅助方法 (克隆、删除、包管理)
    # ==========================
    def clone_env(self, source_env, target_env, log_callback=None):
        if target_env in self.list_envs():
            return
        if log_callback:
            log_callback(f"正在克隆 {source_env} -> {target_env}...")
        self._current_log_callback = log_callback

        conda_exe = self._get_conda_exe_path()

        # 克隆时同样加入 override，防止解析依赖时去连 defaults
        args = ["create", "--name", target_env, "--clone", source_env, "-y"]
        for channel in self.CONDA_CHANNELS:
            args.extend(["-c", channel])
        args.append("--override-channels")

        self._start_conda_process(
            conda_exe, args, lambda ec, es: self._on_clone_finished(ec, es, target_env)
        )

    def _on_clone_finished(self, ec, es, env_name):
        if ec == 0:
            self.meta[env_name] = str(self.miniconda_path / "envs" / env_name)
            self._save_meta(self.meta)
            self._scan_envs()
            if self._current_log_callback:
                self._current_log_callback(f"克隆完成 ✅")
            self.install_finished.emit("success")
        else:
            self.install_finished.emit(f"克隆失败 Code {ec}")

    def remove_env(self, env_name, log_callback=None):
        if log_callback:
            self._current_log_callback = log_callback
        conda_exe = self._get_conda_exe_path()
        # 删除不需要联网，所以不需要镜像源参数
        self._start_conda_process(
            conda_exe,
            ["env", "remove", "--name", env_name, "-y"],
            lambda ec, es: self._on_remove_finished_wrapper(env_name),
        )

    def _on_remove_finished_wrapper(self, env_name):
        env_path = self.miniconda_path / "envs" / env_name
        if env_path.exists():
            try:
                shutil.rmtree(env_path, ignore_errors=True)
            except:
                pass

        if env_name in self.meta:
            del self.meta[env_name]
        self._save_meta(self.meta)
        self._scan_envs()
        if self._current_log_callback:
            self._current_log_callback(f"环境已删除")
        self.remove_finished.emit("success")

    def _on_process_output(self):
        if self._process:
            data = self._process.readAllStandardOutput()
            try:
                text = (
                    data.data().decode("gbk")
                    if self._is_windows
                    else data.data().decode("utf-8")
                )
            except:
                text = data.data().decode("utf-8", errors="ignore")
            if text.strip() and self._current_log_callback:
                self._current_log_callback(self._clean_ansi_codes(text.strip()))

    def _install_default_packages(self, env_name, python_exe):
        self._install_next_package(python_exe, list(self.DEFAULT_PACKAGES))

    def _install_next_package(self, python_exe, remaining):
        if not remaining:
            if self._current_log_callback:
                self._current_log_callback("默认包安装完成 ✅")
            self.install_finished.emit("success")
            return

        pkg = remaining[0]
        if self._current_log_callback:
            self._current_log_callback(f"安装包: {pkg}...")

        # PIP 安装同样需要使用镜像
        cmd = ["-m", "pip", "install", pkg]
        mirrors = self.config.mirrors.value
        if mirrors:
            for m in mirrors:
                cmd.extend(
                    ["--extra-index-url", m, "--trusted-host", urlparse(m).hostname]
                )

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_process_output)
        if self._is_windows:
            self._process.setProcessEnvironment(self._get_process_environment())
        self._process.finished.connect(
            lambda ec, es: self._install_next_package(python_exe, remaining[1:])
        )
        self._process.start(str(python_exe), cmd)

    def ensure_pip(self, python_exe: str, log_callback=None) -> bool:
        # 简单检查 pip
        proc = QProcess()
        if self._is_windows:
            proc.setProcessEnvironment(self._get_process_environment())
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
            env_path = Path(self.meta[env_name])
            if env_path.is_file():
                return env_path
            # 兼容旧元数据（可能存的是 bin/Scripts 目录）
            if env_path.name in ("bin", "Scripts"):
                candidate = env_path / self._get_python_exe_name()
                if candidate.exists():
                    return candidate
                if self._is_windows:
                    candidate = env_path.parent / "python.exe"
                    if candidate.exists():
                        return candidate
                else:
                    candidate = env_path.parent / "bin" / "python"
                    if candidate.exists():
                        return candidate
            candidate = self._env_python_from_env_dir(env_path)
            if candidate.exists():
                return candidate
        p = self._env_python_from_env_dir(self.miniconda_path / "envs" / env_name)
        if p.exists():
            return p
        if env_name == "miniconda":
            return self._env_python_from_env_dir(self.miniconda_path)
        return Path("non_existent")

    def _clean_ansi_codes(self, text):
        return re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])").sub("", text)

    def _get_process_environment(self):
        from PyQt5.QtCore import QProcessEnvironment

        env = QProcessEnvironment.systemEnvironment()
        env.insert("CONDA_ALWAYS_YES", "true")  # 确保非交互
        if self._is_windows and not env.contains("SystemRoot"):
            env.insert("SystemRoot", os.environ.get("SystemRoot", "C:\\Windows"))
        return env

    # 保留旧接口，防止外部调用报错
    def _get_hidden_window_environment(self):
        return self._get_process_environment()
