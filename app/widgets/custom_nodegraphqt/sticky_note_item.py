# -*- coding: utf-8 -*-
import json
import time

from NodeGraphQt.constants import (
    Z_VAL_NODE, ICON_NODE_BASE, Z_VAL_BACKDROP
)
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem
from NodeGraphQt.qgraphics.node_text_item import NodeTextItem
from qtpy import QtCore, QtGui
from qtpy import QtWidgets


# ------------------------------------------------------------------------------
# 1. 功能按钮类 (Action Button)
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
        # 长按连续触发计时器
        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self.func)
        self._is_pressed = False

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
        # 如果是加减按钮，启动长按计时器
        if self.label in ["+", "−"]:
            self._timer.start(200) # 200ms 后开始连续触发
        self._is_pressed = True

    def mouseReleaseEvent(self, event):
        self._timer.stop()
        self._is_pressed = False
        super(ActionButton, self).mouseReleaseEvent(event)

    def hoverEnterEvent(self, event):
        self.setBrush(self.base_color.lighter(120))

    def hoverLeaveEvent(self, event):
        self.setBrush(self.base_color)


# ------------------------------------------------------------------------------
# 2. 锚点 Pin
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
# 3. 文本块 (支持 8 向缩放)
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
        self.anchor_pin = NoteAnchorPin(self.parentItem(), self)
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
        rect = self.boundingRect()
        center = rect.center()
        p_in_block = pin_local_pos - self.pos()
        dx, dy = p_in_block.x() - center.x(), p_in_block.y() - center.y()
        if abs(dx / rect.width()) > abs(dy / rect.height()):
            return self.pos() + QtCore.QPointF(rect.right() if dx > 0 else rect.left(), center.y())
        else:
            return self.pos() + QtCore.QPointF(center.x(), rect.bottom() if dy > 0 else rect.top())

    def hoverMoveEvent(self, event):
        if self.textInteractionFlags() & QtCore.Qt.TextEditorInteraction:
            self.setCursor(QtCore.Qt.IBeamCursor)
            return
        rect = self.boundingRect()
        m, x, y = self._resize_margin, event.pos().x(), event.pos().y()
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
        if self.textInteractionFlags() & QtCore.Qt.TextEditorInteraction:
            super(NoteTextBlock, self).mousePressEvent(event)
            return
        rect = self.boundingRect()
        m, x, y = self._resize_margin, event.pos().x(), event.pos().y()
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
                    self.setX(self.x() + diff);
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
        if event.button() == QtCore.Qt.LeftButton:
            self.setFlag(self.ItemIsMovable, False)
            self.setTextInteractionFlags(QtCore.Qt.TextEditorInteraction)
            self.setFocus()
            event.accept()
        super(NoteTextBlock, self).mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
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
            bg_rect = QtCore.QRectF(self.textWidth() - 98, -28, 98, 24)
            painter.setBrush(QtGui.QColor(20, 20, 20, 220))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(bg_rect, 4, 4)
        super(NoteTextBlock, self).paint(painter, option, widget)


# ------------------------------------------------------------------------------
# 4.StickyNoteItem (防误触核心)
# ------------------------------------------------------------------------------

class StickyNoteItem(BackdropNodeItem):
    def __init__(self, name='Sticky Note', text='', parent=None):
        # 1. 先声明关键变量为 None，防止父类初始化时触发布局报错
        self._text_item = None
        self._icon_item = None
        self.btn_lock = None
        self._text_blocks = []

        super(StickyNoteItem, self).__init__(name, text, parent)

        # 2. 基础参数
        self._header_height = 30.0
        self._locked = False
        self.node = None

        # 模拟双击判定计时
        self._last_click_time = 0
        self._double_click_threshold = 0.25

        # 3. 层级与标志位
        self.setZValue(Z_VAL_BACKDROP)
        self.setFlag(self.ItemClipsChildrenToShape, False)
        self.setFlag(self.ItemIsSelectable, True)

        # 显式接受右键，确保场景能识别到该 Item，从而让你的劫持逻辑 itemAt 能抓到它
        self.setAcceptedMouseButtons(QtCore.Qt.LeftButton | QtCore.Qt.RightButton)

        # 4. 初始化 UI 组件
        self._text_item = NodeTextItem(self.name, self)
        font = QtGui.QFont("Microsoft YaHei UI", 25)
        font.setBold(True)
        self._text_item.setFont(font)
        self._text_item.setDefaultTextColor(QtGui.QColor(255, 255, 255))

        pixmap = QtGui.QPixmap(":/icons/文本注释.svg").scaled(
            20, 20,
            QtCore.Qt.IgnoreAspectRatio,
            QtCore.Qt.SmoothTransformation
        )
        self._icon_item = QtWidgets.QGraphicsPixmapItem(pixmap, self)
        self.btn_lock = ActionButton("🔓", (80, 80, 80), self.toggle_lock, self)

        # 5. 初次布局更新
        self._update_layout()

    def boundingRect(self):
        """实时返回宽高，解决缩放后点击失效"""
        return QtCore.QRectF(0, 0, self._width, self._height)

    def _update_layout(self):
        """更新 UI 元素位置 (增加安全检查)"""
        if not self._text_item or not self._icon_item or not self.btn_lock:
            return

        self._icon_item.setPos(10, (self._header_height - 20) / 2)
        t_rect = self._text_item.boundingRect()
        self._text_item.setPos((self._width - t_rect.width()) / 2, 0)
        self.btn_lock.setPos(self._width - 25, 5)

    def toggle_lock(self):
        self._locked = not self._locked
        self.btn_lock.label = "🔒" if self._locked else "🔓"
        self.btn_lock.update()
        self.setFlag(self.ItemIsMovable, not self._locked)
        self.setFlag(self.ItemIsSelectable, not self._locked)
        for b in self._text_blocks:
            b.setFlag(b.ItemIsMovable, not self._locked)
            b.setFlag(b.ItemIsSelectable, not self._locked)
        self.update()

    def mousePressEvent(self, event):
        if self._locked:
            event.ignore()
            return

        pos = event.pos()
        # 探测点击到的具体物体
        item = self.scene().itemAt(event.scenePos(), QtGui.QTransform())

        # --- 右键处理 (修复画布菜单劫持问题) ---
        if event.button() == QtCore.Qt.RightButton:
            # 必须 accept，这样场景认为点击了 Item，你的 contextMenuEvent 劫持逻辑中 itemAt 就不为 None
            event.accept()
            # 停止向下传递，防止 Backdrop 的右键默认逻辑执行
            return

        # --- 左键处理 ---
        # 1. 点击标题栏：执行正常选中/移动
        if pos.y() < self._header_height:
            self.setFlag(self.ItemIsSelectable, True)
            super(StickyNoteItem, self).mousePressEvent(event)
            return

        # 2. 点击内部已有的 UI 元素 (按钮、文本块、引线锚点)
        if item and item != self and item != self._sizer:
            self.setFlag(self.ItemIsSelectable, True)
            super(StickyNoteItem, self).mousePressEvent(event)
            return

        # 3. 点击背景躯干区域：
        curr_time = time.time()
        # 判定双击 (模拟)
        if (curr_time - self._last_click_time) < self._double_click_threshold:
            self.add_text_block("双击编辑...", pos)
            self._last_click_time = 0
            # 【核心修复】这里 accept 且不调用 super，这样 Backdrop 就没机会去全选内部节点
            event.accept()
            return

            # 判定单击：透传给画布框选
        self._last_click_time = curr_time
        self.setFlag(self.ItemIsSelectable, False)
        # ignore() 发送给画布，触发框选，同时因为没调 super()，不会全选内部
        event.ignore()

    def mouseDoubleClickEvent(self, event):
        """标题栏双击改名"""
        if event.pos().y() < self._header_height:
            items = self.scene().items(event.scenePos())
            if self._text_item in items:
                self._text_item.set_editable(True)
                self._text_item.setFocus()
                event.accept()
                return
        super(StickyNoteItem, self).mouseDoubleClickEvent(event)

    def on_sizer_pos_changed(self, pos):
        """缩放更新"""
        self.prepareGeometryChange()
        super(StickyNoteItem, self).on_sizer_pos_changed(pos)
        self._update_layout()

    def paint(self, painter, option, widget):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.boundingRect()

        c = self.color
        alpha = 40 if self._locked else 80
        bg_color = QtGui.QColor(c[0], c[1], c[2], alpha)
        painter.setBrush(bg_color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, 5, 5)

        # 标题栏
        header_color = QtGui.QColor(c[0], c[1], c[2], 200)
        header_height = max(self._text_item.boundingRect().height(), self._header_height)
        header_rect = QtCore.QRectF(0, 0, rect.width(), header_height)
        painter.setBrush(header_color)
        painter.drawRoundedRect(header_rect, 5, 5)
        painter.drawRect(QtCore.QRectF(0, header_height - 5, rect.width(), 5))

        # 绘制内部文本块的引线
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 255, 255, 120), 1.2, QtCore.Qt.DashLine))
        for b in self._text_blocks:
            if b.anchor_pin and b.anchor_pin.scene():
                p1 = b.get_edge_point(b.anchor_pin.pos())
                p2 = b.anchor_pin.pos()
                painter.drawLine(p1, p2)

        # 选中描边
        if self.selected and not self._locked:
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 255, 255, 200), 1.5))
            painter.drawRoundedRect(rect, 5, 5)

        painter.restore()

    # --- 基础功能 ---

    def add_text_block(self, text, pos, width=200, font_size=20):
        # 确保引用正确
        block = NoteTextBlock(text, pos, width, font_size, self)
        self._text_blocks.append(block)
        self.on_text_block_changed()
        return block

    def on_text_block_changed(self):
        if not self.node: return
        data = []
        for b in self._text_blocks:
            anchor_pos = [b.anchor_pin.pos().x(), b.anchor_pin.pos().y()] if b.anchor_pin else None
            data.append({
                'text': b.toPlainText(), 'x': b.pos().x(), 'y': b.pos().y(),
                'w': b.textWidth(), 'size': b.font().pointSize(), 'anchor': anchor_pos
            })
        self.node.set_property('notes_json', json.dumps(data), push_undo=False)

    def load_data(self, json_str):
        if not json_str: return
        for b in self._text_blocks:
            if b.anchor_pin:
                try:
                    self.scene().removeItem(b.anchor_pin)
                except:
                    pass
            try:
                self.scene().removeItem(b)
            except:
                pass
        self._text_blocks = []
        try:
            data = json.loads(json_str)
            for item in data:
                block = self.add_text_block(item['text'], QtCore.QPointF(item['x'], item['y']),
                                            item.get('w', 200), item['size'])
                if item.get('anchor'):
                    block.anchor_pin = NoteAnchorPin(self, block)
                    block.anchor_pin.setPos(item['anchor'][0], item['anchor'][1])
        except:
            pass

    @AbstractNodeItem.width.setter
    def width(self, width=0.0):
        AbstractNodeItem.width.fset(self, width)
        self.prepareGeometryChange()
        self._sizer.set_pos(self._width, self._height)
        self._update_layout()

    @AbstractNodeItem.height.setter
    def height(self, height=0.0):
        AbstractNodeItem.height.fset(self, height)
        self.prepareGeometryChange()
        self._sizer.set_pos(self._width, self._height)
        self._update_layout()

    @AbstractNodeItem.name.setter
    def name(self, name=''):
        AbstractNodeItem.name.fset(self, name)
        if self._text_item and self._text_item.toPlainText() != name:
            self._text_item.setPlainText(name)
            self._update_layout()