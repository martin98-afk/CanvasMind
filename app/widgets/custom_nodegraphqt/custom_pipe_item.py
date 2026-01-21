#!/usr/bin/python
import math
from PyQt5 import QtGui, QtWidgets, QtCore
from NodeGraphQt.constants import (
    PipeLayoutEnum, PortTypeEnum, PipeEnum,
    Z_VAL_PIPE, ITEM_CACHE_MODE
)
from NodeGraphQt.qgraphics.pipe import PipeItem, LivePipeItem


# ==========================================================
# 动画控制器 (全局单例)
# ==========================================================
class FlowController(QtCore.QObject):
    _instance = None
    frame_updated = QtCore.pyqtSignal(float)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FlowController, cls).__new__(cls)
            cls._instance.timer = QtCore.QTimer()
            cls._instance.timer.setInterval(30)
            cls._instance.timer.timeout.connect(cls._instance._on_timeout)
            cls._instance.offset = 0.0
            cls._instance.running_pipes = set()
        return cls._instance

    def _on_timeout(self):
        self.offset -= 1.0
        if self.offset <= -100.0:
            self.offset = 0.0
        self.frame_updated.emit(self.offset)

    def register_pipe(self, pipe):
        self.running_pipes.add(pipe)
        if not self.timer.isActive():
            self.timer.start()

    def unregister_pipe(self, pipe):
        if pipe in self.running_pipes:
            self.running_pipes.remove(pipe)
        if not self.running_pipes:
            self.timer.stop()


# ==========================================================
# 优化后的连接线 (基类)
# ==========================================================
class CustomPipeItem(PipeItem):
    def __init__(self):
        self._running = False
        self._running_type = ""
        self._flow_running = False
        self._current_flow_offset = 0.0
        self._is_hovered = False
        self._controller = FlowController()

        super(CustomPipeItem, self).__init__()
        self.setAcceptHoverEvents(True)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        path = self.path()
        if path.isEmpty(): return

        # --- 颜色逻辑 ---
        c = self.color
        base_color = QtGui.QColor(c[0], c[1], c[2], c[3])

        if self._running:
            if self._running_type == "input":
                base_color = QtGui.QColor(64, 158, 255, 255)  # 蓝
            else:
                base_color = QtGui.QColor(50, 205, 50, 255)  # 绿

        if self._active:
            base_color = QtGui.QColor(*PipeEnum.ACTIVE_COLOR.value)
        elif self._highlight and not self._running:
            base_color = QtGui.QColor(*PipeEnum.HIGHLIGHT_COLOR.value)

        # 1. 绘制底层阴影
        painter.save()
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 80), self.pen().widthF() + 1.5))
        painter.drawPath(path)
        painter.restore()

        # 2. 绘制发光层
        if self._active or self._highlight or self._is_hovered or self._running:
            painter.save()
            glow_steps = 3 if self._active else 2
            alpha_val = 40 if self._active else 25
            for i in range(glow_steps, 0, -1):
                g_col = QtGui.QColor(base_color.red(), base_color.green(), base_color.blue(), alpha_val)
                g_pen = QtGui.QPen(g_col, self.pen().widthF() + (i * 4.5))
                g_pen.setCapStyle(QtCore.Qt.RoundCap)
                painter.setPen(g_pen)
                painter.drawPath(path)
            painter.restore()

        # 3. 绘制主干线
        painter.save()
        main_pen = QtGui.QPen(base_color, self.pen().widthF())
        main_pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.setPen(main_pen)
        painter.drawPath(path)
        painter.restore()

        # 4. 绘制流光动画 (亮白色)
        if getattr(self, '_flow_running', False):
            painter.save()
            bright_white = QtGui.QColor(0, 0, 0, 180)
            f_pen = QtGui.QPen(bright_white, 2.0)
            f_pen.setDashPattern([10, 15])
            f_pen.setDashOffset(-self._current_flow_offset)
            f_pen.setCapStyle(QtCore.Qt.RoundCap)
            painter.setPen(f_pen)
            painter.drawPath(path)
            painter.restore()

        # 5. 绘制方向箭头
        self._draw_direction_pointer()

    # ==========================================================
    # 路径绘制核心逻辑 (完美还原你的避让算法)
    # ==========================================================
    def _draw_path_horizontal(self, start_port, pos1, pos2, path):
        if pos1 == pos2: return

        layout = self.viewer_pipe_layout()

        # 1. 曲线模式
        if layout == PipeLayoutEnum.CURVED.value:
            dx = pos2.x() - pos1.x()
            ctr_offset = max(abs(dx) * 0.5, 40.0)
            if dx < 0: ctr_offset = max(abs(dx) * 0.7, 120.0)
            ctr_offset = min(ctr_offset, 300.0)
            cp1 = QtCore.QPointF(pos1.x() + ctr_offset, pos1.y())
            cp2 = QtCore.QPointF(pos2.x() - ctr_offset, pos2.y())
            if start_port.port_type == PortTypeEnum.IN.value:
                cp1 = QtCore.QPointF(pos1.x() - ctr_offset, pos1.y())
                cp2 = QtCore.QPointF(pos2.x() + ctr_offset, pos2.y())
            path.cubicTo(cp1, cp2, pos2)

        # 2. 折线模式 (还原避让逻辑)
        elif layout == PipeLayoutEnum.ANGLE.value:
            def calc_node_height(node):
                if hasattr(node, "view"): return node.view.boundingRect().height()
                return node.boundingRect().height()

            dx = abs(pos1.x() - pos2.x())
            points = [pos1]
            side_margin = min(40.0, dx * 0.4) if dx > 5 else 5.0

            is_forward = False
            if start_port.port_type == PortTypeEnum.OUT.value:
                is_forward = pos2.x() > pos1.x() + (side_margin * 2)
            else:
                is_forward = pos2.x() < pos1.x() - (side_margin * 2)

            if is_forward:
                mid_x = pos1.x() + (pos2.x() - pos1.x()) / 2
                points.append(QtCore.QPointF(mid_x, pos1.y()))
                points.append(QtCore.QPointF(mid_x, pos2.y()))
            else:
                # 避让逻辑
                node_h = calc_node_height(start_port.node)
                y_offset = -100 if pos1.y() > pos2.y() else node_h
                direct = 1 if start_port.port_type == PortTypeEnum.OUT.value else -1

                p1_ext = QtCore.QPointF(pos1.x() + side_margin * direct, pos1.y())
                p1_bypass = QtCore.QPointF(pos1.x() + side_margin * direct, pos1.y() + y_offset)
                p2_bypass = QtCore.QPointF(pos2.x() - side_margin * direct, pos1.y() + y_offset)
                p2_ext = QtCore.QPointF(pos2.x() - side_margin * direct, pos2.y())
                points.extend([p1_ext, p1_bypass, p2_bypass, p2_ext])

            points.append(pos2)

            # 过滤并画圆角
            clean_points = [points[0]]
            for i in range(1, len(points)):
                if (points[i] - clean_points[-1]).manhattanLength() > 0.5:
                    clean_points.append(points[i])
            self._draw_rounded_path(path, clean_points, radius=16.0)

        self.setPath(path)

    def _draw_rounded_path(self, path, points, radius=10.0):
        if not points: return
        if len(points) < 3:
            path.moveTo(points[0])
            for p in points[1:]: path.lineTo(p)
            return

        path.moveTo(points[0])
        for i in range(1, len(points) - 1):
            p1, p2, p3 = points[i - 1], points[i], points[i + 1]
            d12 = math.sqrt((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2)
            d23 = math.sqrt((p3.x() - p2.x()) ** 2 + (p3.y() - p2.y()) ** 2)
            if d12 < 0.001 or d23 < 0.001:
                path.lineTo(p2)
                continue
            r = min(radius, d12 / 2, d23 / 2)
            p2_start = p2 - (p2 - p1) * (r / d12)
            p2_end = p2 + (p3 - p2) * (r / d23)
            path.lineTo(p2_start)
            path.quadTo(p2, p2_end)
        path.lineTo(points[-1])

    # ==========================================================
    # 交互与状态控制
    # ==========================================================
    def running(self, type="input"):
        self._running = True
        self._running_type = type
        color = (50, 205, 50, 255) if type == "output" else (64, 158, 255, 255)
        self.set_pipe_styling(color=color, width=4, style=self.style)
        self.setZValue(Z_VAL_PIPE + 10)
        self.start_flow()

    def reset(self):
        self._active = False
        self._highlight = False
        self._running = False
        self.set_pipe_styling(color=self.color, width=3, style=self.style)
        self.setZValue(Z_VAL_PIPE)
        self.stop_flow()

    def start_flow(self):
        if not getattr(self, '_flow_running', False):
            self._flow_running = True
            self._controller.frame_updated.connect(self._update_anim)
            self._controller.register_pipe(self)
            self.update()

    def stop_flow(self):
        if hasattr(self, '_flow_running') and self._flow_running:
            self._flow_running = False
            try:
                self._controller.frame_updated.disconnect(self._update_anim)
            except:
                pass
            self._controller.unregister_pipe(self)
            self.update()

    def _update_anim(self, offset):
        if self.scene() and self.isVisible():
            self._current_flow_offset = offset
            self.update()

    def activate(self):
        self._active = True
        self.set_pipe_styling(color=PipeEnum.ACTIVE_COLOR.value, width=5, style=self.style)
        self.setZValue(Z_VAL_PIPE + 10)
        self.start_flow()

    def highlight(self):
        self._highlight = True
        if not self._running:
            self.set_pipe_styling(color=PipeEnum.HIGHLIGHT_COLOR.value, width=4, style=self.style)
        self.update()
        self.setZValue(Z_VAL_PIPE + 10)
        self.start_flow()

    def hoverEnterEvent(self, event):
        self._is_hovered = True
        self.update()
        super(CustomPipeItem, self).hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super(CustomPipeItem, self).hoverLeaveEvent(event)

    def boundingRect(self):
        # 获取路径本身的矩形
        rect = self.path().boundingRect()
        # 预留足够的空间给发光层 (16.5 是你 glow 计算出的最大增量)
        # 我们这里给个 20.0 保证安全
        margin = 20.0
        rect.adjust(-margin, -margin, margin, margin)
        return rect

    def shape(self):
        # 同样扩大碰撞检测和重绘区域的形状
        path = QtGui.QPainterPath()
        # 使用旋转/加宽后的路径作为形状
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(self.pen().widthF() + 20.0)
        return stroker.createStroke(self.path())


class CustomLivePipeItem(CustomPipeItem, LivePipeItem):
    def __init__(self):
        self._flow_running = False
        self._current_flow_offset = 0.0
        self._is_hovered = False
        self._controller = FlowController()
        super(CustomLivePipeItem, self).__init__()

    def draw_path(self, start_port, end_port=None, cursor_pos=None, color=None):
        LivePipeItem.draw_path(self, start_port, end_port, cursor_pos, color)