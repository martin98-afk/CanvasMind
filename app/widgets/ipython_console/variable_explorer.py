import base64
import os
import pickle
import tempfile
import uuid
import time
from loguru import logger
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from spyder.widgets.collectionseditor import CollectionsEditorWidget
from spyder.plugins.variableexplorer.widgets.namespacebrowser import NamespaceBrowser

from app.widgets.basic_widget.style_sheet import StyleSheet


class VariableExplorerCore:
    """变量浏览器核心逻辑，不依赖具体GUI组件"""

    def __init__(self, kernel_manager=None):
        self.kernel_manager = kernel_manager
        self._last_snapshot_hash = None
        self._last_variables = {}
        self._temp_file = None
        self._failed_attempts = 0
        self._last_success_time = time.time()
        self._max_failed_attempts = 10  # 最大失败次数后重启kernel
        self._last_refresh_time = 0
        self._refresh_interval = 0.5  # 防止频繁刷新

    def set_kernel_manager(self, kernel_manager):
        """设置内核管理器"""
        self.kernel_manager = kernel_manager
        self._failed_attempts = 0  # 重置失败计数

    def refresh_variables(self):
        """刷新变量（核心逻辑）"""
        current_time = time.time()
        # 防止过于频繁的刷新
        if current_time - self._last_refresh_time < self._refresh_interval:
            return None

        if not self.kernel_manager or not self.kernel_manager.kernel_client:
            self._failed_attempts += 1
            if self._failed_attempts >= self._max_failed_attempts:
                logger.warning("连续获取变量失败，准备重启kernel")
                self.reset_failure_count()
                return "RESTART_KERNEL"
            return None

        # 检查kernel是否活跃
        if not self.kernel_manager.is_alive():
            self._failed_attempts += 1
            if self._failed_attempts >= self._max_failed_attempts:
                logger.warning("Kernel不活跃，准备重启")
                return "RESTART_KERNEL"
            return None

        try:
            # 生成临时文件路径
            self._temp_file = os.path.join(
                tempfile.gettempdir(),
                f"spyder_vars_{uuid.uuid4().hex}.pkl"
            )

            # 执行代码获取变量
            code = f'''
import pickle
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os
from PIL import Image
from collections import OrderedDict

# 获取所有非内置、非函数、非类型的变量，并且可序列化
_snapshot = OrderedDict()
locals = globals().copy()
for _k, _v in locals.items():
    if (not _k.startswith('_') and 
            not callable(_v) and 
            not isinstance(_v, type) and (
            # 基础类型
            _v is None or
            isinstance(_v, (bool, int, float, complex, str, bytes)) or
            # 容器
            isinstance(_v, (list, tuple, set, frozenset, dict)) or
            # NumPy
            isinstance(_v, (np.ndarray, np.generic)) or
            # Pandas
            isinstance(_v, (pd.DataFrame, pd.Series)) or
            # Image
            isinstance(_v, Image.Image) or
            # Matplotlib
            isinstance(_v, (plt.Figure, plt.Axes)) or
            # 忽略文件
            isinstance(_v, (os.PathLike, os.DirEntry))
        )):
        try:
            pickle.dumps(_v, protocol=pickle.HIGHEST_PROTOCOL)
            _snapshot[_k] = _v
        except Exception as e:
            pass

# 保存到临时文件
try:
    with open(r"{self._temp_file}", "wb") as f:
        pickle.dump(_snapshot, f)
except Exception as e:
    print(f"Error saving variables: {{e}}")  # 错误信息
'''

            self.kernel_manager.execute_code(code, hidden=True)
            self._last_refresh_time = current_time
            self._failed_attempts = 0  # 重置失败计数
            self._last_success_time = current_time
            return self._temp_file

        except Exception as e:
            logger.error(f"刷新变量时发生错误: {e}")
            self._failed_attempts += 1
            if self._failed_attempts >= self._max_failed_attempts:
                logger.warning("连续获取变量失败，准备重启kernel")
                return "RESTART_KERNEL"
            return None

    def load_variables_from_file(self, temp_file_path):
        """从临时文件加载变量（核心逻辑）"""
        if temp_file_path == "RESTART_KERNEL":
            return "RESTART_KERNEL"

        try:
            if os.path.exists(temp_file_path):
                with open(temp_file_path, 'rb') as f:
                    data = pickle.load(f)

                # 检查数据是否有变化
                def safe_hashable_repr(value):
                    try:
                        return base64.b64encode(
                            pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
                        ).decode('utf-8')
                    except Exception:
                        return f"{type(value)}@{id(value)}"

                current_hash_data = {k: safe_hashable_repr(v) for k, v in data.items()}
                current_data_hash = hash(str(sorted(current_hash_data.items())))

                if current_data_hash == self._last_snapshot_hash:
                    return None  # 数据没有变化

                self._last_snapshot_hash = current_data_hash
                self._last_variables = data

                # 安全删除临时文件
                try:
                    os.remove(temp_file_path)
                except OSError:
                    pass  # 文件可能已被删除

                self._failed_attempts = 0  # 重置失败计数
                self._last_success_time = time.time()
                return data
            else:
                logger.warning(f"临时文件不存在: {temp_file_path}")
                self._failed_attempts += 1
                return None
        except Exception as e:
            logger.error(f"加载变量失败: {e}")
            self._failed_attempts += 1
            return None

    def get_current_variables(self):
        """获取当前缓存的变量"""
        return self._last_variables.copy()

    def should_restart_kernel(self):
        """检查是否需要重启kernel"""
        current_time = time.time()
        # 如果长时间没有成功获取变量，或者失败次数过多
        if (self._failed_attempts >= self._max_failed_attempts or
                (current_time - self._last_success_time > 30 and self._failed_attempts > 1)):  # 30秒内失败超过1次
            return True
        return False

    def reset_failure_count(self):
        """重置失败计数"""
        self._failed_attempts = 0
        self._last_success_time = time.time()


class VariableExplorerWidget(QWidget):
    """GUI变量浏览器组件"""

    def __init__(self, parent=None, kernel_manager=None):
        super().__init__(parent)
        self.setMinimumWidth(300)
        self.kernel_manager = kernel_manager
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # 创建变量浏览器核心
        self.core = VariableExplorerCore(kernel_manager)

        # 初始空数据
        self.collection_widget = CollectionsEditorWidget(
            self, data={}, namespacebrowser=NamespaceBrowser(self)
        )
        StyleSheet.VARIABLE_EXPLORER.apply(self.collection_widget.editor)
        self.layout.addWidget(self.collection_widget.editor)

        # 定时器用于自动刷新
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self.refresh_variables)
        self.auto_refresh_timer.setInterval(1000)

        # kernel重启检查定时器
        self.kernel_check_timer = QTimer(self)
        self.kernel_check_timer.timeout.connect(self._check_kernel_status)
        self.kernel_check_timer.setInterval(5000)  # 每5秒检查一次kernel状态

    def set_kernel_manager(self, kernel_manager):
        """设置内核管理器"""
        self.core.set_kernel_manager(kernel_manager)

    def refresh_variables(self):
        """刷新变量显示"""
        result = self.core.refresh_variables()

        if result == "RESTART_KERNEL":
            self._request_kernel_restart()
        elif result:
            # 延迟加载结果，避免阻塞
            QTimer.singleShot(300, lambda: self._update_display(result))

    def _update_display(self, temp_file):
        """更新显示"""
        try:
            data = self.core.load_variables_from_file(temp_file)

            if data == "RESTART_KERNEL":
                self._request_kernel_restart()
            elif data is not None:
                # 在主线程中更新UI
                self.collection_widget.set_data(data)
                self.collection_widget.editor.resizeRowsToContents()
                self.collection_widget.editor.resize_column_contents()
        except Exception as e:
            logger.error(f"更新显示时发生错误: {e}")

    def _check_kernel_status(self):
        """检查kernel状态并决定是否重启"""
        if self.core.should_restart_kernel():
            logger.info("检测到kernel异常，准备重启")
            self._request_kernel_restart()

    def _request_kernel_restart(self):
        """请求重启kernel"""
        logger.info("发出kernel重启请求")
        if self.kernel_manager is not None:
            QTimer.singleShot(1000, self.kernel_manager.restart_kernel)

    def start_auto_refresh(self):
        """开始自动刷新"""
        self.auto_refresh_timer.start()
        self.kernel_check_timer.start()

    def stop_auto_refresh(self):
        """停止自动刷新"""
        self.auto_refresh_timer.stop()
        self.kernel_check_timer.stop()

    def refresh_variables_manually(self):
        """手动刷新变量"""
        self.refresh_variables()

    def reset_kernel_failure_count(self):
        """重置kernel失败计数（在kernel重启成功后调用）"""
        self.core.reset_failure_count()