# -*- coding: utf-8 -*-
import json
import re
from qtpy import QtCore, QtGui, QtWidgets


# ------------------------------------------------------------------------------
# 1. 增强型功能按钮 (支持长按连续触发)
# ------------------------------------------------------------------------------
class ActionButton(QtWidgets.QGraphicsRectItem):
    def __init__(self, label, color, func, parent=None, repeatable=False):
        super(ActionButton, self).__init__(QtCore.QRectF(0, 0, 20, 20), parent)
        self.label = label
        self.func = func
        self.repeatable = repeatable
        self.base_color = QtGui.QColor(*color)
        self.setAcceptHoverEvents(True)
        self.setBrush(self.base_color)
        self.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 60), 1))

        # 用于长按重复触发的定时器
        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self.func)
        self._first_repeat = True

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
        if event.button() == QtCore.Qt.LeftButton:
            self.func()
            if self.repeatable:
                self._first_repeat = True
                self._timer.start(400)  # 首次长按延迟
            event.accept()

    def mouseReleaseEvent(self, event):
        self._timer.stop()
        super(ActionButton, self).mouseReleaseEvent(event)

    def _on_timeout(self):
        if self._first_repeat:
            self._timer.stop()
            self._timer.start(50)  # 进入快速重复阶段
            self._first_repeat = False
        self.func()

    def hoverEnterEvent(self, event):
        self.setBrush(self.base_color.lighter(120))

    def hoverLeaveEvent(self, event):
        self._timer.stop()
        self.setBrush(self.base_color)


# ------------------------------------------------------------------------------
# 2. Markdown 解析逻辑
# ------------------------------------------------------------------------------
def markdown_to_html(text):
    """简单的正则解析，支持链接、粗体、列表"""
    # 转义 HTML 基本字符防止冲突
    html = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # 1. 处理超链接 [text](url) -> <a href="url">text</a>
    # 增加蓝色样式使其看起来像链接
    html = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2" style="color: #4db8ff; text-decoration: underline;">\1</a>',
                  html)

    # 2. 处理粗体 **bold** -> <b>bold</b>
    html = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', html)

    # 3. 处理列表 - list -> &bull; list
    html = re.sub(r'^-\s+(.*)', r'&bull; \1', html, flags=re.MULTILINE)

    # 4. 换行符转 <br/>
    html = html.replace('\n', '<br/>')
    return html


# ------------------------------------------------------------------------------
# 3. 文本块 (支持 Markdown 和 长按缩放)
# ------------------------------------------------------------------------------
class NoteTextBlock(QtWidgets.QGraphicsTextItem):
    def __init__(self, text, pos, width=200, font_size=14, parent=None):
        super(NoteTextBlock, self).__init__(parent)
        self._raw_text = text
        self.setPos(pos)
        self.setTextWidth(width)

        # 字体与超链接交互设置
        font = QtGui.QFont("Microsoft YaHei UI", font_size)
        self.setFont(font)
        self.setDefaultTextColor(QtGui.QColor(255, 255, 255, 230))

        # 开启超链接点击支持
        self.document().setUndoRedoEnabled(False)
        self.setOpenExternalLinks(True)  # 允许打开浏览器
        self.setTextInteractionFlags(QtCore.Qt.LinksAccessibleByMouse)

        self.setFlags(self.ItemIsSelectable | self.ItemIsMovable | self.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

        self.anchor_pin = None
        self._is_resizing = False
        self._resize_dir = [0, 0]
        self._resize_margin = 12.0

        # 按钮配置 (repeatable=True 支持长按)
        self.btn_sub = ActionButton("−", (60, 60, 60), lambda: self.change_size(-1), self, repeatable=True)
        self.btn_add = ActionButton("+", (60, 60, 60), lambda: self.change_size(1), self, repeatable=True)
        self.btn_lnk = ActionButton("➚", (0, 100, 100), self.create_anchor, self)
        self.btn_del = ActionButton("✕", (120, 40, 40), self.remove_self, self)

        self._btns = [self.btn_sub, self.btn_add, self.btn_lnk, self.btn_del]
        for btn in self._btns: btn.hide()

        self.render_markdown()
        self._update_toolbar_pos()

    def render_markdown(self):
        """将原始文本渲染为HTML"""
        html_content = markdown_to_html(self._raw_text)
        self.setHtml(html_content)

    def change_size(self, delta):
        f = self.font()
        new_size = max(6, f.pointSize() + delta)
        f.setPointSize(new_size)
        self.prepareGeometryChange()
        self.setFont(f)
        # 重新应用 HTML 以保持样式一致
        self.render_markdown()
        self.parentItem().on_text_block_changed()

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            # 进入编辑模式：显示原始 Markdown 源码
            self.setPlainText(self._raw_text)
            self.setTextInteractionFlags(QtCore.Qt.TextEditorInteraction)
            self.setFocus()
            self.setFlag(self.ItemIsMovable, False)
            event.accept()

    def focusOutEvent(self, event):
        # 退出编辑模式：保存源码并重新渲染
        self._raw_text = self.toPlainText()
        self.setTextInteractionFlags(QtCore.Qt.LinksAccessibleByMouse)
        self.render_markdown()
        self.setFlag(self.ItemIsMovable, True)
        self.parentItem().on_text_block_changed()
        super(NoteTextBlock, self).focusOutEvent(event)

    def _update_toolbar_pos(self):
        w = self.textWidth()
        for i, btn in enumerate(self._btns):
            btn.setPos(w - (4 - i) * 24, -26)

    # --- 以下保持原有逻辑 ---
    def create_anchor(self):
        if self.anchor_pin: self.remove_pin()
        self.anchor_pin = NoteAnchorPin(self.parentItem(), self)
        self.anchor_pin.setPos(self.pos() + QtCore.QPointF(self.textWidth() + 40, 20))
        self.parentItem().on_text_block_changed()

    def remove_pin(self):
        if self.anchor_pin:
            if self.scene(): self.scene().removeItem(self.anchor_pin)
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
        # 这里的判断是为了点击链接时显示手型
        item = self.document().documentLayout().anchorAt(event.pos())
        if item:
            self.setCursor(QtCore.Qt.PointingHandCursor)
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

        # 检查是否点击了链接
        anchor = self.document().documentLayout().anchorAt(event.pos())
        if anchor:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(anchor))
            event.accept()
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
# 4. 锚点 Pin & StickyNoteItem (保持原有逻辑)
# ------------------------------------------------------------------------------
from NodeGraphQt.constants import Z_VAL_NODE
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem


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


class StickyNoteItem(BackdropNodeItem):
    def __init__(self, name='Sticky Note', parent=None):
        super(StickyNoteItem, self).__init__(name, parent)
        self._text_blocks = []
        self._header_height = 35
        self._locked = False
        self.setZValue(Z_VAL_NODE - 50)
        self.setFlag(self.ItemClipsChildrenToShape, False)
        self.node = None
        self.btn_lock = ActionButton("U", (80, 80, 80), self.toggle_lock, self)
        self.btn_lock.setPos(5, 7)

    def toggle_lock(self):
        self._locked = not self._locked
        self.btn_lock.label = "🔒" if self._locked else "🔓"
        self.btn_lock.update()
        self.setFlag(self.ItemIsMovable, not self._locked)
        for b in self._text_blocks:
            b.setFlag(b.ItemIsMovable, not self._locked)
            b.setFlag(b.ItemIsSelectable, not self._locked)
        self.update()

    def mousePressEvent(self, event):
        if self._locked:
            event.ignore()
            return
        if event.pos().y() < self._header_height:
            super(StickyNoteItem, self).mousePressEvent(event)
        else:
            item = self.scene().itemAt(event.scenePos(), QtGui.QTransform())
            if item == self or item == self._sizer:
                event.ignore()
            else:
                super(StickyNoteItem, self).mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self._locked:
            event.ignore()
            return
        if event.pos().y() > self._header_height:
            item = self.scene().itemAt(event.scenePos(), QtGui.QTransform())
            if item == self:
                self.add_text_block("## 新注释\n- [链接标题](https://example.com)\n- **粗体文字**", event.pos())
                event.accept()
                return
        super(StickyNoteItem, self).mouseDoubleClickEvent(event)

    def paint(self, painter, option, widget):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = QtCore.QRectF(0, 0, self._width, self._height)
        alpha = 60 if self._locked else 160
        bg_color = QtGui.QColor(*self.color)
        bg_color.setAlpha(alpha)
        painter.setBrush(bg_color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, 10, 10)

        header_rect = QtCore.QRectF(0, 0, self._width, self._header_height)
        painter.setBrush(QtGui.QColor(0, 0, 0, 100))
        painter.drawRoundedRect(header_rect, 10, 10)
        painter.drawRect(QtCore.QRectF(0, self._header_height - 5, self._width, 5))

        painter.setPen(QtGui.QPen(QtGui.QColor(0, 255, 255, 120), 1.5, QtCore.Qt.DashLine))
        for b in self._text_blocks:
            if b.anchor_pin and b.anchor_pin.scene():
                p1 = b.get_edge_point(b.anchor_pin.pos())
                p2 = b.anchor_pin.pos()
                painter.drawLine(p1, p2)

        if self.selected and not self._locked:
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 255, 255, 180), 1.5))
            painter.drawRoundedRect(rect, 10, 10)

        painter.setPen(QtGui.QColor(255, 255, 255, 220))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(header_rect.adjusted(35, 0, 0, 0), QtCore.Qt.AlignVCenter, self.name)
        painter.restore()

    def on_text_block_changed(self):
        if not self.node: return
        data = []
        for b in self._text_blocks:
            anchor_pos = [b.anchor_pin.pos().x(), b.anchor_pin.pos().y()] if b.anchor_pin else None
            data.append({'type': 'text', 'text': b._raw_text, 'x': b.pos().x(), 'y': b.pos().y(),
                         'w': b.textWidth(), 'size': b.font().pointSize(), 'anchor': anchor_pos})
        self.node.set_property('notes_json', json.dumps(data), push_undo=False)
        self.update()

    def load_data(self, json_str):
        if not json_str: return
        for b in self._text_blocks:
            if b.anchor_pin: self.scene().removeItem(b.anchor_pin)
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