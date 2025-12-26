# -*- coding: utf-8 -*-
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QSizePolicy
from Qt import QtWidgets, QtCore
from loguru import logger

from app.widgets.node_widget.base import CustomNodeBaseWidget

# ✅ 关键：导入 QWebEngineView
try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
    HAS_WEBENGINE = True
except ImportError:
    QWebEngineView = None
    HAS_WEBENGINE = False
    from Qt import QtWidgets
    logger.error("警告: QtWebEngine not available. Chart will not render.")


class ChartWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(str)

    def __init__(self, parent=None, default_html=""):
        super().__init__(parent)
        self._html = default_html or "<center>等待图表...</center>"
        self.setStyleSheet("background-color: transparent; border: none;")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if HAS_WEBENGINE:
            self.view = QWebEngineView(self)
            self.view.setAttribute(Qt.WA_TranslucentBackground)
            self.view.page().setBackgroundColor(Qt.transparent)
            self.view.setContextMenuPolicy(Qt.NoContextMenu)
            self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            # ✅ 移除 maximumSize 限制！
            self.view.setMinimumSize(720, 520)  # 图表 700x500 + 边距
            self.view.setMaximumSize(720, 520)  # ← 也可以设最大值，避免拉伸失真
            self.view.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding,
                QtWidgets.QSizePolicy.Expanding
            )
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
        self._html = html or "<center>无数据</center>"
        if HAS_WEBENGINE:
            self.view.setHtml(self._html, QtCore.QUrl("https://chart.local/"))
        self.valueChanged.emit(self._html)

    def get_value(self) -> str:
        return self._html

    def sizeHint(self):
        # 返回一个“推荐”尺寸，供节点布局参考
        return QtCore.QSize(720, 520)  # 推荐默认尺寸


class ChartWidgetWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", label="", default="", window=None):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET)
        self.set_name(name)
        widget = ChartWidget(default_html=default)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value: str):
        self.get_custom_widget().set_value(value)