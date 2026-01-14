# -*- coding: utf-8 -*-
import re
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PyQt5.QtCore import Qt, QSize, QUrl, pyqtSignal
from Qt import QtWidgets
from loguru import logger

from app.widgets.node_widget.base import CustomNodeBaseWidget

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
    HAS_WEBENGINE = True
except ImportError:
    QWebEngineView = None
    HAS_WEBENGINE = False
    from Qt import QtWidgets
    logger.error("警告: QtWebEngine not available. Chart will not render.")


class HtmlWidget(QtWidgets.QWidget):
    valueChanged = pyqtSignal(str)
    sizeHintChanged = pyqtSignal()

    def __init__(self, parent=None, default_html=""):
        super().__init__(parent)
        # 初始化 HTML 内容
        self._html = default_html or "<center>等待图表...</center>"

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if HAS_WEBENGINE:
            self.view = QWebEngineView(self)
            # 允许背景透明
            self.view.setAttribute(Qt.WA_TranslucentBackground)
            self.view.page().setBackgroundColor(Qt.transparent)
            self.view.setContextMenuPolicy(Qt.NoContextMenu)
            layout.addWidget(self.view)
            # 初始加载
            self.view.setHtml(self._html, QUrl("https://chart.local/"))
        else:
            self.fallback = QtWidgets.QLabel("需 QtWebEngine 支持图表")
            self.fallback.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.fallback)

    def set_value(self, html: str):
        """修复：确保更新了内容并重新加载"""
        new_html = str(html) if html is not None else ""
        if new_html == self._html:
            return

        self._html = new_html  # 必须更新成员变量

        if HAS_WEBENGINE:
            # 修复：使用传入的 new_html 而不是旧的 self._html
            self.view.setHtml(self._html, QUrl("https://chart.local/"))

            # 根据内容动态调整 WebEngineView 的最小尺寸
            content_w, content_h = self._extract_size_from_html(self._html)
            self.view.setMinimumSize(content_w, content_h)

        self.sizeHintChanged.emit()
        self.valueChanged.emit(self._html)

    def _extract_size_from_html(self, html: str):
        """从 HTML 提取尺寸，增加容错"""
        width_match = re.search(r'width\s*:\s*(\d+)px', html, re.IGNORECASE)
        height_match = re.search(r'height\s*:\s*(\d+)px', html, re.IGNORECASE)

        width = int(width_match.group(1)) if width_match else 200
        height = int(height_match.group(1)) if height_match else 150
        # 添加内边距（避免贴边）
        padding_w = 20
        padding_h = 20  # 标题栏高度
        return width + padding_w, height + padding_h

    def get_value(self) -> str:
        return self._html

    def sizeHint(self):
        w, h = self._extract_size_from_html(self._html)
        return QSize(w, h)


class HtmlWidgetWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", default="", window=None):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET)
        self.set_name(name)
        widget = HtmlWidget(default_html=default, parent=window)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)
        # ✅ 监听尺寸请求
        widget.sizeHintChanged.connect(self._update_node)

    def _update_node(self):
        if self.node.graph is not None:
            self.node.view.set_proxy_mode(False)
            self.node.view.draw_node()

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value: str):
        self.get_custom_widget().set_value(value)