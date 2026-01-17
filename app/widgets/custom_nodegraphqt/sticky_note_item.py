# -*- coding: utf-8 -*-
import json
import time

from NodeGraphQt.constants import (
    Z_VAL_NODE, Z_VAL_BACKDROP
)
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem
from NodeGraphQt.qgraphics.node_text_item import NodeTextItem
from qfluentwidgets import ColorDialog
from qtpy import QtCore, QtGui, QtWidgets


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
        if self.label in ["+", "−"]:
            self._timer.start(200)
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
# 2. 锚点 Pin (增加目标吸附与位置更新逻辑)
# ------------------------------------------------------------------------------
class NoteAnchorPin(QtWidgets.QGraphicsRectItem):
    def __init__(self, parent_note_item, parent_block):
        super(NoteAnchorPin, self).__init__(QtCore.QRectF(-7, -7, 14, 14), parent_note_item)
        self.parent_block = parent_block
        self.setZValue(Z_VAL_NODE + 20)
        self.setFlags(self.ItemIsMovable | self.ItemIsSelectable | self.ItemSendsGeometryChanges)

        # --- 新增属性 ---
        self._target_item = None  # 记录吸附的节点 Item 对象
        self._target_offset = QtCore.QPointF(0, 0)  # 记录相对于目标节点的偏移

        # 样式
        self.default_brush = QtGui.QColor(0, 255, 255)
        self.locked_brush = QtGui.QColor(255, 50, 50)  # 吸附成功变红
        self.setBrush(self.default_brush)
        self.setPen(QtGui.QPen(QtCore.Qt.white, 2))

    def itemChange(self, change, value):
        if change == self.ItemPositionChange and self.parentItem():
            self.parentItem().update()  # 移动时刷新父级连线
        return super(NoteAnchorPin, self).itemChange(change, value)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.RightButton:
            self.parent_block.remove_pin()
            event.accept()
            return
        # 按下时如果是吸附状态，可以选择解绑，这里简单处理为允许直接拖拽调整
        super(NoteAnchorPin, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super(NoteAnchorPin, self).mouseMoveEvent(event)
        # 拖拽时，如果底下有节点，变色提示
        colliding = [
            i for i in self.scene().items(self.scenePos())
            if isinstance(i, AbstractNodeItem) and i != self.parentItem()
        ]
        self.setBrush(self.locked_brush if colliding else self.default_brush)

    def mouseReleaseEvent(self, event):
        super(NoteAnchorPin, self).mouseReleaseEvent(event)

        # 松开时检测吸附
        current_scene_pos = self.scenePos()
        colliding_items = self.scene().items(current_scene_pos)

        target = None
        for item in colliding_items:
            # 排除自身所在的 StickyNote
            if isinstance(item, AbstractNodeItem) and item != self.parentItem():
                target = item
                break

        if target:
            # 计算吸附点（最近边缘）
            rect = target.sceneBoundingRect()
            snapped_pos = self._get_closest_point_on_rect(rect, current_scene_pos)

            # 设置新位置 (转为父级坐标)
            self.setPos(self.parentItem().mapFromScene(snapped_pos))

            # 绑定目标
            self._target_item = target
            # 记录偏移量：吸附点 - 目标左上角
            self._target_offset = snapped_pos - target.scenePos()

            self.setBrush(self.locked_brush)
        else:
            # 解绑
            self._target_item = None
            self.setBrush(self.default_brush)

        self.parentItem().update()

    def _get_closest_point_on_rect(self, rect, pos):
        """计算吸附点"""
        x, y = pos.x(), pos.y()
        left, right, top, bottom = rect.left(), rect.right(), rect.top(), rect.bottom()

        clamp_x = max(left, min(x, right))
        clamp_y = max(top, min(y, bottom))

        dl, dr = abs(x - left), abs(x - right)
        dt, db = abs(y - top), abs(y - bottom)
        m = min(dl, dr, dt, db)

        if m == dl: return QtCore.QPointF(left, clamp_y)
        if m == dr: return QtCore.QPointF(right, clamp_y)
        if m == dt: return QtCore.QPointF(clamp_x, top)
        return QtCore.QPointF(clamp_x, bottom)

    def update_position_from_target(self):
        """实时跟随逻辑：根据目标位置反算自身位置"""
        if not self._target_item:
            return

        # 安全检查：如果目标节点被删除了，解绑
        if self._target_item.scene() != self.scene():
            self._target_item = None
            self.setBrush(self.default_brush)
            return

        # 1. 计算目标此时此刻的世界坐标吸附点
        target_pos = self._target_item.scenePos()
        target_snap_point = target_pos + self._target_offset

        # 2. 将该点转换为 StickyNote 内部坐标
        # mapFromScene 会自动处理 StickyNote 自身的移动
        new_local_pos = self.parentItem().mapFromScene(target_snap_point)

        # 3. 如果位置有变化，则更新
        if (new_local_pos - self.pos()).manhattanLength() > 0.1:
            self.setPos(new_local_pos)


# ------------------------------------------------------------------------------
# 3. 文本块 - 保持不变
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
# 4. StickyNoteItem (增加定时器实现实时跟随)
# ------------------------------------------------------------------------------

class StickyNoteItem(BackdropNodeItem):

    def __init__(self, name='Sticky Note', text='', parent=None):
        self._text_item = None
        self._icon_item = None
        self.btn_lock = None
        self.btn_color = None
        self._text_blocks = []

        super(StickyNoteItem, self).__init__(name, text, parent)

        # --- 核心新增：同步定时器 ---
        # 不需要 set_graph，自己监视自己
        self._sync_timer = QtCore.QTimer()
        self._sync_timer.setInterval(30)  # 30ms 刷新率 (约30fps)
        self._sync_timer.timeout.connect(self._sync_pins)
        # 默认启动，开销极小
        self._sync_timer.start()
        # ------------------------

        self._header_height = 30.0
        self._locked = False
        self.node = None
        self._last_click_time = 0
        self._double_click_threshold = 0.25

        self.setZValue(Z_VAL_BACKDROP)
        self.setFlag(self.ItemClipsChildrenToShape, False)
        self.setFlag(self.ItemIsSelectable, True)
        self.setAcceptedMouseButtons(QtCore.Qt.LeftButton | QtCore.Qt.RightButton)

        self._text_item = NodeTextItem(self.name, self)
        font = QtGui.QFont("Microsoft YaHei UI", 25)
        font.setBold(True)
        self._text_item.setFont(font)
        self._text_item.setDefaultTextColor(QtGui.QColor(255, 255, 255))

        pixmap = QtGui.QPixmap(":/icons/文本注释.svg").scaled(
            28, 28,
            QtCore.Qt.IgnoreAspectRatio,
            QtCore.Qt.SmoothTransformation
        )
        self._icon_item = QtWidgets.QGraphicsPixmapItem(pixmap, self)
        self.btn_lock = ActionButton("🔓", (80, 80, 80), self.toggle_lock, self)
        self.btn_color = ActionButton("🎨", (80, 80, 80), self.change_color, self)

        self._update_layout()

    # --- 新增：定时同步函数 ---
    def _sync_pins(self):
        """定时检查所有 Pin 的目标位置并更新"""
        # 如果当前场景不显示，或没有文本块，就跳过
        if not self.scene() or not self.isVisible() or not self._text_blocks:
            return

        need_update = False
        for block in self._text_blocks:
            pin = block.anchor_pin
            # 如果 Pin 存在且绑定了目标节点
            if pin and pin._target_item:
                old_pos = pin.pos()
                pin.update_position_from_target()
                if pin.pos() != old_pos:
                    need_update = True

        # 只有在位置真正改变时才重绘，节省性能
        if need_update:
            self.update()

    # --- ItemChange: 处理 StickyNote 自身移动时的 Pin 位置补偿 ---
    def itemChange(self, change, value):
        """
        当 StickyNote 自身被拖动时，
        如果 Pin 吸附了外部节点，Pin 必须反向移动以保持世界坐标不变。
        update_position_from_target 里的 mapFromScene 自动处理了这个逻辑。
        """
        if change == self.ItemPositionChange:
            # 手动触发一次同步，保证拖拽自身时的平滑度
            self._sync_pins()
        return super(StickyNoteItem, self).itemChange(change, value)

    def boundingRect(self):
        return QtCore.QRectF(0, 0, self._width, self._height)

    def _update_layout(self):
        if not self._text_item or not self._icon_item or not self.btn_lock or not self.btn_color:
            return

        self._icon_item.setPos(10, (self._header_height - 10) / 2)
        t_rect = self._text_item.boundingRect()
        self._text_item.setPos((self._width - t_rect.width()) / 2, 0)
        self.btn_lock.setPos(self._width - 25, 5)
        self.btn_color.setPos(self._width - 50, 5)

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

    def change_color(self):
        """弹出颜色选择框并更改节点颜色"""
        current_rgb = self.color
        current_color = QtGui.QColor(*current_rgb)

        # 弹出对话框
        new_color = QtWidgets.QColorDialog.getColor(
            current_color,
            None,
            "选择注释背景颜色",
            QtWidgets.QColorDialog.ShowAlphaChannel
        )

        if new_color.isValid():
            # 更新 Item 内部颜色属性 (AbstractNodeItem property)
            # NodeGraphQt 通常使用 (r, g, b) 或 (r, g, b, a) 元组
            c_tuple = (new_color.red(), new_color.green(), new_color.blue())
            self.color = c_tuple

            # 强制重绘
            self.update()

            # 如果绑定了 Node 对象，同步更新 Node 属性以持久化
            if self.node:
                self.node.set_color(c_tuple[0], c_tuple[1], c_tuple[2])

    def mousePressEvent(self, event):
        if self._locked:
            event.ignore()
            return

        pos = event.pos()
        item = self.scene().itemAt(event.scenePos(), QtGui.QTransform())

        if event.button() == QtCore.Qt.RightButton:
            event.accept()
            return

        if pos.y() < self._header_height:
            self.setFlag(self.ItemIsSelectable, True)
            super(StickyNoteItem, self).mousePressEvent(event)
            return

        if item and item != self and item != self._sizer:
            self.setFlag(self.ItemIsSelectable, True)
            super(StickyNoteItem, self).mousePressEvent(event)
            return

        curr_time = time.time()
        if (curr_time - self._last_click_time) < self._double_click_threshold:
            self.add_text_block("双击编辑...", pos)
            self._last_click_time = 0
            event.accept()
            return

        self._last_click_time = curr_time
        self.setFlag(self.ItemIsSelectable, False)
        event.ignore()

    def mouseDoubleClickEvent(self, event):
        if event.pos().y() < self._header_height:
            items = self.scene().items(event.scenePos())
            if self._text_item in items:
                self._text_item.set_editable(True)
                self._text_item.setFocus()
                event.accept()
                return
        super(StickyNoteItem, self).mouseDoubleClickEvent(event)

    def on_sizer_pos_changed(self, pos):
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

        header_color = QtGui.QColor(c[0], c[1], c[2], 200)
        header_height = max(self._text_item.boundingRect().height(), self._header_height)
        header_rect = QtCore.QRectF(0, 0, rect.width(), header_height)
        painter.setBrush(header_color)
        painter.drawRoundedRect(header_rect, 5, 5)
        painter.drawRect(QtCore.QRectF(0, header_height - 5, rect.width(), 5))

        # 绘制引线
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 255, 255, 120), 2.0, QtCore.Qt.DashLine))
        for b in self._text_blocks:
            if b.anchor_pin and b.anchor_pin.scene():
                p1 = b.get_edge_point(b.anchor_pin.pos())
                p2 = b.anchor_pin.pos()
                painter.drawLine(p1, p2)

                # 可选：绘制连接圆点
                if b.anchor_pin._target_item:
                    painter.setBrush(QtGui.QColor(255, 50, 50))
                    painter.setPen(QtCore.Qt.NoPen)
                    painter.drawEllipse(p2, 3, 3)

        if self.selected and not self._locked:
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 255, 255, 200), 1.5))
            painter.drawRoundedRect(rect, 5, 5)

        painter.restore()

    def add_text_block(self, text, pos, width=200, font_size=20):
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