#!/usr/bin/python
import math

from NodeGraphQt.constants import (
    PipeLayoutEnum,
    PortTypeEnum, PipeEnum, Z_VAL_PIPE, Z_VAL_NODE, ITEM_CACHE_MODE
)
from NodeGraphQt.qgraphics.pipe import PipeItem, LivePipeItem
from PyQt5 import QtGui, QtWidgets
from Qt import QtCore


class CustomPipeItem(PipeItem):
    _flow_running = False

    def __init__(self, input_port=None, output_port=None):
        super(CustomPipeItem, self).__init__()
        # --- 修正：定义一个更细的笔用于 hover 区域 ---
        self._hover_pen = QtGui.QPen()
        self._hover_pen.setWidth(8)
        self._hover_pen.setCapStyle(QtCore.Qt.RoundCap)
        self._hover_pen.setJoinStyle(QtCore.Qt.MiterJoin)
        # --- 结束修正 ---

        # ==========================================================
        # [新增] 数据流动画所需的属性
        # ==========================================================
        self._flow_anim_timer = QtCore.QTimer()
        self._flow_anim_timer.setInterval(30)  # 约 30 FPS
        self._flow_anim_timer.timeout.connect(self._update_flow_anim)
        self._flow_offset = 0.0
        # ==========================================================

    # ==========================================================
    # [新增] 动画控制方法
    # ==========================================================
    def start_flow(self):
        """启动数据流动画"""
        if not self._flow_running:
            self._flow_running = True
            # 临时关闭缓存以确保动画流畅刷新
            self.setCacheMode(QtWidgets.QGraphicsItem.NoCache)
            self._flow_anim_timer.start()

    def stop_flow(self):
        """停止数据流动画"""
        if self._flow_running:
            self._flow_running = False
            self._flow_anim_timer.stop()
            self._flow_offset = 0.0
            # 恢复缓存模式（如果你原有的逻辑需要缓存）
            self.setCacheMode(ITEM_CACHE_MODE)
            self.update()

    def _update_flow_anim(self):
        """定时器回调，更新虚线偏移量"""
        self._flow_offset -= 1.0  # 控制流速和方向
        if self._flow_offset <= -1000.0:
            self._flow_offset = 0.0
        self.update()

    # ==========================================================

    # ==========================================================
    # [新增] 覆写 itemChange 以确保删除时停止计时器
    # ==========================================================
    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemSceneChange and value is None:
            self.stop_flow()
        return super(CustomPipeItem, self).itemChange(change, value)

    def _draw_flow_particles(self, painter):
        if not self._flow_running:
            return

        path = self.path()
        # 算出当前时间点粒子应该在的位置 (0.0 - 1.0)
        # self._flow_offset 可以映射到 0-1 之间
        t = (self._flow_offset % 100) / 100.0

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(255, 255, 255, 200))  # 白色粒子

        # 在路径上均匀分布 3 个粒子
        partical_num = 5
        for i in range(partical_num):
            percent = (t + i * 1 / partical_num) % 1.0
            pos = path.pointAtPercent(percent)
            painter.drawEllipse(pos, 4, 4)  # 绘制直径为 3 的粒子

    # ==========================================================
    # [新增] 覆写 paint 方法实现绘图叠加
    # ==========================================================
    def paint(self, painter, option, widget):
        """
        覆写 paint 方法。
        首先调用父类方法绘制原本的连线，
        然后如果动画开启，在上方绘制流动的虚线。
        """
        painter.save()
        # 先画一层比主线宽 2 像素的黑色底线
        bg_pen = QtGui.QPen(QtGui.QColor(30, 30, 30))
        bg_pen.setWidthF(self.pen().widthF() + 2.0)
        painter.setPen(bg_pen)
        painter.drawPath(self.path())
        painter.restore()
        # 1. 绘制原有的连线外观（保持你不变的逻辑）
        super(CustomPipeItem, self).paint(painter, option, widget)

        # 2. 绘制流动动画
        if self._flow_running:
            painter.save()
            self._draw_flow_particles(painter)
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
            # 1. 基础切线是水平距离的一半
            tangent = dx * 0.5

            # 2. 修正：当水平距离 dx 非常小时，如果还用固定最小值(如40)，曲线会扭曲。
            # 我们基于垂直距离 dy 补偿一点弧度，但限制它不能在 dx 很小时过大。
            if dx < 100:
                # 在近距离时，切线由 dx 和 dy 共同决定，比例缩小
                # 这里的公式保证了当 dx 趋近 0 时，切线不会保持在 40 导致“打结”
                tangent = min(max(dx * 0.5, dy * 0.1), 40.0)
                # 确保即使重合也有极小的一段直线引出
                tangent = max(tangent, 15.0)
            else:
                # 远距离时限制最大切线长度，防止曲线过大
                tangent = min(tangent, 150.0)

            # 判断端口类型决定切线方向
            if start_port.port_type == PortTypeEnum.IN.value:
                cp1 = QtCore.QPointF(pos1.x() - tangent, pos1.y())
                cp2 = QtCore.QPointF(pos2.x() + tangent, pos2.y())
            else:
                cp1 = QtCore.QPointF(pos1.x() + tangent, pos1.y())
                cp2 = QtCore.QPointF(pos2.x() - tangent, pos2.y())

            path.cubicTo(cp1, cp2, pos2)

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
        Defines the shape used for hover detection.
        """
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(self._hover_pen.width())
        stroker.setCapStyle(self._hover_pen.capStyle())
        stroker.setJoinStyle(self._hover_pen.joinStyle())
        return stroker.createStroke(self.path())

    def activate(self):
        self._active = True
        self.set_pipe_styling(
            color=PipeEnum.ACTIVE_COLOR.value,
            width=3,
            style=PipeEnum.DRAW_TYPE_DEFAULT.value
        )
        self.setZValue(Z_VAL_NODE + 0.5)
        # 可选：激活时自动开始流动
        self.start_flow()

    def highlight(self):
        self._highlight = True
        self.set_pipe_styling(
            color=PipeEnum.HIGHLIGHT_COLOR.value,
            width=2,
            style=PipeEnum.DRAW_TYPE_DEFAULT.value
        )
        self.setZValue(Z_VAL_NODE + 0.5)
        self.start_flow()

    def reset(self):
        """
        reset the pipe state and styling.
        """
        self._active = False
        self._highlight = False
        self.set_pipe_styling(color=self.color, width=2, style=self.style)
        self._draw_direction_pointer()
        self.setZValue(Z_VAL_PIPE)
        # 可选：重置时停止流动
        self.stop_flow()


class CustomLivePipeItem(CustomPipeItem, LivePipeItem):

    def draw_path(self, start_port, end_port=None, cursor_pos=None, color=None):
        super(LivePipeItem, self).draw_path(start_port, end_port, cursor_pos)
        self.draw_index_pointer(start_port, cursor_pos, color)