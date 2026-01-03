# -*- coding: utf-8 -*-
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem
from qtpy import QtCore, QtGui, QtWidgets


# ------------------------------------------------------------------------------
# 1. 文本编辑组件 - 解决 set_property 触发问题
# ------------------------------------------------------------------------------

class EditableTextItem(QtWidgets.QGraphicsTextItem):
    def __init__(self, parent=None):
        super(EditableTextItem, self).__init__(parent)
        self.setTabChangesFocus(True)

    def focusOutEvent(self, event):
        super(EditableTextItem, self).focusOutEvent(event)
        self.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)
        view_item = self.parentItem()
        if view_item:
            # 这里的获取路径已经过加固
            node = getattr(view_item, 'node', None)
            if not node:
                try:
                    node = view_item.graph.get_node_by_id(view_item.id)
                except:
                    pass

            if node and node.get_property('note_text') != self.toPlainText():
                node.set_property('note_text', self.toPlainText(), push_undo=True)


# ------------------------------------------------------------------------------
# 2. 视图层 (UI) - 修复形状匹配与缩放
# ------------------------------------------------------------------------------


class StickyNoteItem(BackdropNodeItem):
    def __init__(self, name='Sticky Note', text='', parent=None):
        super(StickyNoteItem, self).__init__(name, parent)

        # 【核心设置 1】：开启子项裁剪，防止文本超出节点圆角边框
        self.setFlag(QtWidgets.QGraphicsItem.ItemClipsChildrenToShape, True)

        self._text_item = EditableTextItem(self)
        self._text_item.setPlainText(text)

        font = QtGui.QFont("Microsoft YaHei", 11)
        if not QtGui.QFontInfo(font).exactMatch():
            font = QtGui.QFont("Arial", 11)
        self._text_item.setFont(font)
        self._text_item.setDefaultTextColor(QtGui.QColor(255, 255, 255, 210))

        # 边距设置
        self._text_item.document().setDocumentMargin(12)
        self._text_item.setZValue(self.zValue() + 0.1)
        self.node = None

    def set_text(self, text):
        if self._text_item.toPlainText() != text:
            self._text_item.setPlainText(text)

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            # 双击时，如果点击位置在标题栏下方，才触发编辑
            if event.pos().y() > 30:
                self._text_item.setTextInteractionFlags(QtCore.Qt.TextEditorInteraction)
                self._text_item.setFocus()
                event.accept()
                return
        super(StickyNoteItem, self).mouseDoubleClickEvent(event)

    def paint(self, painter, option, widget):
        """绘制逻辑：实时匹配形状"""
        # --- 1. 自动同步文本宽度与节点宽度 ---
        margin = 2
        header_height = 32
        # 设置文本项的位置
        self._text_item.setPos(margin, header_height)
        # 【核心设置 2】：强制文本宽度等于节点宽度（减去边距），实现自动换行
        # 这里必须在每次 paint 时或 resize 时调用
        self._text_item.setTextWidth(max(10, self._width - margin * 2))

        # --- 2. 绘图 ---
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        rect = QtCore.QRectF(0, 0, self._width, self._height)

        # 背景
        bg_color = QtGui.QColor(*self.color)
        bg_color.setAlpha(170)
        painter.setBrush(bg_color)
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 30), 1))
        painter.drawRoundedRect(rect, 10, 10)

        # 标题栏
        header_rect = QtCore.QRectF(0, 0, self._width, header_height)
        painter.setBrush(QtGui.QColor(0, 0, 0, 60))
        painter.setPen(QtCore.Qt.NoPen)
        path = QtGui.QPainterPath()
        path.addRoundedRect(header_rect, 10, 10)
        painter.drawPath(path)

        # 右下角缩放手柄装饰
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 80), 2))
        handle_size = 12
        for i in range(2):
            offset = i * 5
            painter.drawLine(
                QtCore.QPointF(self._width - handle_size + offset, self._height - 3),
                QtCore.QPointF(self._width - 3, self._height - handle_size + offset)
            )

        if self.selected:
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 255, 255, 200), 2))
            painter.drawRoundedRect(rect, 10, 10)

        painter.restore()
