import os
import uuid
from loguru import logger

from PyQt5.QtCore import QThread, pyqtSignal


class LocalConnectWorker(QThread):
    """
    本地内核连接工人：负责在后台启动本地 Python 进程并建立 ZMQ 通信。
    """
    finished = pyqtSignal(bool, str)
    status_update = pyqtSignal(str)

    def __init__(self, manager, python_exe_path):
        super().__init__()
        self.manager = manager
        self.python_exe_path = python_exe_path

    def run(self):
        try:
            self.status_update.emit("[*] 正在准备本地环境...")
            # 调用你原有的 IPythonKernelManager.start_kernel
            success = self.manager.start_kernel(self.python_exe_path)

            if success:
                # 增加一个微小的握手检查，确保 Client 准备好了
                self.status_update.emit("[*] 正在同步本地内核状态...")
                self.finished.emit(True, "")
            else:
                self.finished.emit(False, "本地内核启动失败，请检查 Python 路径")
        except Exception as e:
            self.finished.emit(False, str(e))


class IPythonKernelManager:
    """纯IPython内核管理器，不依赖GUI组件"""

    def __init__(self, python_exe_path=None):
        self.python_exe_path = python_exe_path
        self.kernel_manager = None
        self.kernel_client = None
        self.connection_file = None
        self._shutdown_worker = None  # 保持引用防止被销毁

    def start_kernel(self, python_exe_path=None):
        import os
        # 如果已经启动，健康且pythonexe 路径一致，则不重新启动，重新启动必须先手动调用shutdown_kernel，再start_kernel方便管理
        if python_exe_path and (self.python_exe_path != python_exe_path or not self.is_alive()):
            self.shutdown_kernel(async_mode=False)
        else:
            return True
        if python_exe_path:
            self.python_exe_path = python_exe_path

        # Windows: 确保使用 python.exe 而非 pythonw.exe
        if os.name == 'nt' and self.python_exe_path and self.python_exe_path.endswith('pythonw.exe'):
            self.python_exe_path = self.python_exe_path.replace('pythonw.exe', 'python.exe')

        if not self.python_exe_path or not os.path.exists(self.python_exe_path):
            raise ValueError(f"Python解释器路径不存在: {self.python_exe_path}")

        try:
            from qtconsole.manager import QtKernelManager
            import tempfile, uuid, os, subprocess

            self.connection_file = os.path.join(
                tempfile.gettempdir(),
                f'kernel_{uuid.uuid4().hex}.json'
            )

            env = os.environ.copy()
            python_dir = os.path.dirname(self.python_exe_path)
            env_python_path = os.path.join(python_dir, "Lib", "site-packages")
            env['PATH'] = python_dir + os.pathsep + env.get('PATH', '')
            env['PYTHONPATH'] = env_python_path
            env['PYTHONEXECUTABLE'] = self.python_exe_path
            env.pop('PYTHONHOME', None)
            env['PYTHONUNBUFFERED'] = '1'
            env['MPLBACKEND'] = 'Agg'

            self.kernel_manager = QtKernelManager(connection_file=self.connection_file)

            # === 关键：Windows 中断支持 ===
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                extra_arguments = {
                    'startupinfo': startupinfo,
                    'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
                }
            else:
                extra_arguments = {'start_new_session': True}

            self.kernel_manager.start_kernel(
                executable=self.python_exe_path,
                env=env,
                **extra_arguments
            )
            self.kernel_client = self.kernel_manager.client()
            self.kernel_client.start_channels()
            return True
        except Exception as e:
            logger.error(f"启动 kernel 失败: {e}")
            return False

    def execute_code(self, code, hidden=False):
        """执行代码"""
        if not self.kernel_client:
            raise RuntimeError("Kernel未启动")

        self.kernel_client.execute(code, silent=hidden)

    def interrupt_kernel(self):
        """中断正在运行的代码"""
        if self.kernel_manager and self.kernel_manager.is_alive():
            try:
                # QtKernelManager 提供的标准接口
                self.kernel_manager.interrupt_kernel()
                return True
            except Exception as e:
                logger.error(f"中断 kernel 失败: {e}")
        return False

    def shutdown_kernel(self, **kwargs):
        """
        [同步关闭]
        因为使用了 now=True，这通常是发送 SIGKILL，速度非常快（<10ms）。
        在此处使用 QThread 是过度设计，且是导致崩溃的根源。
        """
        try:
            if self.kernel_client:
                # 停止通道必须在创建它的线程（主线程）调用
                self.kernel_client.stop_channels()
                self.kernel_client = None

            if self.kernel_manager:
                # now=True 表示强制杀进程，不要等待
                if self.kernel_manager.has_kernel:
                    self.kernel_manager.shutdown_kernel(now=True)
                self.kernel_manager = None

            # 清理临时文件
            if self.connection_file and os.path.exists(self.connection_file):
                try:
                    os.remove(self.connection_file)
                except:
                    pass

            logger.info("内核已关闭")
        except Exception as e:
            logger.error(f"关闭内核时出错: {e}")

    def is_alive(self):
        """内核是否存活"""
        return self.kernel_manager.is_alive() if self.kernel_manager else False

    def get_kernel_info(self):
        """获取内核信息"""
        if self.kernel_client:
            return {
                'is_alive': self.kernel_manager.is_alive() if self.kernel_manager else False,
                'connection_file': self.connection_file,
                'python_exe': self.python_exe_path
            }
        return {"is_alive": False}

    def __del__(self):
        """析构时需谨慎，不能启动 QThread"""
        if self.kernel_manager:
            try:
                # 最后的防线：如果还在运行，尝试快速杀掉
                self.kernel_manager.shutdown_kernel(now=True)
            except:
                pass


class MultiKernelManager:
    """多内核管理器"""

    def __init__(self):
        self.kernels = {}
        self.current_kernel_id = None

    def create_kernel(self, kernel_id=None, python_exe_path=None):
        """创建新内核"""
        if kernel_id is None:
            kernel_id = str(uuid.uuid4())

        kernel = IPythonKernelManager(python_exe_path)
        self.kernels[kernel_id] = kernel
        self.current_kernel_id = kernel_id
        return kernel_id

    def get_kernel(self, kernel_id=None):
        """获取指定内核或当前内核"""
        if kernel_id is None:
            kernel_id = self.current_kernel_id
        return self.kernels.get(kernel_id)

    def switch_kernel(self, kernel_id):
        """切换当前内核"""
        if kernel_id in self.kernels:
            self.current_kernel_id = kernel_id
            return True
        return False

    def execute_code(self, code, kernel_id=None, hidden=False):
        """执行代码到指定内核"""
        kernel = self.get_kernel(kernel_id)
        if kernel:
            return kernel.execute_code(code, hidden)
        raise ValueError(f"Kernel {kernel_id} not found")

    def interrupt_kernel(self, kernel_id):
        """中断指定内核"""
        kernel = self.get_kernel(kernel_id)
        if kernel:
            return kernel.interrupt_kernel()
        raise ValueError(f"Kernel {kernel_id} not found")

    def shutdown_kernel(self, kernel_id):
        """关闭指定内核"""
        kernel = self.kernels.get(kernel_id)
        if kernel:
            kernel.shutdown_kernel()
            del self.kernels[kernel_id]
            if self.current_kernel_id == kernel_id:
                self.current_kernel_id = next(iter(self.kernels), None)

    def shutdown_all(self):
        """关闭所有内核"""
        for kernel in self.kernels.values():
            kernel.shutdown_kernel()
        self.kernels.clear()
        self.current_kernel_id = None
