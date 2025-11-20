#!/usr/bin/python

from NodeGraphQt.constants import (
    PipeLayoutEnum,
    PortTypeEnum, PipeEnum, Z_VAL_PIPE, Z_VAL_NODE
)
from NodeGraphQt.qgraphics.pipe import PipeItem, LivePipeItem
from NodeGraphQt.qgraphics.port import PortItem
from Qt import QtCore


class CustomPipeItem(PipeItem):

    def _draw_path_horizontal(self, start_port, pos1, pos2, path):
        """
        Draws the horizontal path between ports.

        Args:
            start_port (PortItem): port used to draw the starting point.
            pos1 (QPointF): start port position.
            pos2 (QPointF): end port position.
            path (QPainterPath): path to draw.
        """
        def calc_node_height(node):
            """
            Calculates the height of a node.

            Args:
                node (NodeItem): node to calculate the height of.

            Returns:
                float: height of the node.
            """
            if getattr(node, "_widgets", None) is None:
                return node.boundingRect().height()
            height = 0
            for widget in node._widgets.values():
                if not widget.isVisible():
                    continue
                # ✅ 关键：使用 widget.widget().sizeHint() 获取真实尺寸
                real_widget = widget.widget()
                if real_widget is not None:
                    w_size = real_widget.sizeHint()
                    height += w_size.height() + 3
                else:
                    # fallback（理论上不会走到这里）
                    br = widget.boundingRect()
                    height += br.height() + 3

            return node.boundingRect().height()


        if self.viewer_pipe_layout() == PipeLayoutEnum.CURVED.value:
            ctr_offset_x1, ctr_offset_x2 = pos1.x(), pos2.x()
            tangent = abs(ctr_offset_x1 - ctr_offset_x2)

            max_width = start_port.node.boundingRect().width()
            tangent = min(tangent, max_width)
            if start_port.port_type == PortTypeEnum.IN.value:
                ctr_offset_x1 -= tangent
                ctr_offset_x2 += tangent
            else:
                ctr_offset_x1 += tangent
                ctr_offset_x2 -= tangent

            ctr_point1 = QtCore.QPointF(ctr_offset_x1, pos1.y())
            ctr_point2 = QtCore.QPointF(ctr_offset_x2, pos2.y())
            path.cubicTo(ctr_point1, ctr_point2, pos2)
            self.setPath(path)
        elif self.viewer_pipe_layout() == PipeLayoutEnum.ANGLE.value:
            ctr_offset_x1, ctr_offset_x2 = pos1.x(), pos2.x()
            ctr_offset_y1, ctr_offset_y2 = pos1.y(), pos2.y()
            distance = abs(ctr_offset_x1 - ctr_offset_x2)/2
            if start_port.port_type == PortTypeEnum.IN.value:
                if ctr_offset_x1 >= ctr_offset_x2:
                    ctr_offset_x1 -= distance
                    ctr_offset_x2 += distance

                    ctr_point1 = QtCore.QPointF(ctr_offset_x1, pos1.y())
                    ctr_point2 = QtCore.QPointF(ctr_offset_x2, pos2.y())
                    path.lineTo(ctr_point1)
                    path.lineTo(ctr_point2)
                    path.lineTo(pos2)
                else:
                    start_node_height = calc_node_height(start_port.node)
                    distance2 = abs(ctr_offset_y1 - ctr_offset_y2)
                    if ctr_offset_y1 <= ctr_offset_y2:
                        ctr_offset_x1 -= 40
                        ctr_offset_x2 += 40
                        ctr_offset_y1 += start_node_height
                        ctr_offset_y2 -= distance2 - start_node_height
                    elif ctr_offset_y1 > ctr_offset_y2:
                        ctr_offset_x1 -= 40
                        ctr_offset_x2 += 40
                        ctr_offset_y1 -= 100
                        ctr_offset_y2 += distance2 - 100

                    ctr_point1 = QtCore.QPointF(ctr_offset_x1, pos1.y())
                    ctr_point2 = QtCore.QPointF(ctr_offset_x1, ctr_offset_y1)
                    ctr_point3 = QtCore.QPointF(ctr_offset_x2, ctr_offset_y2)
                    ctr_point4 = QtCore.QPointF(ctr_offset_x2, pos2.y())
                    path.lineTo(ctr_point1)
                    path.lineTo(ctr_point2)
                    path.lineTo(ctr_point3)
                    path.lineTo(ctr_point4)
                    path.lineTo(pos2)
            else:
                if ctr_offset_x1 <= ctr_offset_x2:
                    ctr_offset_x1 += distance
                    ctr_offset_x2 -= distance

                    ctr_point1 = QtCore.QPointF(ctr_offset_x1, pos1.y())
                    ctr_point2 = QtCore.QPointF(ctr_offset_x2, pos2.y())
                    path.lineTo(ctr_point1)
                    path.lineTo(ctr_point2)
                    path.lineTo(pos2)
                else:
                    start_node_height = calc_node_height(start_port.node)
                    distance2 = abs(ctr_offset_y1 - ctr_offset_y2)
                    if ctr_offset_y1 <= ctr_offset_y2:
                        ctr_offset_x1 += 40
                        ctr_offset_x2 -= 40
                        ctr_offset_y1 += distance2 - 100
                        ctr_offset_y2 -= 100
                    else:
                        ctr_offset_x1 += 40
                        ctr_offset_x2 -= 40
                        ctr_offset_y1 -= distance2 - start_node_height
                        ctr_offset_y2 += start_node_height

                    ctr_point1 = QtCore.QPointF(ctr_offset_x1, pos1.y())
                    ctr_point2 = QtCore.QPointF(ctr_offset_x1, ctr_offset_y1)
                    ctr_point3 = QtCore.QPointF(ctr_offset_x2, ctr_offset_y2)
                    ctr_point4 = QtCore.QPointF(ctr_offset_x2, pos2.y())
                    path.lineTo(ctr_point1)
                    path.lineTo(ctr_point2)
                    path.lineTo(ctr_point3)
                    path.lineTo(ctr_point4)
                    path.lineTo(pos2)

            self.setPath(path)

    def activate(self):
        self._active = True
        self.set_pipe_styling(
            color=PipeEnum.ACTIVE_COLOR.value,
            width=3,
            style=PipeEnum.DRAW_TYPE_DEFAULT.value
        )
        self.setZValue(Z_VAL_NODE+1)

    def highlight(self):
        self._highlight = True
        self.set_pipe_styling(
            color=PipeEnum.HIGHLIGHT_COLOR.value,
            width=2,
            style=PipeEnum.DRAW_TYPE_DEFAULT.value
        )
        self.setZValue(Z_VAL_NODE+1)

    def reset(self):
        """
        reset the pipe state and styling.
        """
        self._active = False
        self._highlight = False
        self.set_pipe_styling(color=self.color, width=2, style=self.style)
        self._draw_direction_pointer()
        self.setZValue(Z_VAL_PIPE)


class CustomLivePipeItem(CustomPipeItem, LivePipeItem):

    def draw_path(self, start_port, end_port=None, cursor_pos=None, color=None):
        """
        re-implemented to also update the index pointer arrow position.

        Args:
            start_port (PortItem): port used to draw the starting point.
            end_port (PortItem): port used to draw the end point.
            cursor_pos (QtCore.QPointF): cursor position if specified this
                will be the draw end point.
            color (list[int]): override arrow index pointer color. (r, g, b)
        """
        super(LivePipeItem, self).draw_path(start_port, end_port, cursor_pos)
        self.draw_index_pointer(start_port, cursor_pos, color)