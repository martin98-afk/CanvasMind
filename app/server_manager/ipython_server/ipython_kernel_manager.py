import os
import uuid

from loguru import logger


class IPythonKernelManager:
    """纯IPython内核管理器，不依赖GUI组件"""

    def __init__(self, python_exe_path=None):
        self.python_exe_path = python_exe_path
        self.kernel_manager = None
        self.kernel_client = None
        self.connection_file = None

    def start_kernel(self, python_exe_path=None):
        import os
        if python_exe_path:
            self.python_exe_path = python_exe_path

        # Windows: 确保使用 python.exe 而非 pythonw.exe
        if os.name == 'nt' and self.python_exe_path and self.python_exe_path.endswith('pythonw.exe'):
            self.python_exe_path = self.python_exe_path.replace('pythonw.exe', 'python.exe')

        if not self.python_exe_path or not os.path.exists(self.python_exe_path):
            raise ValueError(f"Python解释器路径不存在: {self.python_exe_path}")

        self.shutdown_kernel()

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

    def shutdown_kernel(self):
        """关闭内核"""
        if self.kernel_client:
            try:
                self.kernel_client.stop_channels()
            except Exception:
                pass
        if self.kernel_manager:
            try:
                self.kernel_manager.shutdown_kernel(now=True)
            except Exception:
                pass
        self.kernel_client = None
        self.kernel_manager = None

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
        self.shutdown_kernel()


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
