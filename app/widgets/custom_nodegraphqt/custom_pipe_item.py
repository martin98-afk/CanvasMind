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
        self.offset -= 0.8
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
        # --- 关键：在调用基类 init 之前初始化变量 ---
        self._running = False
        self._flow_running = False
        self._current_flow_offset = 0.0
        self._is_hovered = False
        self._controller = FlowController()

        # 调用基类构造函数（它会触发 self.reset()）
        super(CustomPipeItem, self).__init__()

        self.setAcceptHoverEvents(True)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        path = self.path()
        if path.isEmpty(): return

        # 颜色逻辑
        base_color = QtGui.QColor(*self.color)
        if self._running and self.type == "input":
            base_color = QtGui.QColor(*(64, 158, 255, 255))
        elif self._running and self.type == "output":
            base_color = QtGui.QColor(*(50, 205, 50, 255))
        if self._active:
            base_color = QtGui.QColor(*PipeEnum.ACTIVE_COLOR.value)
        if self._highlight:
            base_color = QtGui.QColor(*PipeEnum.HIGHLIGHT_COLOR.value)

        # 1. 绘制底层发光 (Glow)
        if self._active or self._highlight or self._is_hovered or self._running:
            painter.save()
            glow_steps = 3 if self._active else 2
            for i in range(glow_steps, 0, -1):
                alpha = 40 if self._active else 20
                g_col = QtGui.QColor(base_color.red(), base_color.green(), base_color.blue(), alpha)
                g_pen = QtGui.QPen(g_col, self.pen().widthF() + (i * 4))
                g_pen.setCapStyle(QtCore.Qt.RoundCap)
                painter.setPen(g_pen)
                painter.drawPath(path)
            painter.restore()

        # 2. 绘制主干线
        painter.save()
        main_pen = QtGui.QPen(base_color, self.pen().widthF())
        main_pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.setPen(main_pen)
        painter.drawPath(path)
        painter.restore()

        # 3. 绘制流动动画
        # 增加属性检查，防止初始化过程中报错
        if getattr(self, '_flow_running', False):
            painter.save()
            bright_color = QtGui.QColor(0, 0, 0, 200)
            f_pen = QtGui.QPen(bright_color, 2.0)
            f_pen.setDashPattern([10, 20])
            f_pen.setDashOffset(-self._current_flow_offset)
            f_pen.setCapStyle(QtCore.Qt.RoundCap)
            painter.setPen(f_pen)
            painter.drawPath(path)
            painter.restore()

    def _draw_path_horizontal(self, start_port, pos1, pos2, path):
        if pos1 == pos2:
            return

        def calc_node_height(node):
            if hasattr(node, "view"):
                return node.view.boundingRect().height()
            return node.boundingRect().height()

        layout = self.viewer_pipe_layout()
        # 获取水平和垂直距离
        if layout == PipeLayoutEnum.CURVED.value:
            dx = pos2.x() - pos1.x()
            # 改进的贝塞尔曲线算法：处理回头路
            ctr_offset = max(abs(dx) * 0.5, 40.0)
            if dx < 0: ctr_offset = max(abs(dx) * 0.7, 120.0)
            ctr_offset = min(ctr_offset, 300.0)

            cp1 = QtCore.QPointF(pos1.x() + ctr_offset, pos1.y())
            cp2 = QtCore.QPointF(pos2.x() - ctr_offset, pos2.y())
            if start_port.port_type == PortTypeEnum.IN.value:
                cp1 = QtCore.QPointF(pos1.x() - ctr_offset, pos1.y())
                cp2 = QtCore.QPointF(pos2.x() + ctr_offset, pos2.y())
            path.cubicTo(cp1, cp2, pos2)
        elif layout == PipeLayoutEnum.ANGLE.value:
            dx = abs(pos1.x() - pos2.x())
            points = [pos1]

            side_margin = min(40.0, dx * 0.4) if dx > 5 else 5.0

            is_forward = False
            if start_port.port_type == PortTypeEnum.OUT.value:
                is_forward = pos2.x() > pos1.x() + (side_margin * 2)
            else:
                is_forward = pos2.x() < pos1.x() - (side_margin * 2)

            if is_forward:
                # 正常向前的折线
                mid_x = pos1.x() + (pos2.x() - pos1.x()) / 2
                points.append(QtCore.QPointF(mid_x, pos1.y()))
                points.append(QtCore.QPointF(mid_x, pos2.y()))
            else:
                # -------------------------------------------------------
                # [修正逻辑]：向上固定100，向下维持节点高度
                # -------------------------------------------------------
                node_h = calc_node_height(start_port.node)

                if pos1.y() > pos2.y():
                    # 起始节点在结束节点【上方】，需要向上避让
                    y_offset = -100
                else:
                    # 起始节点在结束节点【下方】，需要向下避让，使用原来的节点高度
                    y_offset = node_h

                # 根据端口类型计算绕行点
                direct = 1 if start_port.port_type == PortTypeEnum.OUT.value else -1

                p1_ext = QtCore.QPointF(pos1.x() + side_margin * direct, pos1.y())
                p1_bypass = QtCore.QPointF(pos1.x() + side_margin * direct, pos1.y() + y_offset)
                p2_bypass = QtCore.QPointF(pos2.x() - side_margin * direct, pos1.y() + y_offset)
                p2_ext = QtCore.QPointF(pos2.x() - side_margin * direct, pos2.y())

                points.extend([p1_ext, p1_bypass, p2_bypass, p2_ext])

            points.append(pos2)

            # 过滤极近点并绘制圆角
            clean_points = [points[0]]
            for i in range(1, len(points)):
                if (points[i] - clean_points[-1]).manhattanLength() > 0.5:
                    clean_points.append(points[i])

            self._draw_rounded_path(path, clean_points, radius=16.0)

        self.setPath(path)

    def _draw_rounded_path(self, path, points, radius=10.0):
        """
        带安全检查的圆角绘制
        """
        if not points:
            return
        if len(points) < 3:
            # 如果只有一两个点，直接画线，没法做圆角
            path.moveTo(points[0])
            for p in points[1:]:
                path.lineTo(p)
            return

        path.moveTo(points[0])
        for i in range(1, len(points) - 1):
            p1 = points[i - 1]
            p2 = points[i]
            p3 = points[i + 1]

            # 计算两段线段的长度
            d12 = math.sqrt((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2)
            d23 = math.sqrt((p3.x() - p2.x()) ** 2 + (p3.y() - p2.y()) ** 2)

    def hoverEnterEvent(self, event):
        self._is_hovered = True
        self.update()
        super(CustomPipeItem, self).hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super(CustomPipeItem, self).hoverLeaveEvent(event)

    def running(self, type="input"):
        self._running = True
        self.type = type
        color = (50, 205, 50, 255) if type == "output" else (64, 158, 255, 255)  # 蓝色
        self.set_pipe_styling(color=color, width=4, style=self.style)
        self.setZValue(Z_VAL_PIPE + 10)
        self.start_flow()

    def activate(self):
        self._active = True
        self.set_pipe_styling(color=PipeEnum.ACTIVE_COLOR.value, width=5, style=self.style)
        self.setZValue(Z_VAL_PIPE + 10)
        self.start_flow()

    def highlight(self):
        self._highlight = True
        self.set_pipe_styling(color=PipeEnum.HIGHLIGHT_COLOR.value, width=4, style=self.style)
        self.setZValue(Z_VAL_PIPE + 10)
        self.start_flow()

    def reset(self):
        self._active = False
        self._highlight = False
        self._running = False
        # 补齐 set_pipe_styling 的三个参数
        color = getattr(self, 'color', PipeEnum.COLOR.value)
        style = getattr(self, 'style', PipeEnum.DRAW_TYPE_DEFAULT.value)
        self.set_pipe_styling(color=color, width=4, style=style)
        self.setZValue(Z_VAL_PIPE)
        self.stop_flow()

    def start_flow(self):
        if not getattr(self, '_flow_running', False):
            self._flow_running = True
            self._controller.frame_updated.connect(self._update_anim)
            self._controller.register_pipe(self)
            self.update()

    def stop_flow(self):
        # 增加 hasattr 检查，彻底杜绝初始化阶段的 AttributeError
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


# ==========================================================
# 交互中的连线 (Live Pipe)
# ==========================================================
# 调整继承顺序：CustomPipeItem 在前，确保重写的 paint/reset 被优先调用
class CustomLivePipeItem(CustomPipeItem, LivePipeItem):
    def __init__(self):
        # 同样，在 LivePipeItem 初始化前，确保变量存在
        self._flow_running = False
        self._current_flow_offset = 0.0
        self._is_hovered = False
        self._controller = FlowController()

        # 显式调用基类构造
        super(CustomLivePipeItem, self).__init__()

    def draw_path(self, start_port, end_port=None, cursor_pos=None, color=None):
        # 确保使用 LivePipeItem 原始的路径计算逻辑（它是跟随鼠标的）
        LivePipeItem.draw_path(self, start_port, end_port, cursor_pos, color)