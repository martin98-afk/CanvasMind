# -*- coding: utf-8 -*-
import os
import numpy as np
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PIL import Image
from PyQt5.QtCore import QTimer
from Qt import QtWidgets, QtCore

from app.widgets.node_widget.base import CustomNodeBaseWidget
from .data_table_widget import DataTableWidget
from .html_widget import HtmlWidget
from .image_compare_widget import ImageCompareWidget
from .image_gallery_widget import ImageGalleryWidget
from .image_widget import ImageWidget
from app.widgets.node_widget.display_widgets.media_widget import VideoPlayWidget, AudioPlayWidget
from .json_tree_widget import JsonTreeWidget
from .pdf_widget import PdfWidget


class UniversalDisplayWidget(QtWidgets.QWidget):
    """多功能可视化插件，现支持图像对比、图像展示、语音播放、视频播放、html渲染等功能"""
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
            # 1. 优先处理多图 (3张及以上)
            {"id": "gallery", "class": ImageGalleryWidget, "check": self._is_gallery_data, "priority": 1},
            # 2. 处理双图对比
            {"id": "compare", "class": ImageCompareWidget, "check": self._is_compare_data, "priority": 2},
            # 3. 处理 PDF
            {"id": "pdf", "class": PdfWidget, "check": self._is_pdf_path, "priority": 3},
            # 4. 单张图
            {"id": "image", "class": ImageWidget, "check": self._is_image_data, "priority": 4},
            # 5. 视频
            {"id": "video", "class": VideoPlayWidget, "check": self._is_video_path, "priority": 5},
            # 6. 音频
            {"id": "audio", "class": AudioPlayWidget, "check": self._is_audio_path, "priority": 6},
            # 7. 表格
            {"id": "table", "class": DataTableWidget, "check": self._is_table_data, "priority": 7},
            # 8. json
            {"id": "json", "class": JsonTreeWidget, "check": self._is_json_data, "priority": 8},
            # 9. html
            {"id": "html", "class": HtmlWidget, "check": lambda x: isinstance(x, str), "priority": 99},
        ]

    # --- 数据类型判断逻辑 (策略) ---
    def _is_gallery_data(self, value):
        """判断是否为 3 张及以上的图像列表"""
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            # 检查第一个元素是否是图像
            return self._is_image_data(value[0])
        return False

    def _is_pdf_path(self, value):
        """判断是否为 PDF 路径"""
        if isinstance(value, str) and value.lower().endswith('.pdf'):
            # 路径可以不存在（为了加载工作流时的健壮性），由 Widget 内部处理不存在的情况
            return True
        return False

    # 只处理正好 2 张图
    def _is_compare_data(self, value):
        return isinstance(value, (list, tuple)) and len(value) == 2 and self._is_image_data(value[0])

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

    def _is_table_data(self, value):
        # 如果是列表且元素是字典，判定为表格
        return isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict)

    def _is_json_data(self, value):
        # 字典或者是普通列表
        return isinstance(value, (dict, list))
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
        # 1. 处理清空逻辑
        if value is None or value == "" or (isinstance(value, list) and len(value) == 0):
            # 遍历所有缓存的 Widget，全部重置为 None
            for widget in self._view_cache.values():
                widget.set_value(None)

            self.update()
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
            target_widget = self._get_or_create_view(view_id, matched_strategy['class'])
            for v_id, widget in self._view_cache.items():
                if v_id != view_id:
                    # 将不显示的图片控件设为 None，释放它们的尺寸
                    if isinstance(widget, (ImageWidget, ImageCompareWidget, ImageGalleryWidget)):
                        widget.set_value(None)

            self.stack.setCurrentWidget(target_widget)
            target_widget.set_value(value)

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
        self.set_label_visible(False)
        widget = UniversalDisplayWidget(window)
        self.set_custom_widget(widget)

        widget.valueChanged.connect(self.on_value_changed)
        widget.sizeHintChanged.connect(self._sync_node_geometry)

    def _sync_node_geometry(self):
        """
        同步节点大小的核心函数
        """
        if not self.node or not self.node.view:
            return

        view = self.node.view
        # 确保不处于 Proxy 模式（LOD）
        view.set_proxy_mode(False)

        # 1. 强制让 Qt 重新计算内部 Widget 的布局
        widget = self.get_custom_widget()
        if widget:
            widget.adjustSize()

        # 这里使用 fit_to_content，效果是：图片变大，节点变大；图片变小，节点自动缩回。
        if hasattr(view, 'update_layout'):
            QTimer.singleShot(0, view.update_layout)
        else:
            # 回退方案
            QTimer.singleShot(0, view._draw_node_horizontal)

    def set_value(self, value):
        self.get_custom_widget().set_value(value)

    def get_value(self):
        return self.get_custom_widget().get_value()