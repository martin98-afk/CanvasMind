# -*- coding: utf-8 -*-
import hashlib

from PyQt5.QtCore import pyqtSignal, QThread


# --- 工具函数：计算源码MD5 (处理None值) ---
def calculate_md5(text):
    if text is None:
        return ""
    # 统一换行符并去除首尾空格，防止因环境/格式导致的MD5不一致
    clean_text = str(text).replace("\r\n", "\n").strip()
    return hashlib.md5(clean_text.encode('utf-8')).hexdigest()


# --- 异步工作线程 ---
class GenericWorker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
