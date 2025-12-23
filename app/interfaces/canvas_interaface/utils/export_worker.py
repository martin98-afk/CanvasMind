# 启动 uv 环境创建线程
import platform

from PyQt5.QtCore import QThread, pyqtSignal
import re
import toml
import subprocess
import sys

def to_valid_package_name(name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    normalized = re.sub(r"^[^a-zA-Z0-9]+", "", normalized)
    normalized = re.sub(r"[^a-zA-Z0-9]+$", "", normalized)
    if not normalized:
        normalized = "project"
    if normalized and normalized[0].isdigit():
        normalized = "pkg_" + normalized
    return normalized.lower()

class UvWorker(QThread):
    on_success = pyqtSignal(str)
    on_error = pyqtSignal(str)

    def __init__(self, export_path, dependencies, display_name):
        super().__init__()
        self.export_path = export_path
        self.dependencies = dependencies
        self.display_name = display_name

    def run(self):
        try:
            kwargs = {}
            if platform.system() == "Windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            package_name = to_valid_package_name(self.display_name)
            # uv init
            subprocess.run(
                ["uv", "init", "--lib", "--no-readme", "--name", package_name],
                cwd=self.export_path,
                check=True,
                timeout=30,
                **kwargs
            )
            # 写 pyproject.toml
            pyproject_path = self.export_path / "pyproject.toml"
            with open(pyproject_path, 'r', encoding='utf-8') as f:
                pyproject = toml.load(f)
            clean_deps = [d.strip() for d in self.dependencies if
                          d.strip() and not d.strip().startswith("#")]
            pyproject.setdefault("project", {})["dependencies"] = clean_deps
            pyproject["project"]["name"] = package_name
            with open(pyproject_path, 'w', encoding='utf-8') as f:
                toml.dump(pyproject, f)

            # uv lock
            subprocess.run(["uv", "lock"], cwd=self.export_path, check=True, timeout=60, **kwargs)
            # uv sync
            subprocess.run(["uv", "sync", "--frozen"], cwd=self.export_path, check=True, timeout=120, **kwargs)
            # 获取 Python 路径
            venv_path = self.export_path / ".venv"
            if sys.platform == "win32":
                python_exe = venv_path / "Scripts" / "python.exe"
            else:
                python_exe = venv_path / "bin" / "python"
            if not python_exe.exists():
                self.on_error.emit("虚拟环境未生成 Python 可执行文件")
                return
            rel_path = python_exe.relative_to(self.export_path).as_posix()
            self.on_success.emit(rel_path)
        except subprocess.TimeoutExpired as e:
            self.on_error.emit(f"uv 命令超时: {e}")
        except Exception as e:
            self.on_error.emit(str(e))