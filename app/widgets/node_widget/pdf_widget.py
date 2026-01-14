# -*- coding: utf-8 -*-
import os
from PyQt5.QtCore import Qt, QUrl
from Qt import QtWidgets, QtCore
from loguru import logger

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings

    HAS_WEBENGINE = True
except ImportError:
    QWebEngineView = None
    HAS_WEBENGINE = False
    logger.error("警告: QtWebEngine 不可用，无法预览 PDF。")


class PdfWidget(QtWidgets.QWidget):
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # 默认显示大小
        self._current_size = QtCore.QSize(400, 500)

        if HAS_WEBENGINE:
            self.view = QWebEngineView(self)

            # --- 关键设置：开启 PDF 支持 ---
            settings = self.view.settings()
            settings.setAttribute(QWebEngineSettings.PluginsEnabled, True)
            settings.setAttribute(QWebEngineSettings.PdfViewerEnabled, True)
            settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)

            # --- 关键设置：PDF 预览不能使用透明背景，否则会白屏或黑屏 ---
            self.view.page().setBackgroundColor(Qt.white)  # 设为白色背景

            self.layout.addWidget(self.view)
        else:
            self.fallback = QtWidgets.QLabel("环境缺少 QtWebEngine 支持")
            self.fallback.setAlignment(QtCore.Qt.AlignCenter)
            self.layout.addWidget(self.fallback)

    def set_value(self, file_path):
        """支持传入文件路径"""
        if not HAS_WEBENGINE:
            return

        if not file_path or not isinstance(file_path, str) or not os.path.exists(file_path):
            self.view.setUrl(QUrl("about:blank"))
            self._current_size = QtCore.QSize(200, 150)
            self.setFixedSize(self._current_size)
        else:
            # 必须使用绝对路径并转为 QUrl
            abs_path = os.path.abspath(file_path)
            file_url = QUrl.fromLocalFile(abs_path)

            # PDF 渲染通常需要较大的显示空间
            self._current_size = QtCore.QSize(500, 600)
            self.setFixedSize(self._current_size)

            # 使用 setUrl 而不是 setHtml
            self.view.setUrl(file_url)

        self.sizeHintChanged.emit()

    def sizeHint(self):
        return self._current_size