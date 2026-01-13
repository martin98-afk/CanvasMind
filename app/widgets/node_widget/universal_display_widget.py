# -*- coding: utf-8 -*-
import os
import numpy as np
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PIL import Image
from Qt import QtWidgets, QtCore

from .base import CustomNodeBaseWidget
from .html_widget import HtmlWidget
from .image_compare_widget import ImageCompareWidget
from .image_widget import ImageWidget
from app.widgets.node_widget.media_widget import VideoPlayWidget, AudioPlayWidget


class UniversalDisplayWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(object)
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QtWidgets.QStackedWidget()
        self.layout.addWidget(self.stack)

        # 缓存实例，实现延迟加载 { "type_name": widget_instance }
        self._view_cache = {}

        # 注册显示策略配置
        # priority: 优先级，越小越先匹配
        self._strategies = [
            {"id": "compare", "class": ImageCompareWidget, "check": self._is_compare_data, "priority": 1},
            {"id": "image", "class": ImageWidget, "check": self._is_image_data, "priority": 2},
            {"id": "video", "class": VideoPlayWidget, "check": self._is_video_path, "priority": 3},
            {"id": "audio", "class": AudioPlayWidget, "check": self._is_audio_path, "priority": 4},
            {"id": "html", "class": HtmlWidget, "check": lambda x: isinstance(x, str), "priority": 99},
        ]

    # --- 数据类型判断逻辑 (策略) ---
    def _is_compare_data(self, value):
        return isinstance(value, (list, tuple)) and len(value) >= 2 and self._is_image_data(value[0])

    def _is_image_data(self, value):
        if isinstance(value, (np.ndarray, Image.Image)): return True
        if isinstance(value, str):
            ext = os.path.splitext(value)[1].lower()
            return ext in ['.jpg', '.jpeg', '.png', '.bmp', '.webp']
        return False

    def _is_video_path(self, value):
        if not isinstance(value, str) or not os.path.exists(value): return False
        return os.path.splitext(value)[1].lower() in ['.mp4', '.avi', '.mov', '.mkv']

    def _is_audio_path(self, value):
        if not isinstance(value, str) or not os.path.exists(value): return False
        return os.path.splitext(value)[1].lower() in ['.mp3', '.wav', '.ogg', '.flac']

    # --- 核心调度逻辑 ---
    def _get_or_create_view(self, strategy_id, widget_class):
        """根据 ID 延迟实例化控件"""
        if strategy_id not in self._view_cache:
            widget = widget_class(self.parent())
            self.stack.addWidget(widget)
            # 统一绑定尺寸变化信号
            if hasattr(widget, 'sizeHintChanged'):
                widget.sizeHintChanged.connect(self.sizeHintChanged.emit)
            self._view_cache[strategy_id] = widget
        return self._view_cache[strategy_id]

    def set_value(self, value):
        # 1. 处理清空逻辑 (非常重要)
        if value is None or value == "" or value == []:
            # 找到 HTML 视图（作为默认空白页）
            widget = self._get_or_create_view("html", HtmlWidget)
            self.stack.setCurrentWidget(widget)

            # 关键：只重置当前显示的这个，确保它变小
            widget.set_value("<center><small>等待输入...</small></center>")

            self._stop_inactive_media("html")

            # 强制刷新尺寸
            self.updateGeometry()
            self.sizeHintChanged.emit()
            return

        # 2. 正常匹配逻辑
        matched_strategy = None
        for strategy in sorted(self._strategies, key=lambda x: x['priority']):
            if strategy['check'](value):
                matched_strategy = strategy
                break

        if matched_strategy:
            view_id = matched_strategy['id']
            widget = self._get_or_create_view(view_id, matched_strategy['class'])

            # 切换前，如果我们要切换到一个“新”的显示类型，
            # 最好让之前的 Widget 也重置（可选，但能解决你说的“占位”问题）
            # for v in self._view_cache.values():
            #     if v != widget: v.set_value(None)

            self.stack.setCurrentWidget(widget)
            widget.set_value(value)
            self._stop_inactive_media(view_id)

            self.updateGeometry()
            self.sizeHintChanged.emit()

    def _stop_inactive_media(self, active_id):
        """如果切换了页面，停止其他页面的视频/音频，节省 CPU"""
        for v_id, widget in self._view_cache.items():
            if v_id != active_id and hasattr(widget, 'stop'):
                try:
                    widget.stop()
                except:
                    pass

    def play(self):
        """统一播放接口"""
        curr = self.stack.currentWidget()
        if curr and hasattr(curr, 'play'):
            curr.play()

    def sizeHint(self):
        if self.stack.currentWidget():
            return self.stack.currentWidget().sizeHint()
        return QtCore.QSize(200, 150)

    def get_value(self):
        curr = self.stack.currentWidget()
        return curr.get_value() if curr and hasattr(curr, 'get_value') else None


class UniversalWidgetWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", default=None, window=None):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET)
        self.set_name(name)

        widget = UniversalDisplayWidget(window)
        self.set_custom_widget(widget)

        widget.valueChanged.connect(self.on_value_changed)
        widget.sizeHintChanged.connect(self._update_node)
        self._update_timer = QtCore.QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._real_update_node)

    def _update_node(self):
        self._update_timer.start(50)

    def _real_update_node(self):
        if self.node and self.node.graph is not None:
            self.node.view.set_proxy_mode(False)
            self.node.view.draw_node()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)
        # 设置值后也要触发重绘
        self._update_node()

    def get_value(self):
        return self.get_custom_widget().get_value()