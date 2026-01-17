# -*- coding: utf-8 -*-
import json
import time
import re  
from qtpy.QtCore import QUrl  
from qtpy.QtGui import QDesktopServices  

from NodeGraphQt.constants import (
    Z_VAL_NODE, Z_VAL_BACKDROP
)
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem
from NodeGraphQt.qgraphics.node_text_item import NodeTextItem
from qtpy import QtCore, QtGui, QtWidgets


def simple_markdown_to_html(text):
    """简易 Markdown 转 HTML，支持链接和换行"""
    if not text:
        return ""

    # 1. 转义 HTML 特殊字符，防止 XSS 或渲染错误
    html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # 2. 处理 URL 链接: [text](url) -> <a href="url">text</a>
    # 链接颜色设为浅蓝色，去掉了下划线，看着更像 ComfyUI 风格
    link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    link_html = r'<a href="\2" style="color: #4facfe; text-decoration: underline;">\1</a>'
    html = re.sub(link_pattern, link_html, html)

    # 3. 处理换行符 \n -> <br>
    html = html.replace("\n", "<br>")

    return html


# ------------------------------------------------------------------------------
# 1. 功能按钮类 (Action Button) - 无变化
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
# 2. 锚点 Pin (修改：吸附前检查 persistent_id)
# ------------------------------------------------------------------------------
class NoteAnchorPin(QtWidgets.QGraphicsRectItem):
    def __init__(self, parent_note_item, parent_block):
        super(NoteAnchorPin, self).__init__(QtCore.QRectF(-7, -7, 14, 14), parent_note_item)
        self.parent_block = parent_block
        self.setZValue(Z_VAL_NODE + 20)
        self.setFlags(self.ItemIsMovable | self.ItemIsSelectable | self.ItemSendsGeometryChanges)

        self._target_item = None
        self._target_offset = QtCore.QPointF(0, 0)

        self.default_brush = QtGui.QColor(0, 255, 255)
        self.locked_brush = QtGui.QColor(255, 50, 50)
        self.setBrush(self.default_brush)
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

    def mouseMoveEvent(self, event):
        super(NoteAnchorPin, self).mouseMoveEvent(event)
        # 视觉提示：只有当且仅当下面有节点，且该节点有 persistent_id 时才变色（可选）
        # 为了性能，Move 阶段只做简单碰撞检测
        colliding = [
            i for i in self.scene().items(self.scenePos())
            if isinstance(i, AbstractNodeItem) and i != self.parentItem()
        ]
        self.setBrush(self.locked_brush if colliding else self.default_brush)

    def mouseReleaseEvent(self, event):
        super(NoteAnchorPin, self).mouseReleaseEvent(event)
        self.perform_snap()

        # 强制触发保存
        if self.parentItem():
            self.parentItem().on_text_block_changed()

    def perform_snap(self):
        """执行吸附逻辑"""
        if not self.scene(): return

        current_scene_pos = self.scenePos()
        colliding_items = self.scene().items(current_scene_pos)

        target_view_item = None

        # 1. 寻找碰撞的 GraphicsItem
        for item in colliding_items:
            if isinstance(item, AbstractNodeItem) and (not isinstance(item, StickyNoteItem)):
                target_view_item = item
                break

        # 2. 【核心校验】检查是否有 persistent_id
        valid_target = False
        if target_view_item:
            # 调用父级 StickyNote 的辅助方法，通过 View 找 Node
            node_obj = self.parentItem().get_node_by_view(target_view_item)
            if node_obj:
                # 获取 persistent_id
                pid = node_obj.get_property('persistent_id')
                if pid:
                    valid_target = True
                else:
                    print("StickyNote: Target node has no 'persistent_id', ignore snap.")
            else:
                # 可能是还没有绑定 Node 对象的纯 Item，或者 helper 没找到
                print("StickyNote: Cannot find Node object for item.")

        if valid_target and target_view_item:
            # 执行吸附物理计算
            rect = target_view_item.sceneBoundingRect()
            snapped_pos = self._get_closest_point_on_rect(rect, current_scene_pos)

            self.setPos(self.parentItem().mapFromScene(snapped_pos))
            self._target_item = target_view_item
            self._target_offset = snapped_pos - target_view_item.scenePos()
            self.setBrush(self.locked_brush)
        else:
            # 不合法或没撞到，解绑
            self._target_item = None
            self.setBrush(self.default_brush)

        self.parentItem().update()

    def _get_closest_point_on_rect(self, rect, pos):
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
        if not self._target_item: return
        if self._target_item.scene() != self.scene():
            self._target_item = None
            self.setBrush(self.default_brush)
            return

        target_pos = self._target_item.scenePos()
        target_snap_point = target_pos + self._target_offset
        new_local_pos = self.parentItem().mapFromScene(target_snap_point)

        if (new_local_pos - self.pos()).manhattanLength() > 0.1:
            self.setPos(new_local_pos)


# ------------------------------------------------------------------------------
# 3. 文本块 - 无变化
# ------------------------------------------------------------------------------
class NoteTextBlock(QtWidgets.QGraphicsTextItem):
    def __init__(self, text, pos, width=200, font_size=14, parent=None):
        super(NoteTextBlock, self).__init__(parent)

        # 核心：保存原始文本 (Markdown)
        self._raw_text = text

        # 初始化设置
        self.setPos(pos)
        self.setTextWidth(width)
        font = QtGui.QFont("Microsoft YaHei UI", font_size)
        self.setFont(font)
        self.setDefaultTextColor(QtGui.QColor(255, 255, 255, 230))

        # 默认不允许编辑，处于“展示模式”
        self.setFlags(self.ItemIsSelectable | self.ItemIsMovable | self.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)

        # 渲染 HTML (展示模式)
        self.setHtml(simple_markdown_to_html(self._raw_text))

        self.anchor_pin = None
        self._is_resizing = False
        self._resize_dir = [0, 0]
        self._resize_margin = 12.0

        # 按钮栏
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
        # 字体变了，需要通知父级更新 json，但不影响文本内容
        self.parentItem().on_text_block_changed()

    # --- 引线/删除相关 (保持不变) ---
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

    # --- 交互核心逻辑 ---

    def hoverMoveEvent(self, event):
        # 如果正在编辑，显示输入光标
        if self.textInteractionFlags() & QtCore.Qt.TextEditorInteraction:
            self.setCursor(QtCore.Qt.IBeamCursor)
            return

        # 如果是展示模式，检测是否悬停在链接上
        anchor = self.document().documentLayout().anchorAt(event.pos())
        if anchor:
            self.setCursor(QtCore.Qt.PointingHandCursor)
            return

        # 否则处理边缘缩放光标
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
        # 1. 如果正在编辑文本，走默认逻辑
        if self.textInteractionFlags() & QtCore.Qt.TextEditorInteraction:
            super(NoteTextBlock, self).mousePressEvent(event)
            return

        # 2. 检测是否点击了链接 (展示模式下)
        # document().documentLayout().anchorAt(pos) 可以检测指定位置是否有 <a href>
        anchor = self.document().documentLayout().anchorAt(event.pos())
        if anchor:
            # 打开网页
            QDesktopServices.openUrl(QUrl(anchor))
            event.accept()
            return

        # 3. 处理边缘缩放
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
            # 4. 普通点击 (拖拽移动)
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
        # 双击进入编辑模式
        if event.button() == QtCore.Qt.LeftButton:
            # 切换为显示原始 Markdown 文本，方便编辑
            self.setPlainText(self._raw_text)

            self.setFlag(self.ItemIsMovable, False)
            self.setTextInteractionFlags(QtCore.Qt.TextEditorInteraction)
            self.setFocus()

            # 恢复光标为输入型
            self.setCursor(QtCore.Qt.IBeamCursor)
            event.accept()

        super(NoteTextBlock, self).mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        # 失去焦点：退出编辑模式，保存并渲染 HTML
        if self.textInteractionFlags() & QtCore.Qt.TextEditorInteraction:
            # 1. 保存当前编辑框里的内容为新的 raw_text
            self._raw_text = self.toPlainText()

            # 2. 切换回 HTML 渲染
            self.setHtml(simple_markdown_to_html(self._raw_text))

            # 3. 恢复交互标记
            self.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)
            self.setFlag(self.ItemIsMovable, True)

            # 4. 触发保存逻辑
            self.parentItem().on_text_block_changed()

        super(NoteTextBlock, self).focusOutEvent(event)

    # --- 数据相关 ---

    def toPlainText(self):
        # 覆写 toPlainText，确保外部获取数据时拿到的是 _raw_text (Markdown)
        # 因为如果处于 HTML 模式，基类的 toPlainText() 会返回去掉标签的纯文本，丢失格式
        if self.textInteractionFlags() & QtCore.Qt.TextEditorInteraction:
            # 编辑模式下，基类的内容就是 raw text
            return super(NoteTextBlock, self).toPlainText()
        else:
            # 展示模式下，返回内存里存的 markdown
            return self._raw_text

    def itemChange(self, change, value):
        if change == self.ItemSelectedChange:
            for btn in self._btns: btn.setVisible(bool(value))
        if change == self.ItemPositionChange and self.parentItem():
            self.parentItem().update()
            # 这里不用 timer 了，父级有 timer 统一处理
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
# 4. StickyNoteItem
# ------------------------------------------------------------------------------

class StickyNoteItem(BackdropNodeItem):

    def __init__(self, name='Sticky Note', text='', parent=None):
        self._text_item = None
        self._icon_item = None
        self.btn_lock = None
        self.btn_color = None
        self._text_blocks = []

        super(StickyNoteItem, self).__init__(name, text, parent)

        self._sync_timer = QtCore.QTimer()
        self._sync_timer.setInterval(30)
        self._sync_timer.timeout.connect(self._sync_pins)
        self._sync_timer.start()

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

    # --- 辅助方法：View <-> Node 转换 ---

    def get_node_by_view(self, item_view):
        """通过 GraphicsItem 查找对应的逻辑 Node 对象"""
        if not self.node: return None
        # self.node 是 StickyNote 对应的 Node 对象
        # self.node.graph 是 Graph 对象
        graph = self.node.graph
        if not graph: return None

        # 遍历 Graph 中的所有 Node，找到 view 匹配的那个
        for n in graph.all_nodes():
            if n.view == item_view:
                return n
        return None

    def get_view_by_persistent_id(self, pid):
        """通过 persistent_id 查找对应的 GraphicsItem"""
        if not self.node: return None
        graph = self.node.graph
        if not graph: return None

        for n in graph.all_nodes():
            if n.get_property('persistent_id') == pid:
                return n.view
        return None

    # ------------------------------------

    def _sync_pins(self):
        if not self.scene() or not self.isVisible() or not self._text_blocks:
            return

        need_update = False
        for block in self._text_blocks:
            pin = block.anchor_pin
            if pin and pin._target_item:
                old_pos = pin.pos()
                pin.update_position_from_target()
                if pin.pos() != old_pos:
                    need_update = True
        if need_update:
            self.update()

    def itemChange(self, change, value):
        if change == self.ItemPositionChange:
            self._sync_pins()
        return super(StickyNoteItem, self).itemChange(change, value)

    def on_text_block_changed(self):
        """保存数据：将目标节点的 persistent_id 保存下来"""
        if not self.node: return
        data = []
        for b in self._text_blocks:
            pin_data = None
            if b.anchor_pin:
                pin = b.anchor_pin
                target_pid = None

                # 获取 persistent_id
                if pin._target_item:
                    target_node = self.get_node_by_view(pin._target_item)
                    if target_node:
                        target_pid = target_node.get_property('persistent_id')

                # 保存偏移量
                offset = [pin._target_offset.x(), pin._target_offset.y()]

                pin_data = {
                    'pos': [pin.pos().x(), pin.pos().y()],
                    'target_pid': target_pid,  # 保存 PID
                    'offset': offset
                }

            data.append({
                'text': b.toPlainText(),
                'x': b.pos().x(),
                'y': b.pos().y(),
                'w': b.textWidth(),
                'size': b.font().pointSize(),
                'anchor': pin_data
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
                anchor_info = item.get('anchor')
                if anchor_info:
                    pin = NoteAnchorPin(self, block)
                    block.anchor_pin = pin

                    if isinstance(anchor_info, dict):
                        pos = anchor_info.get('pos', [0, 0])
                        pin.setPos(pos[0], pos[1])

                        # 读取 persistent_id
                        pin._temp_target_pid = anchor_info.get('target_pid')

                        # 读取偏移
                        off = anchor_info.get('offset', [0, 0])
                        pin._target_offset = QtCore.QPointF(off[0], off[1])

            # 延迟执行重连
            QtCore.QTimer.singleShot(200, self._rebind_pins_delayed)

        except Exception as e:
            print("StickyNote Load Error:", e)

    def _rebind_pins_delayed(self):
        """延迟执行：通过 persistent_id 重连"""
        if not self.scene(): return

        updated = False

        for block in self._text_blocks:
            pin = block.anchor_pin
            if not pin: continue
            if pin._target_item: continue

            target_view = None

            # 1. 尝试通过 PID 找回 (精准)
            if hasattr(pin, '_temp_target_pid') and pin._temp_target_pid:
                target_view = self.get_view_by_persistent_id(pin._temp_target_pid)

            # 2. 绑定
            if target_view:
                pin._target_item = target_view
                pin.setBrush(pin.locked_brush)
                # 理论上应该重新计算 offset 以防微小位移，但相信保存时的 offset 也行
                # pin._target_offset = pin.scenePos() - target_view.scenePos()
                updated = True

            if hasattr(pin, '_temp_target_pid'):
                del pin._temp_target_pid

        self.update()
        if updated:
            self.on_text_block_changed()

    # ----------------------------------------------------
    # 以下 UI/事件保持不变
    # ----------------------------------------------------

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
        current_rgb = self.color
        current_color = QtGui.QColor(*current_rgb)
        new_color = QtWidgets.QColorDialog.getColor(
            current_color, None, "选择注释背景颜色", QtWidgets.QColorDialog.ShowAlphaChannel
        )
        if new_color.isValid():
            c_tuple = (new_color.red(), new_color.green(), new_color.blue())
            self.color = c_tuple
            self.update()
            if self.node:
                self.node.set_color(c_tuple[0], c_tuple[1], c_tuple[2])

    def mousePressEvent(self, event):
        if self._locked:
            event.ignore();
            return
        pos = event.pos()
        item = self.scene().itemAt(event.scenePos(), QtGui.QTransform())
        if event.button() == QtCore.Qt.RightButton:
            event.accept();
            return
        if pos.y() < self._header_height:
            self.setFlag(self.ItemIsSelectable, True)
            super(StickyNoteItem, self).mousePressEvent(event);
            return
        if item and item != self and item != self._sizer:
            self.setFlag(self.ItemIsSelectable, True)
            super(StickyNoteItem, self).mousePressEvent(event);
            return
        curr_time = time.time()
        if (curr_time - self._last_click_time) < self._double_click_threshold:
            self.add_text_block("双击编辑...", pos)
            self._last_click_time = 0
            event.accept();
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
                event.accept();
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

        # --- 修改开始 ---
        # 预先定义好线的样式
        line_pen = QtGui.QPen(QtGui.QColor(0, 255, 255, 120), 2.0, QtCore.Qt.DashLine)

        for b in self._text_blocks:
            if b.anchor_pin and b.anchor_pin.scene():
                p1 = b.get_edge_point(b.anchor_pin.pos())
                p2 = b.anchor_pin.pos()

                # 【关键修复】每次画线前，都要显式设置画笔！
                # 否则如果上一次循环画了红点把笔设为了 NoPen，这里就会画不出线
                painter.setPen(line_pen)
                painter.drawLine(p1, p2)

                if b.anchor_pin._target_item:
                    painter.setBrush(QtGui.QColor(255, 50, 50))
                    painter.setPen(QtCore.Qt.NoPen)  # 这里把笔设没了，必须在下次循环前恢复
                    painter.drawEllipse(p2, 3, 3)
        # --- 修改结束 ---

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