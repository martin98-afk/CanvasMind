# -*- coding: utf-8 -*-
import json
from qtpy import QtCore, QtGui, QtWidgets
from NodeGraphQt.constants import Z_VAL_NODE


# ------------------------------------------------------------------------------
# 1. 功能按钮类
# ------------------------------------------------------------------------------
class ActionButton(QtWidgets.QGraphicsRectItem):
    def __init__(self, label, color, func, parent=None):
        super(ActionButton, self).__init__(QtCore.QRectF(0, 0, 20, 20), parent)
        self.label = label
        self.func = func
        self.base_color = QtGui.QColor(*color)
        self.setAcceptHoverEvents(True)
        self.setBrush(self.base_color)
        self.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 60), 1))

    def paint(self, painter, option, widget):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setBrush(self.brush())
        painter.setPen(self.pen())
        painter.drawRoundedRect(self.rect(), 4, 4)
        painter.setPen(QtCore.Qt.white)
        f = painter.font()
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(self.rect(), QtCore.Qt.AlignCenter, self.label)

    def mousePressEvent(self, event):
        event.accept()
        self.func()

    def hoverEnterEvent(self, event):
        self.setBrush(self.base_color.lighter(120))

    def hoverLeaveEvent(self, event):
        self.setBrush(self.base_color)


# ------------------------------------------------------------------------------
# 2. 锚点 Pin (相对父级固定)
# ------------------------------------------------------------------------------
class NoteAnchorPin(QtWidgets.QGraphicsRectItem):
    def __init__(self, parent_note_item, parent_block):
        super(NoteAnchorPin, self).__init__(QtCore.QRectF(-7, -7, 14, 14), parent_note_item)
        self.parent_block = parent_block
        self.setZValue(Z_VAL_NODE + 20)
        self.setFlags(self.ItemIsMovable | self.ItemIsSelectable | self.ItemSendsGeometryChanges)
        self.setBrush(QtGui.QColor(0, 255, 255))
        self.setPen(QtGui.QPen(QtCore.Qt.white, 2))

    def itemChange(self, change, value):
        if change == self.ItemPositionChange and self.parentItem():
            self.parentItem().update()
        return super(NoteAnchorPin, self).itemChange(change, value)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.RightButton:
            self.parent_block.remove_pin()
            event.accept()
            return
        super(NoteAnchorPin, self).mousePressEvent(event)


# ------------------------------------------------------------------------------
# 3. 文本块 (修复：双击编辑 + 8向缩放 + 相对引线)
# ------------------------------------------------------------------------------
class NoteTextBlock(QtWidgets.QGraphicsTextItem):
    def __init__(self, text, pos, width=200, font_size=14, parent=None):
        super(NoteTextBlock, self).__init__(parent)
        self.setPlainText(text)
        self.setPos(pos)
        self.setTextWidth(width)

        font = QtGui.QFont("Microsoft YaHei UI", font_size)
        self.setFont(font)
        self.setDefaultTextColor(QtGui.QColor(255, 255, 255, 230))

        # 初始状态：可选中、可移动
        self.setFlags(self.ItemIsSelectable | self.ItemIsMovable | self.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

        self.anchor_pin = None
        self._is_resizing = False
        self._resize_dir = [0, 0]
        self._resize_margin = 12.0

        self.btn_sub = ActionButton("−", (60, 60, 60), lambda: self.change_size(-1), self)
        self.btn_add = ActionButton("+", (60, 60, 60), lambda: self.change_size(1), self)
        self.btn_lnk = ActionButton("➚", (0, 100, 100), self.create_anchor, self)
        self.btn_del = ActionButton("✕", (120, 40, 40), self.remove_self, self)
        self._btns = [self.btn_sub, self.btn_add, self.btn_lnk, self.btn_del]
        for btn in self._btns: btn.hide()
        self._update_toolbar_pos()

    def _update_toolbar_pos(self):
        w = self.textWidth()
        for i, btn in enumerate(self._btns):
            btn.setPos(w - (4 - i) * 24, -26)

    def change_size(self, delta):
        f = self.font()
        f.setPointSize(max(6, f.pointSize() + delta))
        self.prepareGeometryChange()
        self.setFont(f)
        self.parentItem().on_text_block_changed()

    def create_anchor(self):
        if self.anchor_pin: self.remove_pin()
        # 父级设为 BackdropItem
        self.anchor_pin = NoteAnchorPin(self.parentItem(), self)
        # 本地坐标定位
        self.anchor_pin.setPos(self.pos() + QtCore.QPointF(self.textWidth() + 40, 20))
        self.parentItem().on_text_block_changed()

    def remove_pin(self):
        if self.anchor_pin:
            self.scene().removeItem(self.anchor_pin)
            self.anchor_pin = None
            self.parentItem().on_text_block_changed()

    def remove_self(self):
        self.remove_pin()
        p = self.parentItem()
        if self in p._text_blocks: p._text_blocks.remove(self)
        self.scene().removeItem(self)
        p.on_text_block_changed()

    def get_edge_point(self, pin_local_pos):
        """引线从边缘出发的计算逻辑"""
        rect = self.boundingRect()
        center = rect.center()
        # 计算 Pin 相对于文字块内部中心的偏移
        p_in_block = pin_local_pos - self.pos()
        dx = p_in_block.x() - center.x()
        dy = p_in_block.y() - center.y()

        if abs(dx / rect.width()) > abs(dy / rect.height()):
            return self.pos() + QtCore.QPointF(rect.right() if dx > 0 else rect.left(), center.y())
        else:
            return self.pos() + QtCore.QPointF(center.x(), rect.bottom() if dy > 0 else rect.top())

    # --- 交互与缩放逻辑 ---
    def hoverMoveEvent(self, event):
        if self.textInteractionFlags() & QtCore.Qt.TextEditorInteraction:
            self.setCursor(QtCore.Qt.IBeamCursor)
            return

        rect = self.boundingRect()
        m = self._resize_margin
        x, y = event.pos().x(), event.pos().y()
        dx, dy = 0, 0
        if x < m:
            dx = -1
        elif x > rect.width() - m:
            dx = 1
        if y < m:
            dy = -1
        elif y > rect.height() - m:
            dy = 1

        if dx != 0 or dy != 0:
            if (dx == 1 and dy == 1) or (dx == -1 and dy == -1):
                self.setCursor(QtCore.Qt.SizeFDiagCursor)
            elif (dx == -1 and dy == 1) or (dx == 1 and dy == -1):
                self.setCursor(QtCore.Qt.SizeBDiagCursor)
            elif dx != 0:
                self.setCursor(QtCore.Qt.SizeHorCursor)
            else:
                self.setCursor(QtCore.Qt.SizeVerCursor)
        else:
            self.setCursor(QtCore.Qt.ArrowCursor)
        super(NoteTextBlock, self).hoverMoveEvent(event)

    def mousePressEvent(self, event):
        # 如果正在编辑，让基类处理光标定位
        if self.textInteractionFlags() & QtCore.Qt.TextEditorInteraction:
            super(NoteTextBlock, self).mousePressEvent(event)
            return

        rect = self.boundingRect()
        m = self._resize_margin
        x, y = event.pos().x(), event.pos().y()
        dx, dy = 0, 0
        if x < m:
            dx = -1
        elif x > rect.width() - m:
            dx = 1
        if y < m:
            dy = -1
        elif y > rect.height() - m:
            dy = 1

        if dx != 0 or dy != 0:
            self._is_resizing = True
            self._resize_dir = [dx, dy]
            self.setFlag(self.ItemIsMovable, False)
            event.accept()
        else:
            super(NoteTextBlock, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_resizing:
            self.prepareGeometryChange()
            dx, dy = self._resize_dir
            pos = event.pos()
            if dx == 1:
                self.setTextWidth(max(60, pos.x()))
            elif dx == -1:
                diff = pos.x()
                if self.textWidth() - diff > 60:
                    self.setX(self.x() + diff)
                    self.setTextWidth(self.textWidth() - diff)
            if dy == -1: self.setY(self.y() + pos.y())
            self._update_toolbar_pos()
        else:
            super(NoteTextBlock, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_resizing:
            self._is_resizing = False
            self.setFlag(self.ItemIsMovable, True)
        self.parentItem().on_text_block_changed()
        super(NoteTextBlock, self).mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        # 核心修复：进入编辑模式
        if event.button() == QtCore.Qt.LeftButton:
            self.setFlag(self.ItemIsMovable, False)  # 编辑时必须禁用移动
            self.setTextInteractionFlags(QtCore.Qt.TextEditorInteraction)
            self.setFocus()
            # 重新发送点击事件以确保光标定位
            event.accept()
        super(NoteTextBlock, self).mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        # 核心修复：退出编辑模式
        self.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)
        self.setFlag(self.ItemIsMovable, True)
        self.parentItem().on_text_block_changed()
        super(NoteTextBlock, self).focusOutEvent(event)

    def itemChange(self, change, value):
        if change == self.ItemSelectedChange:
            for btn in self._btns: btn.setVisible(bool(value))
        if change == self.ItemPositionChange and self.parentItem():
            self.parentItem().update()
            QtCore.QTimer.singleShot(1, self.parentItem().on_text_block_changed)
        return super(NoteTextBlock, self).itemChange(change, value)

    def paint(self, painter, option, widget):
        if self.isSelected():
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 255, 255, 100), 1, QtCore.Qt.DashLine))
            painter.drawRect(self.boundingRect())
            # 按钮区域背景
            bg_rect = QtCore.QRectF(self.textWidth() - 98, -28, 98, 24)
            painter.setBrush(QtGui.QColor(20, 20, 20, 220))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(bg_rect, 4, 4)
        super(NoteTextBlock, self).paint(painter, option, widget)


# ------------------------------------------------------------------------------
# 4. 主画布节点视图 (StickyNoteItem)
# ------------------------------------------------------------------------------
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem


class StickyNoteItem(BackdropNodeItem):
    def __init__(self, name='Sticky Note', parent=None):
        super(StickyNoteItem, self).__init__(name, parent)
        self._text_blocks = []
        self._header_height = 35
        self.setZValue(Z_VAL_NODE - 10)
        self.setFlag(self.ItemClipsChildrenToShape, False)
        self.node = None

    def paint(self, painter, option, widget):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = QtCore.QRectF(0, 0, self._width, self._height)

        bg_color = QtGui.QColor(*self.color)
        bg_color.setAlpha(160)
        painter.setBrush(bg_color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, 10, 10)

        header_rect = QtCore.QRectF(0, 0, self._width, self._header_height)
        painter.setBrush(QtGui.QColor(0, 0, 0, 100))
        painter.drawRoundedRect(header_rect, 10, 10)
        painter.drawRect(QtCore.QRectF(0, self._header_height - 5, self._width, 5))

        # 绘制边缘引线
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 255, 255, 150), 1.5, QtCore.Qt.DashLine))
        for b in self._text_blocks:
            if isinstance(b, NoteTextBlock) and b.anchor_pin:
                p1 = b.get_edge_point(b.anchor_pin.pos())
                p2 = b.anchor_pin.pos()
                painter.drawLine(p1, p2)

        if self.selected:
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 255, 255, 180), 1.5))
            painter.drawRoundedRect(rect, 10, 10)

        painter.setPen(QtGui.QColor(255, 255, 255, 220))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(header_rect.adjusted(15, 0, 0, 0), QtCore.Qt.AlignVCenter, self.name)
        painter.restore()

    def mouseDoubleClickEvent(self, event):
        if event.pos().y() < self._header_height:
            super(StickyNoteItem, self).mouseDoubleClickEvent(event)
            return
        item = self.scene().itemAt(event.scenePos(), QtGui.QTransform())
        if isinstance(item, (NoteTextBlock, ActionButton, NoteAnchorPin)): return
        self.add_text_block("双击编辑内容...", event.pos())

    def on_text_block_changed(self):
        if not self.node: return
        data = []
        for b in self._text_blocks:
            anchor_pos = [b.anchor_pin.pos().x(), b.anchor_pin.pos().y()] if b.anchor_pin else None
            data.append({
                'type': 'text', 'text': b.toPlainText(),
                'x': b.pos().x(), 'y': b.pos().y(),
                'w': b.textWidth(), 'size': b.font().pointSize(),
                'anchor': anchor_pos
            })
        self.node.set_property('notes_json', json.dumps(data), push_undo=False)

    def load_data(self, json_str):
        if not json_str: return
        for b in self._text_blocks:
            if isinstance(b, NoteTextBlock) and b.anchor_pin:
                self.scene().removeItem(b.anchor_pin)
            self.scene().removeItem(b)
        self._text_blocks = []
        try:
            data = json.loads(json_str)
            for item in data:
                block = self.add_text_block(item['text'], QtCore.QPointF(item['x'], item['y']), item.get('w', 200),
                                            item['size'])
                if item.get('anchor'):
                    block.anchor_pin = NoteAnchorPin(self, block)
                    block.anchor_pin.setPos(item['anchor'][0], item['anchor'][1])
        except:
            pass

    def add_text_block(self, text, pos, width=200, font_size=14):
        block = NoteTextBlock(text, pos, width, font_size, self)
        self._text_blocks.append(block)
        return block