#!/usr/bin/python
import math

from NodeGraphQt.constants import (
    PipeLayoutEnum,
    PortTypeEnum, PipeEnum, Z_VAL_PIPE, Z_VAL_NODE, ITEM_CACHE_MODE
)
from NodeGraphQt.qgraphics.pipe import PipeItem, LivePipeItem
from PyQt5 import QtGui, QtWidgets, QtCore


# 全局动画控制器（单例模式思想）
class FlowController(QtCore.QObject):
    _instance = None
    frame_updated = QtCore.pyqtSignal(float)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FlowController, cls).__new__(cls)
            cls._instance.timer = QtCore.QTimer()
            cls._instance.timer.setInterval(30) # 30ms 刷新率
            cls._instance.timer.timeout.connect(cls._instance._on_timeout)
            cls._instance.offset = 0.0
            cls._instance.running_pipes = set()
        return cls._instance

    def _on_timeout(self):
        # 递减偏移量，模拟流动
        self.offset += 0.5
        if self.offset >= 100.0:
            self.offset = 0.0
        # 通知所有监听者重绘
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


class CustomPipeItem(PipeItem):
    _flow_running = False

    def __init__(self, input_port=None, output_port=None):
        super(CustomPipeItem, self).__init__()
        self._hover_pen = QtGui.QPen()
        self._hover_pen.setWidth(15)
        self._hover_pen.setCapStyle(QtCore.Qt.RoundCap)
        self._hover_pen.setJoinStyle(QtCore.Qt.MiterJoin)
        self._current_flow_offset = 0.0
        self._controller = FlowController()

    # ==========================================================
    # [新增] 动画控制方法
    # ==========================================================
    def _update_anim(self, offset):
        if self.scene() and self.isVisible():
            self._current_flow_offset = offset
            self.update()

    def start_flow(self):
        if not self._flow_running:
            self._flow_running = True
            self._controller.frame_updated.connect(self._update_anim)
            self._controller.register_pipe(self)
            self.update()

    def stop_flow(self):
        if self._flow_running:
            self._flow_running = False
            try:
                self._controller.frame_updated.disconnect(self._update_anim)
            except:
                pass
            self._controller.unregister_pipe(self)
            self.update()

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemSceneChange and value is None:
            self.stop_flow()
        return super(CustomPipeItem, self).itemChange(change, value)

    # ==========================================================
    # [新增] 覆写 paint 方法实现绘图叠加
    # ==========================================================
    def paint(self, painter, option, widget):
        # 1. 绘制底线 (深色背景，模拟边框)
        painter.save()
        bg_pen = QtGui.QPen(QtGui.QColor(20, 20, 20))
        bg_pen.setWidthF(self.pen().widthF() + 2.5)
        painter.setPen(bg_pen)
        painter.drawPath(self.path())
        painter.restore()

        # 2. 绘制正常的线
        super(CustomPipeItem, self).paint(painter, option, widget)

        # 3. 绘制流动效果 (ComfyUI 风格：高亮虚线)
        if self._flow_running:
            painter.save()
            path = self.path()

            # 创建流动笔刷
            # 颜色：稍微透明的亮色 (ComfyUI 选中时通常是金色或白色)
            flow_color = QtGui.QColor(255, 255, 255, 180)
            if self._active:
                flow_color = QtGui.QColor(255, 200, 50, 255)  # 激活时金色

            pen = QtGui.QPen(flow_color, 3)
            pen.setCapStyle(QtCore.Qt.RoundCap)

            # 关键：设置虚线模式
            # [线段长度, 间隔长度]
            dash_pattern = [5, 15]
            pen.setDashPattern(dash_pattern)

            # 关键：设置偏移量实现动画
            # 这里利用 path length 做一个归一化，或者直接用 offset
            # Qt 的 setDashOffset 并不总是沿着 path 完美流动，但在较长曲线上效果不错
            # 更好的方式是配合 QPainterPathStroker (开销稍大) 或直接用 offset
            pen.setDashOffset(self._current_flow_offset)

            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawPath(path)

            painter.restore()

    # ==========================================================

    def _draw_path_horizontal(self, start_port, pos1, pos2, path):
        """
        优化后的路径绘制逻辑，修复近距离扭曲问题
        """
        if pos1 == pos2:
            return

        def calc_node_height(node):
            if hasattr(node, "view"):
                return node.view.boundingRect().height()
            return node.boundingRect().height()

        layout = self.viewer_pipe_layout()

        # 获取水平和垂直距离
        dx = abs(pos1.x() - pos2.x())
        dy = abs(pos1.y() - pos2.y())

        # 1. 【曲线布局优化】解决近距离扭曲
        if layout == PipeLayoutEnum.CURVED.value:
            # --- 核心算法：自适应切线 ---
            # 默认切线长度
            tangent = max(abs(dx) * 0.6, 20)

            # 修正：处理“回头路”的情况 (结束点在起始点左侧)
            # ComfyUI 在这种情况下会把线拉得很长，形成一个大大的 S 型
            is_backward = False
            if start_port.port_type == PortTypeEnum.IN.value:
                if pos1.x() > pos2.x(): is_backward = True
            else:
                if pos1.x() > pos2.x(): is_backward = True  # 假设左进右出，如果右边的x反而小

            if is_backward:
                tangent = max(tangent, 150)  # 回头时切线拉长

            # 限制切线最大值，防止太夸张
            if tangent > 300: tangent = 300

            cp1 = QtCore.QPointF(pos1.x() + tangent, pos1.y())
            cp2 = QtCore.QPointF(pos2.x() - tangent, pos2.y())

            # 根据端口方向调整控制点方向 (这里假设标准的左进右出)
            if start_port.port_type == PortTypeEnum.IN.value:
                cp1 = QtCore.QPointF(pos1.x() - tangent, pos1.y())
                cp2 = QtCore.QPointF(pos2.x() + tangent, pos2.y())

            path.cubicTo(cp1, cp2, pos2)
            self.setPath(path)

        # 2. 【折线布局优化】实现动态避让
        elif layout == PipeLayoutEnum.ANGLE.value:
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

            # --- 安全检查：防止除零 ---
            if d12 < 0.001 or d23 < 0.001:
                path.lineTo(p2)
                continue

            # 动态调整半径，确保半径不会超过线段长度的一半
            actual_radius = min(radius, d12 / 2, d23 / 2)

            # 计算切点位置
            p2_start = p2 - (p2 - p1) * (actual_radius / d12)
            p2_end = p2 + (p3 - p2) * (actual_radius / d23)

            path.lineTo(p2_start)
            path.quadTo(p2, p2_end)

        path.lineTo(points[-1])

    def shape(self):
        """
        重写碰撞检测形状。
        技巧：在生成线的碰撞形状后，减去首尾两端的圆形区域。
        这样在端口附近点击时，不会判定为点击了线，而是直接穿透给端口。
        """
        path = self.path()
        if path.elementCount() == 0:
            return super(CustomPipeItem, self).shape()

        # 1. 生成原本的宽线条碰撞区
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(self._hover_pen.width())
        stroker.setCapStyle(self._hover_pen.capStyle())
        stroker.setJoinStyle(self._hover_pen.joinStyle())
        pipe_shape = stroker.createStroke(path)

        # 2. 定义挖孔逻辑
        # 获取路径的首尾点（即连接端口的位置）
        start_pos = path.pointAtPercent(0.0)
        end_pos = path.pointAtPercent(1.0)

        # 定义一个“安全半径”，在这个半径内点击，算作点击端口，不算点击线
        # 建议比端口视觉半径大一点，比如 12-15px
        safe_radius = 5.0

        cutout = QtGui.QPainterPath()
        cutout.addEllipse(start_pos, safe_radius, safe_radius)
        cutout.addEllipse(end_pos, safe_radius, safe_radius)

        # 3. 从线的形状中减去端口区域 (Subtraction)
        # 这样鼠标在端口附近时，shape() 覆盖不到，事件就会漏下去给 PortItem
        return pipe_shape.subtracted(cutout)

    def activate(self):
        self._active = True
        self.set_pipe_styling(
            color=PipeEnum.ACTIVE_COLOR.value,
            width=3,
            style=PipeEnum.DRAW_TYPE_DEFAULT.value
        )
        # 修正：不要用 Z_VAL_NODE + 0.5，这会遮挡端口
        # 使用 Z_VAL_PIPE + 2 (确保比未选中的线高，但比节点低)
        self.setZValue(Z_VAL_PIPE + 2)
        self.start_flow()

    def highlight(self):
        self._highlight = True
        self.set_pipe_styling(
            color=PipeEnum.HIGHLIGHT_COLOR.value,
            width=2,
            style=PipeEnum.DRAW_TYPE_DEFAULT.value
        )
        # 修正：同上
        self.setZValue(Z_VAL_PIPE + 2)
        self.start_flow()

    def reset(self):
        self._active = False
        self._highlight = False
        self.set_pipe_styling(color=self.color, width=2, style=self.style)
        self._draw_direction_pointer()
        self.setZValue(Z_VAL_PIPE)
        self.stop_flow()


class CustomLivePipeItem(CustomPipeItem, LivePipeItem):

    def draw_path(self, start_port, end_port=None, cursor_pos=None, color=None):
        super(LivePipeItem, self).draw_path(start_port, end_port, cursor_pos)
        self.draw_index_pointer(start_port, cursor_pos, color)