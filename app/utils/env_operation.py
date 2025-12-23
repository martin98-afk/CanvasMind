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
        base = Path(sys.executable).parent / "_internal"
        uv_exe = base / "uv.exe"
        if uv_exe.exists():
            return str(uv_exe)
    return "uv"


class EnvironmentManager(QObject):
    """使用 uv 管理 Python 环境（自动下载并嵌入多版本 Python）"""

    log_signal = pyqtSignal(str)
    install_finished = pyqtSignal(str)
    remove_finished = pyqtSignal(object)

    ENV_DIR = Path(__file__).parent.parent.parent / ".venv"
    BASE_ENVS_DIR = ENV_DIR
    META_FILE = ENV_DIR / "environments.json"

    def __init__(self):
        super().__init__()
        self.config = Settings.get_instance()
        self.ENV_DIR.mkdir(exist_ok=True)
        self.BASE_ENVS_DIR.mkdir(parents=True, exist_ok=True)
        if not self.META_FILE.exists():
            self._save_meta({})
        self.meta = self._load_meta()
        self._scan_envs()
        self._process = None
        self._current_log_callback = None
        self._pending_env_creation = None
        # 新增：用于收集 uv python find 输出
        self._uv_find_output = ""
        self._collecting_find_output = False

    def _load_meta(self):
        try:
            return json.loads(self.META_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_meta(self, data):
        self.META_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _scan_envs(self):
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
                    log_callback("❌ 未检测到 uv")
                return False
        except Exception as e:
            if log_callback:
                log_callback(f"❌ 检查 uv 失败: {e}")
            return False

    def _on_create_env_finished(self, exit_code, exit_status, env_name):
        try:
            if exit_code != 0:
                error_msg = f"环境 {env_name} 创建失败，退出码: {exit_code}"
                if self._current_log_callback:
                    self._current_log_callback(error_msg)
                self.install_finished.emit(error_msg)
                return

            env_path = self.ENV_DIR / env_name
            python_exe = self._get_python_exe_in(env_path)

            if not python_exe.exists():
                error_msg = f"未找到 python.exe: {python_exe}"
                if self._current_log_callback:
                    self._current_log_callback(error_msg)
                self.install_finished.emit(error_msg)
                return

            self.meta[env_name] = str(env_path)
            self._save_meta(self.meta)
            if self._current_log_callback:
                self._current_log_callback(f"✅ 环境 {env_name} 创建成功")
            QTimer.singleShot(1000, lambda: self._install_default_packages(env_name, python_exe))
        except Exception as e:
            if self._current_log_callback:
                import traceback
                self._current_log_callback(f"创建环境异常: {e}\n{traceback.format_exc()}")
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
            requirements = result.stdout.strip() or "# 空环境"
        except Exception as e:
            if log_callback:
                log_callback(f"导出依赖失败: {e}")
            self.install_finished.emit(str(e))
            return
        req_file = self.ENV_DIR / f"{target_env}_requirements.txt"
        req_file.write_text(requirements, encoding="utf-8")
        source_version = self._get_python_version(source_python)
        self.create_env(source_version, target_env, log_callback)
        self._pending_clone_req = (target_env, req_file)

    def _get_python_version(self, python_exe: Path) -> str:
        try:
            result = subprocess.run([str(python_exe), "--version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                ver = result.stdout.strip().split()[-1]
                return ".".join(ver.split(".")[:2])
        except:
            pass
        return "3.11"

    def _install_default_packages(self, env_name: str, python_exe: Path):
        if hasattr(self, '_pending_clone_req') and self._pending_clone_req[0] == env_name:
            target_env, req_file = self._pending_clone_req
            delattr(self, '_pending_clone_req')
            self._install_from_requirements(python_exe, req_file, env_name)
        else:
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
        """cmd: list of strings"""
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
        if not self._process:
            return
        data = self._process.readAllStandardOutput().data().decode("utf-8", errors="ignore")
        if data.strip() and self._current_log_callback:
            clean_data = self._clean_ansi_codes(data.strip())
            self._current_log_callback(clean_data)

        # ✅ 收集 uv python find 的输出
        if self._collecting_find_output:
            self._uv_find_output += data

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

    # ============================================
    # 核心：用 uv 下载 + 复制到本地（全程异步）
    # ============================================

    def get_base_python_dir(self, version: str) -> Path:
        clean_version = "".join(version.split(".")[:2])  # 3.13 → 313
        return self.BASE_ENVS_DIR / f"python_base_{clean_version}"

    def ensure_python_installed(self, version: str, log_callback=None):
        base_dir = self.get_base_python_dir(version)
        python_exe = base_dir / "python.exe"
        if python_exe.exists():
            if log_callback:
                log_callback(f"✅ Python {version} 已存在: {python_exe}")
            self._proceed_to_create_venv_with_base_python(version)
            return
        if log_callback:
            log_callback(f"正在通过 uv 下载 Python {version}...")
        self._pending_python_version = version
        self._current_log_callback = log_callback
        cmd = ["uv", "python", "install", str(version)]
        self._start_process(cmd, log_callback, self._on_uv_python_install_finished)

    def _on_uv_python_install_finished(self, exit_code, exit_status):
        version = self._pending_python_version
        if exit_code != 0:
            error = "uv python install 失败"
            if self._current_log_callback:
                self._current_log_callback(f"❌ {error}")
            self.install_finished.emit(error)
            return
        if self._current_log_callback:
            self._current_log_callback("✅ uv 下载完成，正在定位路径...")
        # ✅ 开始收集 find 输出
        self._collecting_find_output = True
        self._uv_find_output = ""
        cmd = ["uv", "python", "find", str(version)]
        self._start_process(cmd, self._current_log_callback, self._on_uv_python_find_finished)

    def _on_uv_python_find_finished(self, exit_code, exit_status):
        # ✅ 停止收集
        self._collecting_find_output = False
        if exit_code != 0:
            error = "uv python find 失败"
            if self._current_log_callback:
                self._current_log_callback(f"❌ {error}")
            self.install_finished.emit(error)
            return
        output = self._uv_find_output.strip()
        if not output:
            error = "uv python find 无输出"
            if self._current_log_callback:
                self._current_log_callback(f"❌ {error}")
            self.install_finished.emit(error)
            return
        try:
            python_exe_path = Path(output).resolve()
            uv_python_dir = python_exe_path.parent
            if not uv_python_dir.exists() or not (uv_python_dir / "Lib").exists():
                raise RuntimeError(f"无效的 Python 目录: {uv_python_dir}")

            base_dir = self.get_base_python_dir(self._pending_python_version)

            # 🔥 强制清理并复制（修复 WinError 183）
            if base_dir.exists():
                shutil.rmtree(base_dir)
            base_dir.parent.mkdir(parents=True, exist_ok=True)

            if self._current_log_callback:
                self._current_log_callback(f"正在复制到 {base_dir} ...")

            # 使用 dirs_exist_ok=True（Python 3.8+）
            shutil.copytree(uv_python_dir, base_dir, dirs_exist_ok=True)

            if self._current_log_callback:
                self._current_log_callback("✅ Python 嵌入成功")
            self._proceed_to_create_venv_with_base_python(self._pending_python_version)

        except Exception as e:
            error = f"复制失败: {e}"
            if self._current_log_callback:
                self._current_log_callback(f"❌ {error}")
            self.install_finished.emit(str(error))

    def _proceed_to_create_venv_with_base_python(self, python_version):
        if not self._pending_env_creation:
            return
        version, env_name, log_callback = self._pending_env_creation
        base_dir = self.get_base_python_dir(python_version)
        base_python_exe = base_dir / "python.exe"
        if not base_python_exe.exists():
            if log_callback:
                log_callback("❌ 嵌入式 Python 未找到")
            self.install_finished.emit("嵌入式 Python 不存在")
            return
        env_path = self.ENV_DIR / env_name
        cmd = ["uv", "venv", str(env_path), "--python", str(base_python_exe)]
        if log_callback:
            log_callback(f"正在创建虚拟环境 {env_name}...")
        self._current_log_callback = log_callback
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_process_output)
        if platform.system() == "Windows":
            from PyQt5.QtCore import QProcessEnvironment
            env = QProcessEnvironment.systemEnvironment()
            self._process.setProcessEnvironment(env)
        self._process.finished.connect(lambda ec, es: self._on_create_env_finished(ec, es, env_name))
        self._process.start(cmd[0], cmd[1:])

    def create_env(self, python_version: str, env_name: str, log_callback=None):
        if env_name in self.list_envs():
            if log_callback:
                log_callback(f"环境 {env_name} 已存在")
            self.install_finished.emit("已存在")
            return
        if not self.ensure_uv_installed(log_callback):
            self.install_finished.emit("uv 未安装")
            return
        self._pending_env_creation = (python_version, env_name, log_callback)
        self.ensure_python_installed(python_version, log_callback)

    def ensure_pip(self, python_exe: str, log_callback=None) -> bool:
        return True