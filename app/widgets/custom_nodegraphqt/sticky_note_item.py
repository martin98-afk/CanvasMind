# -*- coding: utf-8 -*-
import json

from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem
from qtpy import QtCore, QtGui, QtWidgets
from NodeGraphQt.constants import Z_VAL_NODE


# ------------------------------------------------------------------------------
# 1. 微型按钮组件 (用于字号调节)
# ------------------------------------------------------------------------------
class FontButton(QtWidgets.QGraphicsRectItem):
    def __init__(self, label, parent=None):
        super(FontButton, self).__init__(QtCore.QRectF(0, 0, 22, 22), parent)
        self.label = label
        self.setAcceptHoverEvents(True)
        self._hovering = False

    def paint(self, painter, option, widget):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        # 删除按钮使用淡淡的红色背景，普通按钮使用深灰色
        if self.label == "x":
            color = QtGui.QColor(150, 50, 50) if self._hovering else QtGui.QColor(100, 40, 40)
        else:
            color = QtGui.QColor(80, 80, 80) if self._hovering else QtGui.QColor(60, 60, 60)

        painter.setBrush(color)
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 50), 1))
        painter.drawRoundedRect(self.rect(), 4, 4)

        painter.setPen(QtCore.Qt.white)
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect(), QtCore.Qt.AlignCenter, self.label)

    def hoverEnterEvent(self, event):
        self._hovering = True
        self.update()

    def hoverLeaveEvent(self, event):
        self._hovering = False
        self.update()

    def mousePressEvent(self, event):
        if self.parentItem():
            if self.label == "+":
                self.parentItem().change_size(1)
            elif self.label == "-":
                self.parentItem().change_size(-1)
            elif self.label == "x":
                self.parentItem().remove_self()
        event.accept()


# ------------------------------------------------------------------------------
# 2. 增强型文本块 (OneNote 风格)
# ------------------------------------------------------------------------------

class NoteTextBlock(QtWidgets.QGraphicsTextItem):
    def __init__(self, text, pos, width=200, font_size=14, parent=None):
        super(NoteTextBlock, self).__init__(parent)
        self.setPlainText(text)
        self.setPos(pos)
        self.setTextWidth(width)

        font = QtGui.QFont("Microsoft YaHei UI", font_size)
        if not QtGui.QFontInfo(font).exactMatch():
            font = QtGui.QFont("Arial", font_size)
        self.setFont(font)
        self.setDefaultTextColor(QtGui.QColor(255, 255, 255, 220))

        self.setFlags(
            QtWidgets.QGraphicsItem.ItemIsSelectable |
            QtWidgets.QGraphicsItem.ItemIsMovable |
            QtWidgets.QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

        self._is_resizing = False
        self._resizing_edge = 12.0

        # 创建按钮组
        self.btn_del = FontButton("x", self)
        self.btn_add = FontButton("+", self)
        self.btn_sub = FontButton("-", self)

        # 初始隐藏
        for btn in [self.btn_del, self.btn_add, self.btn_sub]:
            btn.hide()

        self._update_toolbar_pos()

    def _update_toolbar_pos(self):
        """让工具栏按钮在文本框右上角水平排列"""
        w = self.textWidth()
        y_off = -28
        # 从右往左排：x, +, -
        self.btn_del.setPos(w - 22, y_off)
        self.btn_add.setPos(w - 48, y_off)
        self.btn_sub.setPos(w - 74, y_off)

    def change_size(self, delta):
        f = self.font()
        new_size = max(6, f.pointSize() + delta)
        f.setPointSize(new_size)
        self.setFont(f)
        if self.parentItem():
            self.parentItem().on_text_block_changed()

    def remove_self(self):
        """删除当前文本块"""
        parent = self.parentItem()
        if parent and hasattr(parent, '_text_blocks'):
            if self in parent._text_blocks:
                parent._text_blocks.remove(self)
            self.scene().removeItem(self)
            parent.on_text_block_changed()

    def hoverMoveEvent(self, event):
        if event.pos().x() >= self.textWidth() - self._resizing_edge:
            self.setCursor(QtCore.Qt.SizeHorCursor)
        else:
            self.setCursor(QtCore.Qt.IBeamCursor if self.hasFocus() else QtCore.Qt.ArrowCursor)
        super(NoteTextBlock, self).hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if self.cursor().shape() == QtCore.Qt.SizeHorCursor:
            self._is_resizing = True
            event.accept()
        else:
            super(NoteTextBlock, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_resizing:
            new_width = max(80, event.pos().x())
            self.setTextWidth(new_width)
            self._update_toolbar_pos()
            self.prepareGeometryChange()
        else:
            super(NoteTextBlock, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._is_resizing = False
        if self.parentItem():
            self.parentItem().on_text_block_changed()
        super(NoteTextBlock, self).mouseReleaseEvent(event)

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemSelectedChange:
            visible = bool(value)
            for btn in [self.btn_del, self.btn_add, self.btn_sub]:
                btn.setVisible(visible)

        if change == QtWidgets.QGraphicsItem.ItemPositionChange and self.parentItem():
            QtCore.QTimer.singleShot(1, self.parentItem().on_text_block_changed)
        return super(NoteTextBlock, self).itemChange(change, value)

    def paint(self, painter, option, widget):
        if self.isSelected():
            # 绘制外框
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 255, 255, 80), 1, QtCore.Qt.DashLine))
            painter.drawRect(self.boundingRect())
            # 绘制顶部抓手条 (OneNote 风格)
            painter.setBrush(QtGui.QColor(255, 255, 255, 20))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRect(QtCore.QRectF(0, -5, self.textWidth(), 5))
        super(NoteTextBlock, self).paint(painter, option, widget)

    def mouseDoubleClickEvent(self, event):
        self.setTextInteractionFlags(QtCore.Qt.TextEditorInteraction)
        self.setFocus()
        super(NoteTextBlock, self).mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        self.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)
        if self.parentItem():
            self.parentItem().on_text_block_changed()
        super(NoteTextBlock, self).focusOutEvent(event)

# ------------------------------------------------------------------------------
# 3. 注释节点主视图 (StickyNoteItem)
# ------------------------------------------------------------------------------

class StickyNoteItem(BackdropNodeItem):
    def __init__(self, name='Sticky Note', parent=None):
        super(StickyNoteItem, self).__init__(name, parent)
        self._text_blocks = []
        self._header_height = 35
        self.setZValue(Z_VAL_NODE - 5)
        # 必须关掉子项裁剪，否则文字块坐标上方的按钮会被切掉
        self.setFlag(QtWidgets.QGraphicsItem.ItemClipsChildrenToShape, False)
        self.node = None

    def paint(self, painter, option, widget):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = QtCore.QRectF(0, 0, self._width, self._height)

        # ComfyUI 背景
        bg_color = QtGui.QColor(*self.color)
        bg_color.setAlpha(160)
        painter.setBrush(bg_color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, 12, 12)

        # 标题栏
        header_rect = QtCore.QRectF(0, 0, self._width, self._header_height)
        painter.setBrush(QtGui.QColor(0, 0, 0, 100))
        path = QtGui.QPainterPath()
        path.addRoundedRect(header_rect, 12, 12)
        path.addRect(QtCore.QRectF(0, self._header_height-10, self._width, 10))
        painter.drawPath(path)

        # 选中描边
        if self.selected:
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 255, 255, 180), 1.5))
            painter.drawRoundedRect(rect, 12, 12)

        painter.setPen(QtGui.QColor(255, 255, 255, 220))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(header_rect.adjusted(15,0,0,0), QtCore.Qt.AlignVCenter, self.name)
        painter.restore()

    def mouseDoubleClickEvent(self, event):
        if event.pos().y() < self._header_height:
            super(StickyNoteItem, self).mouseDoubleClickEvent(event)
            return
        # 避免在点击工具栏或文字时触发新建
        item = self.scene().itemAt(event.scenePos(), QtGui.QTransform())
        if isinstance(item, (NoteTextBlock, FontButton)):
            return
        self.add_text_block("新注释...", event.pos())

    def add_text_block(self, text, pos, width=200, font_size=14):
        block = NoteTextBlock(text, pos, width, font_size, self)
        self._text_blocks.append(block)
        if self.node:
            self.on_text_block_changed()
        return block

    def on_text_block_changed(self):
        if not self.node or not self.node.has_property('notes_json'):
            return
        data = []
        for b in self._text_blocks:
            data.append({
                'text': b.toPlainText(),
                'x': b.pos().x(),
                'y': b.pos().y(),
                'w': b.textWidth(),
                'size': b.font().pointSize()
            })
        self.node.set_property('notes_json', json.dumps(data), push_undo=False)

    def load_data(self, json_str):
        if not json_str: return
        for b in self._text_blocks:
            if b.scene(): b.scene().removeItem(b)
        self._text_blocks = []
        try:
            data = json.loads(json_str)
            for item in data:
                self.add_text_block(item['text'], QtCore.QPointF(item['x'], item['y']), item.get('w', 200), item['size'])
        except: pass