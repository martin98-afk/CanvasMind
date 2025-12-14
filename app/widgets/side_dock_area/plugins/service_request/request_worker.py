# -*- coding: utf-8 -*-
import requests
from PyQt5.QtCore import QObject, pyqtSignal, QRunnable


class RequestSignals(QObject):
    success = pyqtSignal(object)
    error = pyqtSignal(str)


class RequestWorker(QRunnable):
    def __init__(self, url, payload, timeout=30):
        super().__init__()
        self.url = url
        self.payload = payload
        self.timeout = timeout
        self.signals = RequestSignals()

    def run(self):
        try:
            response = requests.post(self.url, json=self.payload, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            self.signals.success.emit(result)
        except Exception as e:
            if isinstance(e, requests.exceptions.Timeout):
                msg = "请求超时，请检查网络或服务状态。"
            elif isinstance(e, requests.exceptions.ConnectionError):
                msg = "无法连接到服务，请确认服务是否运行。"
            elif isinstance(e, requests.exceptions.HTTPError):
                msg = f"HTTP 错误: {e.response.status_code} - {e.response.reason}"
            elif isinstance(e, ValueError):
                msg = "服务返回了无效的 JSON 格式。"
            else:
                msg = f"未知错误: {str(e)}"
            self.signals.error.emit(msg)