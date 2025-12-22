# -*- coding: utf-8 -*-
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from PyQt5.QtCore import QObject, pyqtSignal, QProcess, QTimer

from app.utils.config import Settings


def get_uv_path():
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包模式
        base_path = Path("_internal")  # 或 sys.executable.parent（见下方说明）
        uv_path = base_path / "uv.exe"
    else:
        # 开发模式
        uv_path = "uv"
    return str(uv_path)


class EnvironmentManager(QObject):
    """使用 uv 管理 Python 虚拟环境和包（替代 Miniconda）"""

    log_signal = pyqtSignal(str)
    install_finished = pyqtSignal(str)
    remove_finished = pyqtSignal(object)

    ENV_DIR = Path(__file__).parent.parent.parent / ".venv"
    META_FILE = ENV_DIR / "environments.json"

    def __init__(self):
        super().__init__()
        self.config = Settings.get_instance()
        self.ENV_DIR.mkdir(exist_ok=True)
        if not self.META_FILE.exists():
            self._save_meta({})
        self.meta = self._load_meta()
        self._scan_envs()
        self._process = None
        self._current_log_callback = None

    def _load_meta(self):
        try:
            return json.loads(self.META_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_meta(self, data):
        self.META_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _scan_envs(self):
        """扫描 envs/ 下所有合法 venv"""
        new_meta = {}
        for d in self.ENV_DIR.iterdir():
            if d.is_dir():
                python_exe = self._get_python_exe_in(d)
                if python_exe and python_exe.exists():
                    new_meta[d.name] = str(d)
        self.meta = new_meta
        self._save_meta(self.meta)

    def _get_python_exe_in(self, env_path: Path) -> Path:
        if platform.system() == "Windows":
            return env_path / "Scripts" / "python.exe"
        else:
            return env_path / "bin" / "python"

    def get_python_exe(self, env_name: str) -> Path:
        if env_name not in self.meta:
            return None
        env_path = Path(self.meta[env_name])
        return self._get_python_exe_in(env_path)

    def list_envs(self):
        self._scan_envs()
        return list(self.meta.keys())

    def ensure_uv_installed(self, log_callback=None) -> bool:
        """确保 uv 已安装（简单检查）"""
        try:
            kwargs = {}
            if platform.system() == "Windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(
                [get_uv_path(), "--version"],
                capture_output=True,
                text=True,
                timeout=15,
                **kwargs
            )
            if result.returncode == 0:
                if log_callback:
                    log_callback("✅ uv 已安装")
                return True
            else:
                if log_callback:
                    log_callback("❌ 未检测到 uv，请先安装 uv（pip install uv）")
                return False
        except FileNotFoundError:
            if log_callback:
                log_callback("❌ 未检测到 uv，请先安装 uv（pip install uv）")
            return False
        except Exception as e:
            if log_callback:
                log_callback(f"❌ 检查 uv 时出错: {e}")
            return False

    def _on_create_env_finished(self, exit_code, exit_status, env_name):
        try:
            if exit_code != 0:
                error_msg = f"环境 {env_name} 创建失败，退出码: {exit_code}"
                if self._current_log_callback:
                    self._current_log_callback(error_msg)
                self.install_finished.emit(error_msg)
                return

            # ✅ 直接构造预期的 python 路径（不依赖 meta）
            env_path = self.ENV_DIR / env_name
            python_exe = self._get_python_exe_in(env_path)

            if not python_exe.exists():
                error_msg = f"环境创建成功，但未找到 python.exe: {python_exe}"
                if self._current_log_callback:
                    self._current_log_callback(error_msg)
                self.install_finished.emit(error_msg)
                return

            # ✅ 现在才更新 meta
            self.meta[env_name] = str(env_path)
            self._save_meta(self.meta)

            if self._current_log_callback:
                self._current_log_callback(f"✅ 环境 {env_name} 创建成功")

            QTimer.singleShot(1000, lambda: self._install_default_packages(env_name, python_exe))
        except Exception as e:
            if self._current_log_callback:
                self._current_log_callback(f"创建环境异常: {e}")
                import traceback
                self._current_log_callback(traceback.format_exc())
            self.install_finished.emit(str(e))

    def clone_env(self, source_env: str, target_env: str, log_callback=None):
        if source_env not in self.list_envs():
            error_msg = f"源环境 {source_env} 不存在"
            if log_callback:
                log_callback(error_msg)
            self.install_finished.emit(error_msg)
            return

        if target_env in self.list_envs():
            if log_callback:
                log_callback(f"目标环境 {target_env} 已存在")
            self.install_finished.emit("已存在")
            return

        if not self.ensure_uv_installed(log_callback):
            self.install_finished.emit("uv 未安装")
            return

        # 步骤1: 获取源环境的包列表
        if log_callback:
            log_callback(f"正在导出 {source_env} 的依赖...")

        source_python = self.get_python_exe(source_env)
        try:
            result = subprocess.run(
                [get_uv_path(), "pip", "freeze", "--python", str(source_python)],
                capture_output=True,
                text=True,
                timeout=15
            )
            if result.returncode != 0:
                raise RuntimeError("导出依赖失败")

            requirements = result.stdout.strip()
            if not requirements:
                requirements = "# 空环境"
        except Exception as e:
            if log_callback:
                log_callback(f"导出依赖失败: {e}")
            self.install_finished.emit(str(e))
            return

        req_file = self.ENV_DIR / f"{target_env}_requirements.txt"
        req_file.write_text(requirements, encoding="utf-8")

        # 步骤2: 创建新环境（使用相同Python版本）
        source_version = self._get_python_version(source_python)
        self.create_env(source_version, target_env, log_callback)
        # 克隆逻辑延后到 install_default_packages 中处理
        # 临时存储 req_file 路径
        self._pending_clone_req = (target_env, req_file)

    def _get_python_version(self, python_exe: Path) -> str:
        try:
            result = subprocess.run(
                [str(python_exe), "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # 返回 "3.11" 这样的主次版本
                ver = result.stdout.strip().split()[-1]
                return ".".join(ver.split(".")[:2])
        except:
            pass
        return "3.11"  # fallback

    def _install_default_packages(self, env_name: str, python_exe: Path):
        # 检查是否是克隆场景
        if hasattr(self, '_pending_clone_req') and self._pending_clone_req[0] == env_name:
            target_env, req_file = self._pending_clone_req
            delattr(self, '_pending_clone_req')
            self._install_from_requirements(python_exe, req_file, env_name)
        else:
            # 默认包安装
            packages = self.config.default_packages.value
            if packages:
                if self._current_log_callback:
                    self._current_log_callback(f"正在安装默认包: {', '.join(packages)}")
                self._install_next_package(python_exe, list(packages), env_name)
            else:
                if self._current_log_callback:
                    self._current_log_callback("✅ 无默认包，环境初始化完成")
                self.install_finished.emit("安装完成")

    def _install_from_requirements(self, python_exe: Path, req_file: Path, env_name: str):
        if self._current_log_callback:
            self._current_log_callback(f"正在从 {req_file.name} 安装依赖...")

        cmd = [get_uv_path(), "pip", "install", "-r", str(req_file), "--python", str(python_exe)]
        self._add_mirror_sources_to_cmd(cmd)

        def _on_finished(ec, es):
            req_file.unlink(missing_ok=True)
            if ec == 0:
                if self._current_log_callback:
                    self._current_log_callback("✅ 克隆依赖安装完成")
                self.install_finished.emit("克隆完成")
            else:
                if self._current_log_callback:
                    self._current_log_callback("❌ 克隆依赖安装失败")
                self.install_finished.emit("克隆失败")

        self._start_process(cmd, self._current_log_callback, _on_finished)

    def remove_env(self, env_name: str, log_callback=None):
        if env_name not in self.list_envs():
            if log_callback:
                log_callback(f"环境 {env_name} 不存在")
            self.remove_finished.emit("不存在")
            return

        env_path = Path(self.meta[env_name])
        try:
            if log_callback:
                log_callback(f"正在删除环境 {env_name} ...")
            shutil.rmtree(env_path, ignore_errors=True)
            del self.meta[env_name]
            self._save_meta(self.meta)
            self._scan_envs()
            if log_callback:
                log_callback(f"✅ 环境 {env_name} 删除完成")
            self.remove_finished.emit("success")
        except Exception as e:
            if log_callback:
                log_callback(f"删除失败: {e}")
            self.remove_finished.emit(str(e))

    def _start_process(self, cmd, log_callback, finished_callback, *args):
        self._current_log_callback = log_callback
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_process_output)
        if platform.system() == "Windows":
            from PyQt5.QtCore import QProcessEnvironment
            env = QProcessEnvironment.systemEnvironment()
            self._process.setProcessEnvironment(env)
        self._process.finished.connect(lambda ec, es: finished_callback(ec, es, *args))
        self._process.start(cmd[0], cmd[1:])

    def _on_process_output(self):
        if self._process:
            data = self._process.readAllStandardOutput().data().decode("utf-8", errors="ignore")
            if data.strip() and self._current_log_callback:
                clean_data = self._clean_ansi_codes(data.strip())
                self._current_log_callback(clean_data)

    def _clean_ansi_codes(self, text):
        ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
        return ansi_escape.sub('', text)

    def _add_mirror_sources_to_cmd(self, cmd):
        mirrors = self.config.mirrors.value
        if mirrors:
            primary = mirrors[0]
            cmd.extend(["--index-url", primary])
            parsed = urlparse(primary)
            cmd.extend(["--trusted-host", parsed.hostname])
            for mirror in mirrors[1:]:
                cmd.extend(["--extra-index-url", mirror])
                parsed = urlparse(mirror)
                cmd.extend(["--trusted-host", parsed.hostname])

    def _install_next_package(self, python_exe: Path, remaining, env_name: str):
        if not remaining:
            if self._current_log_callback:
                self._current_log_callback("✅ 默认包安装完成")
            self.install_finished.emit("安装完成")
            return

        pkg = remaining[0]
        cmd = [get_uv_path(), "pip", "install", pkg, "--python", str(python_exe)]
        self._add_mirror_sources_to_cmd(cmd)

        def _on_finished(ec, es):
            if ec != 0:
                if self._current_log_callback:
                    self._current_log_callback(f"⚠️ {pkg} 安装失败，继续...")
            else:
                if self._current_log_callback:
                    self._current_log_callback(f"✅ {pkg} 安装完成")
            QTimer.singleShot(500, lambda: self._install_next_package(python_exe, remaining[1:], env_name))

        self._start_process(cmd, self._current_log_callback, _on_finished)

    def ensure_python_installed(self, version: str, log_callback=None) -> bool:
        """
        确保指定版本的 Python 已通过 uv 安装
        返回: (是否成功, python_path)
        """
        if log_callback:
            log_callback(f"正在检查 Python {version} 是否已安装...")

        # 先列出已安装的 Python
        try:
            kwargs = {}
            if platform.system() == "Windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(
                [get_uv_path(), "python", "list"],
                capture_output=True,
                text=True,
                timeout=15,
                **kwargs
            )
            if result.returncode != 0:
                if log_callback:
                    log_callback(f"❌ 无法列出 Python: {result.stderr}")
                return False
        except FileNotFoundError:
            if log_callback:
                log_callback("❌ uv 未安装")
            return False
        except Exception as e:
            if log_callback:
                log_callback(f"❌ 检查 Python 时出错: {e}")
            return False

        # 检查是否已有该版本（模糊匹配，如 3.12 匹配 3.12.3）
        lines = result.stdout.strip().splitlines()
        for line in lines:
            if line.strip().startswith(version) and "installed" in line:
                # 提取路径（最后一列）
                parts = line.strip().split()
                if parts:
                    python_path = parts[-1]
                    if log_callback:
                        log_callback(f"✅ Python {version} 已安装: {python_path}")
                    return True

        # 未安装，开始安装
        if log_callback:
            log_callback(f"正在安装 Python {version}（通过 uv）... 这可能需要几分钟")

        install_cmd = [get_uv_path(), "python", "install", version, "--no-progress"]
        self._start_process(install_cmd, log_callback, self._dummy_finished)
        self._process.waitForFinished(300_000)  # 最多等待 5 分钟

        if self._process.exitCode() == 0:
            if log_callback:
                log_callback(f"✅ Python {version} 安装成功")
            return True
        else:
            stderr = self._process.readAllStandardError().data().decode("utf-8", errors="ignore")
            if log_callback:
                log_callback(f"❌ 安装 Python {version} 失败: {stderr}")
            return False

    def _dummy_finished(self, ec, es):
        pass  # 用于同步 wait

    def create_env(self, python_version: str, env_name: str, log_callback=None):
        """创建环境，自动安装所需 Python 版本"""
        if not self.ensure_uv_installed(log_callback):
            self.install_finished.emit("uv 未安装")
            return

        if env_name in self.list_envs():
            if log_callback:
                log_callback(f"环境 {env_name} 已存在")
            self.install_finished.emit("已存在")
            return

        # ✅ 关键：确保 Python 版本已安装
        if not self.ensure_python_installed(python_version, log_callback):
            self.install_finished.emit(f"Python {python_version} 安装失败")
            return

        env_path = self.ENV_DIR / env_name
        cmd = [get_uv_path(), "venv", str(env_path), "--python", python_version]

        if log_callback:
            log_callback(f"正在创建虚拟环境 {env_name} ...")

        self._start_process(cmd, log_callback, self._on_create_env_finished, env_name)

    def ensure_pip(self, python_exe: str, log_callback=None) -> bool:
        # uv pip 不依赖 pip，但某些包可能需要
        # 这里简单返回 True，实际可跳过
        return True