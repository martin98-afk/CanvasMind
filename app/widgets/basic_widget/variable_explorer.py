import base64
import os
import pickle
import tempfile
import uuid
from loguru import logger
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from spyder.widgets.collectionseditor import CollectionsEditorWidget
from spyder.plugins.variableexplorer.widgets.namespacebrowser import NamespaceBrowser


class VariableExplorerCore:
    """变量浏览器核心逻辑，不依赖具体GUI组件"""
    
    def __init__(self, kernel_manager=None):
        self.kernel_manager = kernel_manager
        self._last_snapshot_hash = None
        self._last_variables = {}
        self._temp_file = None
    
    def set_kernel_manager(self, kernel_manager):
        """设置内核管理器"""
        self.kernel_manager = kernel_manager
    
    def refresh_variables(self):
        """刷新变量（核心逻辑）"""
        if not self.kernel_manager or not self.kernel_manager.kernel_client:
            return None
        
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
with open(r"{self._temp_file}", "wb") as f:
    pickle.dump(_snapshot, f)
'''
        
        self.kernel_manager.execute_code(code, hidden=True)
        return self._temp_file
    
    def load_variables_from_file(self, temp_file_path):
        """从临时文件加载变量（核心逻辑）"""
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
                
                os.remove(temp_file_path)
                return data
            else:
                logger.error("临时文件不存在")
                return None
        except Exception as e:
            logger.error(f"加载变量失败: {e}")
            return None
    
    def get_current_variables(self):
        """获取当前缓存的变量"""
        return self._last_variables.copy()


class VariableExplorerWidget(QWidget):
    """GUI变量浏览器组件"""
    
    def __init__(self, parent=None, kernel_manager=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # 深色 QSS
        dark_qss = """
        CollectionsEditorTableView {
            background-color: #19232D;
            color: #FFFFFF;
            alternate-background-color: #1A2029;
            gridline-color: #32414B;
            selection-background-color: #3D5DAE;
            selection-color: #FFFFFF;
        }
        QDialog, QWidget {
            background-color: #19232D;
            color: #FFFFFF;
        }
        QHeaderView::section {
            background-color: #262F3A;
            color: #FFFFFF;
            padding: 4px;
            border: 1px solid #32414B;
        }
        QTableView::item {
            padding: 4px;
        }
        """
        
        # 创建变量浏览器核心
        self.core = VariableExplorerCore(kernel_manager)
        
        # 初始空数据
        self.collection_widget = CollectionsEditorWidget(
            self, data={}, namespacebrowser=NamespaceBrowser(self)
        )
        self.collection_widget.editor.setStyleSheet(dark_qss)
        self.layout.addWidget(self.collection_widget.editor)
        
        # 定时器用于自动刷新
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self.refresh_variables)
        self.auto_refresh_timer.setInterval(1000)
    
    def set_kernel_manager(self, kernel_manager):
        """设置内核管理器"""
        self.core.set_kernel_manager(kernel_manager)
    
    def refresh_variables(self):
        """刷新变量显示"""
        temp_file = self.core.refresh_variables()
        if temp_file:
            # 延迟加载结果
            QTimer.singleShot(300, lambda: self._update_display(temp_file))
    
    def _update_display(self, temp_file):
        """更新显示"""
        data = self.core.load_variables_from_file(temp_file)
        if data is not None:
            self.collection_widget.set_data(data)
            self.collection_widget.editor.resizeRowsToContents()
            self.collection_widget.editor.resize_column_contents()
    
    def start_auto_refresh(self):
        """开始自动刷新"""
        self.auto_refresh_timer.start()
    
    def stop_auto_refresh(self):
        """停止自动刷新"""
        self.auto_refresh_timer.stop()
    
    def refresh_variables_manually(self):
        """手动刷新变量"""
        self.refresh_variables()