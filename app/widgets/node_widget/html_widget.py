# -*- coding: utf-8 -*-
import re
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PyQt5.QtCore import Qt
from Qt import QtWidgets, QtCore
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
    valueChanged = QtCore.Signal(str)
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None, default_html=""):
        super().__init__(parent)
        self._html = default_html or "<center>等待图表...</center>"
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if HAS_WEBENGINE:
            self.view = QWebEngineView(self)
            self.view.setAttribute(Qt.WA_TranslucentBackground)
            self.view.page().setBackgroundColor(Qt.transparent)
            self.view.setContextMenuPolicy(Qt.NoContextMenu)
            layout.addWidget(self.view)
            self.set_value(self._html)
        else:
            self.fallback = QtWidgets.QLabel("需 QtWebEngine 支持图表")
            self.fallback.setAlignment(QtCore.Qt.AlignCenter)
            self.fallback.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding,
                QtWidgets.QSizePolicy.Expanding
            )
            layout.addWidget(self.fallback)

    def set_value(self, html: str):
        self._html = html or ""
        if HAS_WEBENGINE:
            self.view.setHtml(self._html, QtCore.QUrl("https://chart.local/"))
            content_w, content_h = self._extract_size_from_html(html)
            self.view.setMinimumSize(content_w, content_h)
        self.updateGeometry()
        self.sizeHintChanged.emit()
        self.valueChanged.emit(self._html)

    def _extract_size_from_html(self, html: str):
        """从 HTML 中提取 style="width:...px;height:...px" 的尺寸"""
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
        # 注意：sizeHint 在初次布局时使用，但后续会被真实尺寸覆盖
        w, h = self._extract_size_from_html(self._html)
        return QtCore.QSize(w, h)


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