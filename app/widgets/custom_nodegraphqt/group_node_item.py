# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
from collections import OrderedDict

from NodeGraphQt.constants import (
    ITEM_CACHE_MODE, PortTypeEnum, Z_VAL_NODE,
    ICON_NODE_BASE, NodeEnum, Z_VAL_BACKDROP
)
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem
from NodeGraphQt.qgraphics.node_text_item import NodeTextItem
from NodeGraphQt.qgraphics.port import CustomPortItem
from qtpy import QtCore, QtGui, QtWidgets

# 尝试导入你的自定义端口
try:
    from app.widgets.custom_nodegraphqt.custom_port_item import GlowPortItem
except ImportError:
    GlowPortItem = CustomPortItem


class ToggleButton(QtWidgets.QGraphicsItem):
    """左上角的折叠/展开按钮"""

    def __init__(self, parent=None, collapsed=False):
        super(ToggleButton, self).__init__(parent)
        self._collapsed = collapsed
        self.setSize(14, 14)

    def setSize(self, w, h):
        self._width = w
        self._height = h

    def boundingRect(self):
        return QtCore.QRectF(0, 0, self._width, self._height)

    def paint(self, painter, option, widget):
        rect = self.boundingRect()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # 绘制背景圆/框
        painter.setBrush(QtGui.QColor(60, 60, 60))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, 3, 3)

        # 绘制符号 (+ 或 -)
        painter.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200), 2))
        mid_x = rect.width() / 2
        mid_y = rect.height() / 2

        # 横线 (总是画)
        painter.drawLine(QtCore.QPointF(4, mid_y), QtCore.QPointF(rect.width() - 4, mid_y))

        # 竖线 (折叠状态下画，组成 + 号)
        if self._collapsed:
            painter.drawLine(QtCore.QPointF(mid_x, 4), QtCore.QPointF(mid_x, rect.height() - 4))

    def mousePressEvent(self, event):
        # 拦截点击事件，交给父节点处理
        if event.button() == QtCore.Qt.LeftButton:
            self.parentItem().toggle_collapse()


class GroupNodeItem(BackdropNodeItem):
    """
    仿 ComfyUI 组节点：
    - 支持折叠/展开
    - 折叠时显示预览图
    - 拥有输入输出端口
    """

    def __init__(self, name='Group', text='', parent=None):
        self._text_item = None
        self._icon_item = None
        self._input_items = OrderedDict()
        self._output_items = OrderedDict()

        # 新增属性
        self._is_collapsed = False
        self._captured_nodes = []  # 存储被折叠隐藏的节点
        self._expanded_size = (300.0, 300.0)  # 记录展开时的大小
        self._preview_pixmap = None
        self._preview_item = None
        self._toggle_btn = None

        super(GroupNodeItem, self).__init__(name=name, text=text, parent=parent)

        # 初始化标题
        self._text_item = NodeTextItem(self.name, self)
        font = QtGui.QFont()
        font.setPointSize(12)  # 稍微调小一点适应折叠态
        font.setBold(True)
        self._text_item.setFont(font)
        self._text_item.setDefaultTextColor(QtGui.QColor("white"))

        # 初始化图标
        self._icon_item = QtWidgets.QGraphicsPixmapItem(self)
        self._icon_item.setTransformationMode(QtCore.Qt.SmoothTransformation)
        self.icon = ICON_NODE_BASE

        # 初始化预览图 Item (默认隐藏)
        self._preview_item = QtWidgets.QGraphicsPixmapItem(self)
        self._preview_item.setTransformationMode(QtCore.Qt.SmoothTransformation)
        self._preview_item.setVisible(False)
        self._preview_item.setZValue(-1)  # 在端口和文字之下，背景之上

        # 初始化折叠按钮
        self._toggle_btn = ToggleButton(self, collapsed=False)
        self._toggle_btn.setPos(5, 5)

        self.setZValue(Z_VAL_BACKDROP)
        self.update_layout()

    # --- 核心功能：折叠与展开 ---

    def toggle_collapse(self):
        """切换状态"""
        self._is_collapsed = not self._is_collapsed
        self._toggle_btn._collapsed = self._is_collapsed
        self._toggle_btn.update()

        if self._is_collapsed:
            self._collapse()
        else:
            self._expand()

        # 强制重绘
        self.update()
        self.update_layout()

    def _collapse(self):
        """执行折叠逻辑"""
        scene = self.scene()
        if not scene:
            return

        # 1. 记录当前尺寸
        self._expanded_size = (self._width, self._height)

        # 2. 捕获内部节点
        # 获取当前 Backdrop 矩形范围内的所有 Item
        rect = self.sceneBoundingRect()
        items = scene.items(rect)

        self._captured_nodes = []
        for item in items:
            if item == self or item.parentItem() == self:
                continue
            # 假设所有节点都继承自 AbstractNodeItem，或者是连接线
            # 这里简单处理：只隐藏 NodeItem，连线通常会自动处理或不需要隐藏
            if isinstance(item, AbstractNodeItem):
                self._captured_nodes.append(item)
                item.setVisible(False)

        # 3. 缩小自身尺寸 (模拟标准节点大小)
        # 这里设置为一个固定大小，或者根据预览图比例调整
        self.width = 240
        self.height = 160

        # 4. 显示预览图
        self._preview_item.setVisible(True)

        # 5. 调整 Z-Value，折叠后像普通节点一样显示在前面?
        # ComfyUI 中 Group 即使折叠通常也在底层，但为了操作方便，可以适当调整
        # 这里保持 BACKDROP 或稍微提高一点
        self.setZValue(Z_VAL_NODE - 1)

    def _expand(self):
        """执行展开逻辑"""
        # 1. 恢复内部节点可见性
        for item in self._captured_nodes:
            if item.scene():  # 确保项目还在场景中
                item.setVisible(True)
        self._captured_nodes = []

        # 2. 隐藏预览图
        self._preview_item.setVisible(False)

        # 3. 恢复尺寸
        w, h = self._expanded_size
        self.width = w
        self.height = h

        # 4. 恢复 Z-Value
        self.setZValue(Z_VAL_BACKDROP)

    # --- 预览图设置 ---

    def set_preview_image(self, image_path_or_pixmap):
        """设置内部预览图"""
        if isinstance(image_path_or_pixmap, str):
            pixmap = QtGui.QPixmap(image_path_or_pixmap)
        elif isinstance(image_path_or_pixmap, QtGui.QPixmap):
            pixmap = image_path_or_pixmap
        else:
            return

        self._preview_pixmap = pixmap
        self._preview_item.setPixmap(pixmap)
        self.update_layout()

    # --- 布局更新 ---

    def update_layout(self):
        if not self._text_item or not self._icon_item:
            return

        header_height = 26.0

        # 1. 折叠按钮位置
        self._toggle_btn.setPos(6, 6)

        # 2. 图标位置 (在按钮右边)
        self._icon_item.setPos(26.0, (header_height - self._icon_item.pixmap().height()) / 2)

        # 3. 标题位置 (居中或靠左)
        text_rect = self._text_item.boundingRect()
        # 如果折叠，文字可能需要截断显示，这里简化处理
        tx = (self._width - text_rect.width()) / 2
        self._text_item.setPos(tx, 1.0)

        # 4. 预览图布局 (填满内容区域)
        if self._is_collapsed and self._preview_item.pixmap():
            # 计算预览图缩放以适应节点 (留出标题栏和边框)
            avail_w = self._width - 4
            avail_h = self._height - header_height - 4

            pm = self._preview_item.pixmap()
            self._preview_item.setPos(2, header_height + 2)

            # 缩放
            scaled_pm = pm.scaled(avail_w, avail_h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            self._preview_item.setPixmap(scaled_pm)

            # 居中放置
            px = (self._width - scaled_pm.width()) / 2
            py = header_height + (avail_h - scaled_pm.height()) / 2
            self._preview_item.setPos(px, py)

        # 5. 端口对齐
        self.align_ports(v_offset=header_height + 5.0)

        # 如果是展开状态，更新调整手柄的位置
        if not self._is_collapsed and self._sizer:
            self._sizer.set_pos(self._width, self._height)
            self._sizer.setVisible(True)
        elif self._is_collapsed and self._sizer:
            self._sizer.setVisible(False)  # 折叠时不显示调整大小的手柄

    # --- 端口相关 (复用你的代码) ---
    def _add_port(self, port):
        text = QtWidgets.QGraphicsTextItem("", self)
        text.setVisible(False)
        text.setCacheMode(ITEM_CACHE_MODE)
        if port.port_type == PortTypeEnum.IN.value:
            self._input_items[port] = text
        elif port.port_type == PortTypeEnum.OUT.value:
            self._output_items[port] = text
        self.update_layout()
        return port

    def add_input(self, name='input', multi_port=False, display_name=True, locked=False, painter_func=None):
        port = CustomPortItem(self, painter_func) if painter_func else GlowPortItem(self)
        port.name = name
        port.port_type = PortTypeEnum.IN.value
        port.multi_connection = multi_port
        port.display_name = display_name
        port.locked = locked
        return self._add_port(port)

    def add_output(self, name='output', multi_port=False, display_name=True, locked=False, painter_func=None):
        port = CustomPortItem(self, painter_func) if painter_func else GlowPortItem(self)
        port.name = name
        port.port_type = PortTypeEnum.OUT.value
        port.multi_connection = multi_port
        port.display_name = display_name
        port.locked = locked
        return self._add_port(port)

    def align_ports(self, v_offset=0.0):
        # 简化的对齐逻辑，确保端口始终附着在左右边缘
        width = self._width
        txt_offset = 4
        spacing = 2

        # 输入端口
        inputs = [p for p in self.inputs if p.isVisible()]
        for i, port in enumerate(inputs):
            h = port.boundingRect().height()
            py = v_offset + i * (h + spacing)
            port.setPos(-port.boundingRect().width() / 2, py)

        # 输出端口
        outputs = [p for p in self.outputs if p.isVisible()]
        for i, port in enumerate(outputs):
            h = port.boundingRect().height()
            py = v_offset + i * (h + spacing)
            port.setPos(width - port.boundingRect().width() / 2, py)

    @property
    def inputs(self):
        return list(self._input_items.keys())

    @property
    def outputs(self):
        return list(self._output_items.keys())

    @property
    def icon(self):
        return self._properties.get("icon")

    @icon.setter
    def icon(self, value=None):
        self._properties['icon'] = value
        if isinstance(value, QtGui.QIcon):
            pixmap = value.pixmap(28, 28)
        elif isinstance(value, str):
            pixmap = QtGui.QPixmap(value)
        else:
            pixmap = QtGui.QPixmap(ICON_NODE_BASE)
        if pixmap.isNull():
            pixmap = QtGui.QPixmap(ICON_NODE_BASE)
        if pixmap.height() > 28 or pixmap.width() > 28:
            pixmap = pixmap.scaled(28, 28, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        if self._icon_item:
            self._icon_item.setPixmap(pixmap)
        self.update_layout()

    # --- 绘图逻辑 ---

    def paint(self, painter, option, widget):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        radius = 4.0
        rect = self.boundingRect()

        # 1. 样式判定
        # 如果折叠：像普通节点一样绘制（实心背景）
        # 如果展开：像 Backdrop 一样绘制（半透明背景）

        if self._is_collapsed:
            # === 折叠态样式 (Node Style) ===
            bg_color = QtGui.QColor(30, 30, 30, 255)  # 深色实心背景
            header_color = QtGui.QColor(*self.color)
            border_color = QtGui.QColor(100, 100, 100)

            # 绘制主体
            path = QtGui.QPainterPath()
            path.addRoundedRect(rect, radius, radius)
            painter.setBrush(bg_color)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawPath(path)

            # 绘制标题栏背景
            header_height = 26.0
            header_rect = QtCore.QRectF(rect.x(), rect.y(), rect.width(), header_height)
            path_header = QtGui.QPainterPath()
            path_header.setFillRule(QtCore.Qt.WindingFill)
            path_header.addRoundedRect(header_rect, radius, radius)
            # 切掉下半部分的圆角，变成直角
            path_header.addRect(rect.x(), rect.y() + header_height - radius, rect.width(), radius)

            painter.setBrush(header_color)
            painter.drawPath(path_header.simplified())

        else:
            # === 展开态样式 (Backdrop Style) ===
            c = self.color
            bg_color = QtGui.QColor(c[0], c[1], c[2], 40)  # 半透明
            header_color = QtGui.QColor(*self.color)
            border_color = QtGui.QColor(*self.color)

            # 绘制背景
            painter.setBrush(bg_color)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(rect, radius, radius)

            # 绘制标题栏
            top_rect = QtCore.QRectF(rect.x(), rect.y(), rect.width(), 26.0)
            painter.setBrush(header_color)
            painter.drawRoundedRect(top_rect, radius, radius)
            # 修正标题栏下方圆角
            painter.drawRect(QtCore.QRectF(top_rect.left(), top_rect.bottom() - 5, 5, 5))
            painter.drawRect(QtCore.QRectF(top_rect.right() - 5, top_rect.bottom() - 5, 5, 5))

        # 2. 选中边框绘制
        if self.selected:
            sel_color = QtGui.QColor(*NodeEnum.SELECTED_BORDER_COLOR.value)
            pen = QtGui.QPen(sel_color, 1.5)
        else:
            pen = QtGui.QPen(border_color, 1.0)

        painter.setBrush(QtCore.Qt.NoBrush)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, radius, radius)

        painter.restore()

    # --- 尺寸调整回调 ---
    def on_backdrop_updated(self, update_prop, value):
        super(GroupNodeItem, self).on_backdrop_updated(update_prop, value)
        self.update_layout()

    @AbstractNodeItem.width.setter
    def width(self, width=0.0):
        # 必须调用父类的 fset 才能真正更新 geometry
        AbstractNodeItem.width.fset(self, width)
        if self._sizer:
            self._sizer.set_pos(self._width, self._height)
        self.update_layout()

    @AbstractNodeItem.height.setter
    def height(self, height=0.0):
        AbstractNodeItem.height.fset(self, height)
        if self._sizer:
            self._sizer.set_pos(self._width, self._height)
        self.update_layout()