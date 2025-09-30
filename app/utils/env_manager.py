# dev_codes/utils/env_manager.py
import os
import sys
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Optional
import venv
import platform

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
        """判断是否为主进程（避免 PyInstaller 子进程重复初始化）"""
        import sys
        # 方法1：检查是否由 PyInstaller 启动
        if getattr(sys, 'frozen', False):
            # PyInstaller 打包后的程序
            # 检查启动参数中是否有 conda/pip 等子命令
            import inspect
            frame = inspect.currentframe()
            try:
                # 向上查找调用栈
                while frame:
                    filename = frame.f_code.co_filename
                    if 'subprocess' in filename or 'conda' in filename:
                        return False  # 是子进程
                    frame = frame.f_back
            finally:
                del frame
            return True  # 是主进程

        # 方法2：检查启动参数（更简单可靠）
        import sys
        # 如果启动参数中有这些关键词，说明是子进程
        forbidden_args = ['-c', 'conda', 'pip', '--json', 'list']
        for arg in sys.argv[1:]:
            if arg in forbidden_args:
                return False
        return True

    def _auto_discover_environments(self):
        """自动发现环境（只在主进程中执行）"""
        if not self._is_main_process():
            return  # 子进程不执行

        logger.info("🔍 正在自动发现环境...")
        # 1. 发现 conda 环境
        self._discover_conda_environments()

        # 2. 发现 venv 环境
        self._discover_venv_environments()

        # 3. 发现 virtualenv 环境
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

        # 确保至少有一个默认环境（本地环境）
        if not self.environments:
            self._create_default_environment()
            self._save_environments()

    def _create_default_environment(self):
        """创建默认本地环境"""
        # 使用当前 Python 环境作为默认环境
        self.environments["system"] = {
            "path": sys.prefix,
            "name": "默认环境",
            "type": "system",
            "python_version": sys.version,
            "packages": self._get_system_packages()
        }

        # 同时创建一个本地虚拟环境（可选）
        try:
            local_env_path = self.create_environment("local", sys.version_info[:2])
            self.environments["local"] = {
                "path": local_env_path,
                "name": "本地环境",
                "type": "venv",
                "python_version": self._get_python_version(self.get_python_executable("local")),
                "packages": []
            }
        except Exception as e:
            logger.error(f"创建本地环境失败: {e}")

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
            # ✅ 添加超时和错误抑制
            result = subprocess.run(
                ['conda', 'env', 'list', '--json'],
                capture_output=True,
                text=True,
                timeout=5,  # 5秒超时
                cwd=os.getcwd()  # 明确工作目录
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
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, Exception) as e:
            # ✅ 静默处理错误，避免中断主程序
            logger.error(f"⚠️ 发现 conda 环境失败（已忽略）: {e}")
            pass  # 不抛出异常

    def _discover_venv_environments(self):
        """发现 venv 环境"""
        # 搜索常见的虚拟环境目录
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
        # 类似 venv 的发现逻辑
        pass

    def _get_conda_python_executable(self, env_path: str) -> str:
        """获取 conda 环境的 Python 可执行文件"""
        if platform.system() == "Windows":
            return os.path.join(env_path, "Scripts", "python.exe")
        else:
            return os.path.join(env_path, "bin", "python")

    def _get_venv_python_executable(self, env_path: Path) -> str:
        """获取 venv 环境的 Python 可执行文件"""
        if platform.system() == "Windows":
            return str(env_path / "Scripts" / "python.exe")
        else:
            return str(env_path / "bin" / "python")

    def _get_python_version(self, python_exe: str) -> str:
        """获取 Python 版本"""
        try:
            result = subprocess.run([python_exe, '--version'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return "Unknown"
        except Exception as e:
            logger.error(f"获取 Python 版本失败: {e}")
            return "Unknown"

    def _get_system_packages(self) -> List[Dict]:
        """获取系统环境的包列表"""
        try:
            result = subprocess.run([sys.executable, '-m', 'pip', 'list', '--format=json'],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                packages = json.loads(result.stdout)
                return [{"name": pkg["name"], "version": pkg["version"]} for pkg in packages]
        except Exception as e:
            logger.error(f"获取系统包列表失败: {e}")
        return []

    def create_environment(self, name: str, python_version: tuple = None) -> str:
        """创建新环境"""
        env_path = self.base_dir / name
        if env_path.exists():
            raise ValueError(f"环境 {name} 已存在")

        # 创建虚拟环境
        builder = venv.EnvBuilder(with_pip=True, system_site_packages=False)
        builder.create(env_path)

        # 获取 Python 可执行文件路径
        python_exe = self._get_venv_python_executable(env_path)

        # 升级 pip
        try:
            subprocess.run([python_exe, '-m', 'pip', 'install', '--upgrade', 'pip'],
                           capture_output=True, timeout=60)
        except Exception as e:
            logger.error(f"升级 pip 失败: {e}")

        return str(env_path)

    def remove_environment(self, name: str):
        """删除环境"""
        if name in ["default", "system"]:
            raise ValueError("不能删除系统环境")

        if name in self.environments:
            env_path = Path(self.environments[name]["path"])
            if env_path.exists():
                import shutil
                shutil.rmtree(env_path)
            del self.environments[name]
            self._save_environments()

    def list_environments(self) -> List[Dict]:
        """列出所有环境"""
        return list(self.environments.values())

    def get_environment(self, name: str) -> Optional[Dict]:
        """获取环境信息"""
        return self.environments.get(name)

    def get_python_executable(self, env_name: str) -> str:
        """获取环境的 Python 可执行文件路径"""
        env_info = self.get_environment(env_name)
        if not env_info:
            raise ValueError(f"环境 {env_name} 不存在")

        env_path = Path(env_info["path"])
        if env_info["type"] == "conda":
            return self._get_conda_python_executable(str(env_path))
        elif env_info["type"] == "venv":
            return self._get_venv_python_executable(env_path)
        else:
            # 系统环境
            return sys.executable

    def install_package(self, progress_signal: pyqtSignal, env_name: str, package: str, version: str = None) -> bool:
        """在指定环境中安装包"""
        python_exe = self.get_python_executable(env_name)
        cmd = [python_exe, "-m", "pip", "install"]
        if version:
            cmd.append(f"{package}=={version}")
        else:
            cmd.append(package)

        try:
            # 执行命令并实时捕获输出
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 合并 stderr 到 stdout
                text=True,
                bufsize=1,  # 行缓冲
                universal_newlines=True
            )

            # 实时读取输出
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    # 发送实时进度
                    progress_signal.emit(output.strip())

            # 等待进程结束
            return_code = process.poll()
            if return_code == 0:
                # 更新环境包列表
                self._update_package_list(env_name)
                return True
            else:
                logger.error(f"安装失败: {self.package} {self.operation}")
                return False
        except subprocess.TimeoutExpired:
            logger.error("安装超时")
            return False
        except Exception as e:
            logger.error(f"安装错误: {e}")
            return False

    def uninstall_package(self, progress_signal, env_name: str, package: str) -> bool:
        """在指定环境中卸载包"""
        python_exe = self.get_python_executable(env_name)
        cmd = [python_exe, "-m", "pip", "uninstall", package, "-y"]

        try:
            # 执行命令并实时捕获输出
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 合并 stderr 到 stdout
                text=True,
                bufsize=1,  # 行缓冲
                universal_newlines=True
            )

            # 实时读取输出
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    # 发送实时进度
                    progress_signal.emit(output.strip())

            # 等待进程结束
            return_code = process.poll()
            if return_code == 0:
                # 更新环境包列表
                self._update_package_list(env_name)
                return True
            else:
                logger.error(f"卸载失败")
                return False
        except subprocess.TimeoutExpired:
            logger.error("卸载超时")
            return False
        except Exception as e:
            logger.error(f"卸载错误: {e}")
            return False

    def list_packages(self, env_name: str) -> List[Dict]:
        """列出环境中的包"""
        python_exe = self.get_python_executable(env_name)
        cmd = [python_exe, "-m", "pip", "list", "--format=json"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                packages = json.loads(result.stdout)
                return [{"name": pkg["name"], "version": pkg["version"]} for pkg in packages]
            else:
                logger.error(f"获取包列表失败: {result.stderr}")
                return []
        except subprocess.TimeoutExpired:
            logger.error("获取包列表超时")
            return []
        except Exception as e:
            logger.error(f"获取包列表错误: {e}")
            return []

    def _update_package_list(self, env_name: str):
        """更新环境包列表"""
        if env_name in self.environments:
            packages = self.list_packages(env_name)
            self.environments[env_name]["packages"] = packages
            self._save_environments()

    def export_requirements(self, env_name: str, filepath: str):
        """导出环境的 requirements.txt"""
        python_exe = self.get_python_executable(env_name)
        cmd = [python_exe, "-m", "pip", "freeze"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(result.stdout)
                return True
            else:
                logger.error(f"导出失败: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"导出错误: {e}")
            return False

    def import_requirements(self, env_name: str, filepath: str) -> bool:
        """从 requirements.txt 导入包"""
        python_exe = self.get_python_executable(env_name)
        cmd = [python_exe, "-m", "pip", "install", "-r", filepath]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                # 更新环境包列表
                self._update_package_list(env_name)
                return True
            else:
                logger.error(f"导入失败: {result.stderr}")
                return False
        except subprocess.TimeoutExpired:
            logger.error("导入超时")
            return False
        except Exception as e:
            logger.error(f"导入错误: {e}")
            return False

    def update_package(self, progress_signal, env_name: str, package: str) -> bool:
        """在指定环境中更新包"""
        python_exe = self.get_python_executable(env_name)
        cmd = [python_exe, "-m", "pip", "install", "--upgrade", package]

        try:
            # 执行命令并实时捕获输出
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 合并 stderr 到 stdout
                text=True,
                bufsize=1,  # 行缓冲
                universal_newlines=True
            )

            # 实时读取输出
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    # 发送实时进度
                    progress_signal.emit(output.strip())

            # 等待进程结束
            return_code = process.poll()
            if return_code == 0:
                # 更新环境包列表
                self._update_package_list(env_name)
                return True
            else:
                logger.error(f"更新失败")
                return False
        except subprocess.TimeoutExpired:
            logger.error("更新超时")
            return False
        except Exception as e:
            logger.error(f"更新错误: {e}")
            return False


# 全局环境管理器实例
env_manager = EnvironmentManager()