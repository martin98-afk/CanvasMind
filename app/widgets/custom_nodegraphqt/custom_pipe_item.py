#!/usr/bin/python
import math

from NodeGraphQt.constants import (
    PipeLayoutEnum, PortTypeEnum, PipeEnum,
    Z_VAL_PIPE, Z_VAL_PORT
)
from NodeGraphQt.qgraphics.pipe import PipeItem, LivePipeItem
from PyQt5 import QtGui, QtCore

from app.utils.config import Settings


# ==========================================================
# 动画控制器 (全局单例)
# ==========================================================
class FlowController(QtCore.QObject):
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FlowController, cls).__new__(cls)
            cls._instance.timer = QtCore.QTimer()
            cls._instance.timer.setInterval(35)  # 稍微降低频率，30-35ms 视觉足够平滑
            cls._instance.timer.timeout.connect(cls._instance._refresh_pipes)
            cls._instance.offset = 0.0
            cls._instance.running_pipes = set()
        return cls._instance

    def _refresh_pipes(self):
        self.offset += 1.5  # 步长稍大一点，视觉更流畅
        if self.offset >= 100.0:
            self.offset = 0.0

        # 批量通知更新，避免信号分发开销
        for pipe in list(self.running_pipes):
            # 只有在场景中且可见时才触发
            if pipe.scene():
                pipe._current_flow_offset = self.offset
                pipe.update()

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
        # --- 性能优化核心：获取当前视图的缩放比例 (Level of Detail) ---
        lod = option.levelOfDetailFromTransform(painter.worldTransform())

        path = self.path()
        if path.isEmpty(): return

        c = self.color
        base_color = QtGui.QColor(c[0], c[1], c[2], c[3])

        if self._running:
            base_color = QtGui.QColor(64, 158, 255) if self._running_type == "input" else QtGui.QColor(50, 205, 50)
        if self._active:
            base_color = QtGui.QColor(*PipeEnum.ACTIVE_COLOR.value)
        elif self._highlight and not self._running:
            base_color = QtGui.QColor(*PipeEnum.HIGHLIGHT_COLOR.value)

        # 1. 绘制底层阴影 (极小缩放时不画)
        if lod > 0.4:
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 80), self.pen().widthF() + 1.5))
            painter.drawPath(path)

        # 2. 绘制发光层 (只有在中等以上缩放才画，这是性能大户)
        if lod > 0.7 and (self._active or self._highlight or self._is_hovered or self._running):
            glow_steps = 2  # 减少循环次数
            for i in range(glow_steps, 0, -1):
                g_col = QtGui.QColor(base_color.red(), base_color.green(), base_color.blue(), 30)
                g_pen = QtGui.QPen(g_col, self.pen().widthF() + (i * 5))
                g_pen.setCapStyle(QtCore.Qt.RoundCap)
                painter.setPen(g_pen)
                painter.drawPath(path)

        # 3. 绘制主干线 (必须画)
        main_pen = QtGui.QPen(base_color, self.pen().widthF())
        main_pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.setPen(main_pen)
        painter.drawPath(path)

        # 4. 绘制流光动画 (只有放大时才画动画，解决多视角卡顿)
        if lod > 0.5 and getattr(self, '_flow_running', False):
            painter.save()
            # 使用半透明黑或白，增强对比
            f_pen = QtGui.QPen(QtGui.QColor(0, 0, 0, 180), 3)
            f_pen.setDashPattern([10, 15])
            f_pen.setDashOffset(self._current_flow_offset)
            f_pen.setCapStyle(QtCore.Qt.RoundCap)
            painter.setPen(f_pen)
            painter.drawPath(path)
            painter.restore()

        # 5. 绘制方向箭头 (极小时不画)
        if lod > 0.6:
            self._draw_direction_pointer()

    # ==========================================================
    # 路径绘制核心逻辑 (完美还原你的避让算法)
    # ==========================================================
    def _draw_path_horizontal(self, start_port, pos1, pos2, path):
        if pos1 == pos2: return

        layout = self.viewer_pipe_layout()

        # 1. 曲线模式 (保持原样，曲线通常不强调物理避让)
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

        # 2. 折线模式 (增强版避让算法)
        elif layout == PipeLayoutEnum.ANGLE.value:
            points = []

            # 获取端口方向
            # 1 表示向右出, -1 表示向左出
            direction = 1 if start_port.port_type == PortTypeEnum.OUT.value else -1

            # 基础间距
            margin_x = 30.0

            # 计算逻辑：
            # 如果是正常向前连线 (Output 在 Input 左侧)
            is_forward = (pos2.x() > pos1.x() + margin_x * 2) if direction == 1 else (
                        pos2.x() < pos1.x() - margin_x * 2)

            if is_forward:
                # 三段式 (Z型)
                mid_x = pos1.x() + (pos2.x() - pos1.x()) / 2
                points = [
                    pos1,
                    QtCore.QPointF(mid_x, pos1.y()),
                    QtCore.QPointF(mid_x, pos2.y()),
                    pos2
                ]
            else:
                # 五段式避让 (U型绕路)
                # 1. 获取节点信息
                node_item = start_port.node
                node_rect = node_item.sceneBoundingRect()

                # 2. 决定向上绕还是向下绕
                # 如果终点在起点上方，则从上方绕行；反之亦然
                padding = 20.0
                if pos2.y() < pos1.y():
                    # 向上避让：节点的顶部再往上一点
                    bypass_y = node_rect.top() - padding
                else:
                    # 向下避让：节点的底部再往下一点
                    bypass_y = node_rect.bottom() + padding

                # 3. 计算5个关键转折点
                # p1: 出口水平延伸
                p1 = QtCore.QPointF(pos1.x() + margin_x * direction, pos1.y())
                # p2: 垂直转折到避让高度
                p2 = QtCore.QPointF(pos1.x() + margin_x * direction, bypass_y)
                # p3: 水平跨越节点，到达终点前的水平位置
                p3 = QtCore.QPointF(pos2.x() - margin_x * direction, bypass_y)
                # p4: 垂直转折到终点高度
                p4 = QtCore.QPointF(pos2.x() - margin_x * direction, pos2.y())

                points = [pos1, p1, p2, p3, p4, pos2]

            # 过滤重合点并绘制圆角
            clean_points = [points[0]]
            for i in range(1, len(points)):
                if (points[i] - clean_points[-1]).manhattanLength() > 0.1:
                    clean_points.append(points[i])

            self._draw_rounded_path(path, clean_points, radius=15.0)

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
        self.set_pipe_styling(color=color, width=self._get_state_width("running"), style=self.style)
        self.setZValue(Z_VAL_PIPE + 10)
        self.start_flow()

    def reset(self):
        self._running = False
        self._active = False
        self._highlight = False
        self.set_pipe_styling(color=self.color, width=self._get_state_width("normal"), style=self.style)
        self.setZValue(Z_VAL_PIPE)
        self.stop_flow()

    def start_flow(self):
        if not getattr(self, '_flow_running', False):
            self._flow_running = True
            # 直接向控制器注册自己
            self._controller.register_pipe(self)

    def stop_flow(self):
        if getattr(self, '_flow_running', False):
            self._flow_running = False
            self._controller.unregister_pipe(self)

    def _update_anim(self, offset):
        if self.scene() and self.isVisible():
            self._current_flow_offset = offset
            self.update()

    def activate(self):
        self._active = True
        self.set_pipe_styling(color=PipeEnum.ACTIVE_COLOR.value, width=self._get_state_width("activate"), style=self.style)
        self.setZValue(Z_VAL_PORT-0.5)
        self.start_flow()

    def highlight(self):
        self._highlight = True
        if not self._running:
            self.set_pipe_styling(color=PipeEnum.HIGHLIGHT_COLOR.value, width=self._get_state_width("highlight"), style=self.style)
        self.update()
        self.setZValue(Z_VAL_PORT-0.5)
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
        # 预留足够的空间给发光层 (16.5 是 glow 计算出的最大增量)
        margin = 20.0
        rect.adjust(-margin, -margin, margin, margin)
        return rect

    def shape(self):
        path = self.path()
        if path.isEmpty():
            return super(CustomPipeItem, self).shape()

        # 1. 创建原本的宽大点击区域 (与你之前的逻辑一致)
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(self.pen().widthF() + 20.0)
        stroke_path = stroker.createStroke(path)

        # 2. 定义端口处的“安全半径”
        port_safety_radius = 15.0

        # 3. 创建需要挖空的区域
        cutout = QtGui.QPainterPath()

        # 获取路径的起点 (0.0) 和终点 (1.0)
        start_pt = path.pointAtPercent(0.0)
        cutout.addEllipse(start_pt, port_safety_radius, port_safety_radius)

        if path.length() > 0:
            end_pt = path.pointAtPercent(1.0)
            cutout.addEllipse(end_pt, port_safety_radius, port_safety_radius)

        # 4. 核心运算：从线的点击形状中“减去”端口区域
        final_shape = stroke_path.subtracted(cutout)

        return final_shape

    def _get_state_width(self, state):
        """根据状态返回计算后的线宽"""
        offsets = {
            'normal': 0,
            'highlight': 1,
            'active': 2,
            'running': 1
        }
        return int(max(1.0, Settings.get_instance().canvas_pipe_width.value + offsets.get(state, 0)))  # 确保最小宽度1.0


class CustomLivePipeItem(CustomPipeItem, LivePipeItem):

    def __init__(self):
        self._flow_running = False
        self._start_port = None
        self._current_flow_offset = 0.0
        self._is_hovered = False
        self._controller = FlowController()
        super(CustomLivePipeItem, self).__init__()

    def draw_path(self, start_port, end_port=None, cursor_pos=None, color=None):
        if cursor_pos is None:
            return
        self._start_port = start_port
        LivePipeItem.draw_path(self, start_port, end_port, cursor_pos, color)
        self.set_pipe_styling(color=PipeEnum.ACTIVE_COLOR.value, width=self._get_state_width("highlight"),
                              style=self.style)