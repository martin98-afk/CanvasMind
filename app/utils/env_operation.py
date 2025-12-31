# -*- coding: utf-8 -*-
import json
import os
import platform
import re
import shutil
import traceback
from pathlib import Path
from urllib.parse import urlparse

from PyQt5.QtCore import QObject, pyqtSignal, QProcess, QTimer, QUrl
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from loguru import logger

from app.utils.config import Settings


class EnvironmentManager(QObject):
    """使用Miniconda管理Python环境 (增强版)"""

    # 信号
    log_signal = pyqtSignal(str)
    install_finished = pyqtSignal(str)  # 传递结果或异常
    miniconda_install_finished = pyqtSignal(object)
    remove_finished = pyqtSignal(object)

    ENV_DIR = Path(__file__).parent.parent.parent / "envs"
    META_FILE = ENV_DIR / "environments.json"

    # 定义镜像源模板 (优先使用国内源，最后使用官方源)
    # py_ver: 例如 "311" (对应py3.11), ver: Miniconda版本号
    MIRROR_TEMPLATES = [
        "https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py{py_ver}_{ver}-2-Windows-x86_64.exe",
        "https://mirrors.bfsu.edu.cn/anaconda/miniconda/Miniconda3-py{py_ver}_{ver}-2-Windows-x86_64.exe",
        "https://repo.anaconda.com/miniconda/Miniconda3-py{py_ver}_{ver}-2-Windows-x86_64.exe"
    ]

    def __init__(self):
        super().__init__()
        self.config = Settings.get_instance()
        self.refresh_env_config()
        self.ENV_DIR.mkdir(exist_ok=True, parents=True)
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

        # 下载重试队列
        self._download_queue = []
        self._current_download_reply = None

    def refresh_env_config(self):
        # 默认要安装的包列表
        self.DEFAULT_PACKAGES = self.config.default_packages.value
        # 获取配置中的 Miniconda 版本，例如 "latest" 或具体版本号 "4.12.0"
        self.miniconda_version = self.config.miniconda_version.value

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
        """检查Miniconda是否已安装 (检查关键文件)"""
        conda_exe = self.miniconda_path / "Scripts" / "conda.exe"
        python_exe = self.miniconda_path / "python.exe"
        return conda_exe.exists() and python_exe.exists()

    def install_miniconda(self, log_callback=None):
        """安装Miniconda（支持多源重试 + 静默安装）"""
        if self._is_miniconda_installed():
            if log_callback:
                log_callback("Miniconda已安装")
            self.miniconda_install_finished.emit("success")
            return

        self._current_log_callback = log_callback

        # 准备下载队列
        py_version_short = "311"  # 默认使用 Python 3.11 的 Miniconda 基座
        self._download_queue = []

        for template in self.MIRROR_TEMPLATES:
            url = template.format(py_ver=py_version_short, ver=self.miniconda_version)
            self._download_queue.append(url)

        # 确定本地文件名
        filename = self._download_queue[0].split("/")[-1]
        self._installer_path = self.ENV_DIR / filename

        # 检查本地是否已有有效安装包
        if self._installer_path.exists():
            if self._validate_installer(self._installer_path):
                if log_callback:
                    log_callback("本地已存在有效的Miniconda安装包，跳过下载")
                self._start_miniconda_install()
                return
            else:
                if log_callback:
                    log_callback("本地安装包校验失败（可能已损坏），将重新下载...")
                try:
                    self._installer_path.unlink()
                except OSError:
                    pass

        # 开始下载流程
        self._try_next_download_source()

    def _try_next_download_source(self):
        """尝试队列中的下一个下载源"""
        if not self._download_queue:
            error_msg = "所有Miniconda镜像源下载均失败，请检查网络连接。"
            if self._current_log_callback:
                self._current_log_callback(error_msg)
            self.miniconda_install_finished.emit(RuntimeError(error_msg))
            return

        url = self._download_queue.pop(0)
        if self._current_log_callback:
            domain = urlparse(url).netloc
            self._current_log_callback(f"正在从 {domain} 下载Miniconda...")

        request = QNetworkRequest(QUrl(url))
        # 开启重定向跟随
        request.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        self._current_download_reply = self._network_manager.get(request)

    def _validate_installer(self, file_path: Path) -> bool:
        """校验安装包有效性"""
        try:
            # 1. 检查文件大小 (Miniconda 通常 > 50MB)
            if file_path.stat().st_size < 30 * 1024 * 1024:  # 小于30MB视为无效
                logger.warning(f"Installer size too small: {file_path.stat().st_size}")
                return False

            # 2. 检查文件头 (Windows EXE 应以 'MZ' 开头)
            with open(file_path, "rb") as f:
                header = f.read(2)
                if header != b'MZ':
                    logger.warning("Installer header check failed (not an EXE)")
                    return False
            return True
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False

    def _on_download_finished(self, reply):
        """Miniconda安装包下载完成回调"""
        # 防止处理非当前请求（如果有并发情况）
        if reply != self._current_download_reply:
            reply.deleteLater()
            return

        self._current_download_reply = None
        error = reply.error()
        url = reply.url().toString()

        try:
            if error != QNetworkReply.NoError:
                msg = f"源下载失败: {reply.errorString()}"
                logger.warning(msg)
                if self._current_log_callback:
                    self._current_log_callback(msg + "，尝试下一个源...")
                self._try_next_download_source()
                return

            # 保存文件
            data = reply.readAll()
            with open(self._installer_path, "wb") as f:
                f.write(data)

            # 校验文件
            if self._validate_installer(self._installer_path):
                if self._current_log_callback:
                    self._current_log_callback("Miniconda下载完成且校验通过，开始安装...")
                self._start_miniconda_install()
            else:
                msg = "下载的文件校验失败（可能是错误的HTML页面）"
                if self._current_log_callback:
                    self._current_log_callback(msg + "，尝试下一个源...")
                # 删除无效文件
                if self._installer_path.exists():
                    self._installer_path.unlink()
                self._try_next_download_source()

        except Exception as e:
            logger.error(f"Download exception: {e}")
            self._try_next_download_source()
        finally:
            reply.deleteLater()

    def _start_miniconda_install(self):
        """启动Miniconda静默安装进程"""
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)

        # 设置工作目录，防止因为路径问题导致的安装失败
        self._process.setWorkingDirectory(str(self.ENV_DIR))

        if platform.system() == "Windows":
            self._process.setProcessEnvironment(self._get_hidden_window_environment())

        self._process.readyReadStandardOutput.connect(self._on_process_output)
        self._process.finished.connect(self._on_miniconda_install_finished)

        # 构建增强的安装命令
        # /S : 静默安装
        # /InstallationType=JustMe : 仅为当前用户安装 (避免需要管理员权限导致失败)
        # /AddToPath=0 : 不添加到PATH (避免污染环境)
        # /RegisterPython=0 : 不注册为系统Python
        # /D=path : 安装路径
        args = [
            "/S",
            "/InstallationType=JustMe",
            "/AddToPath=0",
            "/RegisterPython=0",
            f"/D={str(self.miniconda_path)}"
        ]

        cmd = str(self._installer_path)
        if self._current_log_callback:
            self._current_log_callback(f"正在执行安装程序，请耐心等待...")
            logger.info(f"Install CMD: {cmd} {args}")

        self._process.start(cmd, args)

    def _on_miniconda_install_finished(self, exit_code, exit_status):
        """Miniconda安装完成回调"""
        try:
            # 再次检查关键文件是否存在，因为静默安装可能返回0但实际未安装成功
            conda_exe = self.miniconda_path / "Scripts" / "conda.exe"
            python_exe = self.miniconda_path / "python.exe"

            if not (conda_exe.exists() and python_exe.exists()):
                error_msg = (f"Miniconda安装看来失败了 (Exit Code: {exit_code})：未找到关键文件。\n"
                             f"可能原因：杀毒软件拦截或路径包含空格/非ASCII字符。")
                if self._current_log_callback:
                    self._current_log_callback(error_msg)
                self.miniconda_install_finished.emit(RuntimeError(error_msg))
                return

            if self._current_log_callback:
                self._current_log_callback("Miniconda安装成功！")

            # 清理安装包
            if self._installer_path and self._installer_path.exists():
                try:
                    self._installer_path.unlink()
                except:
                    pass

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
                log_callback("Miniconda未安装，正在初始化...")
            # 记录待创建的环境
            self._pending_env_creation = (version, env_name, log_callback)
            self.install_miniconda(log_callback)
            return

        self._create_env_with_qprocess(version, env_name, log_callback)

    def _create_env_with_qprocess(self, version, env_name=None, log_callback=None):
        """使用QProcess创建环境"""
        # 提取主要版本号
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
            self.install_finished.emit(str(env_path))
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

        # 构建命令
        args = [
            "create",
            "--name", env_name,
            f"python={version}",
            "-y"
        ]

        self._process.start(str(conda_exe), args)

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
            self.install_finished.emit(str(env_path))
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
                error_msg = f"环境 {env_name} 克隆看似成功但未找到 python.exe"
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
                self.install_finished.emit(error_msg)
                return

            python_exe = self.get_python_exe(env_name)
            if not python_exe.exists():
                error_msg = f"环境 {env_name} 创建失败，未找到 python.exe"
                if self._current_log_callback:
                    self._current_log_callback(error_msg)
                self.install_finished.emit(error_msg)
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
            self.install_finished.emit("安装完成")
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

        # 构建pip安装命令，使用配置的镜像源
        install_cmd = self._build_pip_install_command(package)
        self._process.start(str(python_exe), install_cmd)

    def _build_pip_install_command(self, package):
        """构建pip安装命令，使用配置的镜像源"""
        cmd = ["-m", "pip", "install", package]

        # 获取配置的镜像源列表
        mirrors = self.config.mirrors.value

        if mirrors:  # 如果镜像源列表不为空
            # 添加所有镜像源作为信任的主机
            for mirror_url in mirrors:
                cmd.extend(["--extra-index-url", mirror_url])
                try:
                    parsed = urlparse(mirror_url)
                    cmd.extend(["--trusted-host", parsed.hostname])
                except Exception:
                    logger.warning(f"Invalid mirror URL: {mirror_url}")
        else:
            pass

        return cmd

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
            self.remove_finished.emit(error_msg)
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
            # 即使conda返回成功，物理文件夹可能还残存
            env_path = self.miniconda_path / "envs" / env_name
            if env_path.exists():
                import time
                time.sleep(1)
                try:
                    shutil.rmtree(env_path, ignore_errors=True)
                except Exception as e:
                    logger.warning(f"Failed to fully delete env dir: {e}")

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
        """处理子进程输出，优化中文解码"""
        if self._process:
            raw_data = self._process.readAllStandardOutput()
            data_bytes = bytes(raw_data)

            # 尝试解码，优先GBK（Windows命令行），其次UTF-8
            decoded_str = ""
            try:
                decoded_str = data_bytes.decode("gbk")
            except UnicodeDecodeError:
                try:
                    decoded_str = data_bytes.decode("utf-8", errors="ignore")
                except:
                    pass

            if decoded_str.strip() and self._current_log_callback:
                clean_data = self._clean_ansi_codes(decoded_str.strip())
                self._current_log_callback(clean_data)

    def list_envs(self):
        self._scan_envs()
        return list(self.meta.keys())

    def get_python_exe(self, env_name: str) -> Path:
        if env_name is None:
            return None

        # 优先从 meta 缓存读取
        if env_name in self.meta:
            path = Path(self.meta[env_name]) / "python.exe"
            if path.exists():
                return path

        # 缓存没有，直接拼路径
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
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def ensure_pip(self, python_exe: str, log_callback=None) -> bool:
        proc = QProcess()
        if platform.system() == "Windows":
            proc.setProcessEnvironment(self._get_hidden_window_environment())

        # 1. Check
        proc.start(python_exe, ["-m", "pip", "--version"])
        proc.waitForFinished()

        if proc.exitCode() == 0:
            log_callback and log_callback("pip 已存在 ✅")
            return True
        else:
            log_callback and log_callback("pip 不存在，正在安装 ensurepip...")
            try:
                # 2. Ensurepip
                ensurepip_proc = QProcess()
                if platform.system() == "Windows":
                    ensurepip_proc.setProcessEnvironment(self._get_hidden_window_environment())
                ensurepip_proc.start(python_exe, ["-m", "ensurepip"])
                ensurepip_proc.waitForFinished()

                if ensurepip_proc.exitCode() == 0:
                    # 3. Upgrade
                    pip_upgrade_proc = QProcess()
                    if platform.system() == "Windows":
                        pip_upgrade_proc.setProcessEnvironment(self._get_hidden_window_environment())
                    pip_upgrade_proc.start(python_exe, self._build_pip_install_command("pip"))
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

        # 确保 Conda 操作为非交互模式
        env.insert("CONDA_ALWAYS_YES", "true")

        # 确保 SystemRoot 存在 (某些 conda 操作依赖)
        if not env.contains("SystemRoot"):
            env.insert("SystemRoot", os.environ.get("SystemRoot", "C:\\Windows"))

        return env