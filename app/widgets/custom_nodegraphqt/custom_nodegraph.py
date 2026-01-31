# -*- coding: utf-8 -*-
import copy
import json

from NodeGraphQt import NodeGraph, BaseNode, NodeGraphMenu, GroupNode
from NodeGraphQt.base.commands import PortConnectedCmd
from NodeGraphQt.base.menu import BaseMenu
from NodeGraphQt.constants import (
    PipeLayoutEnum,
    ViewerEnum,
    Z_VAL_PIPE, LayoutDirectionEnum, PortTypeEnum,
)
from NodeGraphQt.errors import NodeDeletionError
from NodeGraphQt.nodes.port_node import PortOutputNode, PortInputNode
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem
from NodeGraphQt.qgraphics.pipe import PipeItem
from NodeGraphQt.qgraphics.slicer import SlicerPipeItem
from NodeGraphQt.widgets.node_graph import SubGraphWidget
from NodeGraphQt.widgets.scene import NodeScene
from NodeGraphQt.widgets.tab_search import TabSearchMenuWidget
from NodeGraphQt.widgets.viewer import NodeViewer
from PyQt5.QtCore import QTimer
from Qt import QtGui, QtCore, QtWidgets
from qtpy import QtGui, QtCore, QtWidgets

from app.components.base import GlobalVariableContext
from app.nodes.group_node import GroupPortInputNode, GroupPortOutputNode
from app.utils.config import Settings
from app.utils.utils import serialize_for_json, deserialize_from_json
from app.widgets.basic_widget.combo_widget import CustomComboBox
from app.widgets.custom_nodegraphqt.custom_node_menu import CustomNodesMenu, BaseMenu
from app.widgets.custom_nodegraphqt.custom_pipe_item import CustomLivePipeItem, CustomPipeItem
from app.widgets.node_widget.base import CustomNodeBaseWidget

# --- 常量配置 ---
SNAP_THRESHOLD = 15.0  # 吸附距离阈值
SNAP_COLOR = QtGui.QColor(255, 128, 0, 200)  # 橙色对齐线


class CustomNodeScene(NodeScene):

    def _draw_dots(self, painter, rect, pen, grid_size):
        """
        draws the grid dots in the scene.

        Args:
            painter (QtGui.QPainter): painter object.
            rect (QtCore.QRectF): rect object.
            pen (QtGui.QPen): pen object.
            grid_size (int): grid size.
        """
        zoom = self.viewer().get_zoom()
        if zoom < 0:
            grid_size = int(abs(zoom) / 0.3 + 1) * grid_size

        left = int(rect.left())
        right = int(rect.right())
        top = int(rect.top())
        bottom = int(rect.bottom())

        first_left = left - (left % grid_size)
        first_top = top - (top % grid_size)

        pen.setWidth(grid_size // 10)
        painter.setPen(pen)

        [painter.drawPoint(int(x), int(y))
         for x in range(first_left, right, grid_size)
         for y in range(first_top, bottom, grid_size)]

    def mousePressEvent(self, event):
        selected_nodes = self.viewer().selected_nodes()
        if self.viewer():
            self.viewer().sceneMousePressEvent(event)
        super(NodeScene, self).mousePressEvent(event)
        keep_selection = any([
            event.button() == QtCore.Qt.MiddleButton,
            event.modifiers() == QtCore.Qt.AltModifier
        ])
        if keep_selection:
            for node in selected_nodes:
                node.setSelected(True)


class CustomNodeViewer(NodeViewer):

    def __init__(self, parent=None, undo_stack=None):
        super(CustomNodeViewer, self).__init__(parent)
        self._navigation_mode = False
        self._custom_menu = None  # 用于存放 CustomGraphMenu 的引用
        self._temp_connection_source = None  # 用于存放拉线的起始端口
        self.setScene(CustomNodeScene(self))
        # --- 性能优化：初始开启抗锯齿 ---
        self.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
        self.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)

        # --- 性能优化：微调 View 参数 ---
        # 视口更新模式：BoundingRect 是最安全的，SmartViewportUpdate 有时会闪烁
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.BoundingRectViewportUpdate)

        # 背景是动态网格（随视口移动），CacheBackground 反而会降低性能（因为每次移动都要重绘缓存）。
        self.setCacheMode(QtWidgets.QGraphicsView.CacheBackground)

        # 优化拖动时的重绘策略
        self.setOptimizationFlag(QtWidgets.QGraphicsView.DontAdjustForAntialiasing)

        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setAcceptDrops(True)
        self.resize(850, 800)

        # --- 内部状态初始化 ---
        self._pipe_layout = PipeLayoutEnum.CURVED.value
        self._panning = False
        self._detached_port = None
        self._start_port = None
        self._origin_pos = None
        self._previous_pos = QtCore.QPoint(int(self.width() / 2),
                                           int(self.height() / 2))
        self._prev_selection_nodes = []
        self._prev_selection_pipes = []
        self._node_positions = {}

        # --- 新增：对齐线对象 (初始化一次，复用) ---
        self._snap_lines_item = QtWidgets.QGraphicsPathItem()
        self._snap_lines_item.setZValue(Z_VAL_PIPE + 100)  # 最顶层
        snap_pen = QtGui.QPen(SNAP_COLOR, 1.0, QtCore.Qt.DashLine)
        snap_pen.setCosmetic(True)  # 缩放时不改变线宽
        self._snap_lines_item.setPen(snap_pen)
        self.scene().addItem(self._snap_lines_item)
        self._snap_lines_item.hide()
        # -------------------------------------

        self._rubber_band = QtWidgets.QRubberBand(
            QtWidgets.QRubberBand.Rectangle, self
        )
        self._rubber_band.isActive = False

        text_color = QtGui.QColor(*tuple(map(
            lambda i, j: i - j, (255, 255, 255),
            ViewerEnum.BACKGROUND_COLOR.value
        )))
        text_color.setAlpha(50)
        self._cursor_text = QtWidgets.QGraphicsTextItem()
        self._cursor_text.setFlag(
            QtWidgets.QGraphicsTextItem.ItemIsSelectable, False
        )
        self._cursor_text.setDefaultTextColor(text_color)
        self._cursor_text.setZValue(Z_VAL_PIPE - 1)
        font = self._cursor_text.font()
        font.setPointSize(7)
        self._cursor_text.setFont(font)
        self.scene().addItem(self._cursor_text)

        self._LIVE_PIPE = CustomLivePipeItem()
        self._LIVE_PIPE.setVisible(False)
        self.scene().addItem(self._LIVE_PIPE)

        self._SLICER_PIPE = SlicerPipeItem()
        self._SLICER_PIPE.setVisible(False)
        self.scene().addItem(self._SLICER_PIPE)

        self._search_widget = TabSearchMenuWidget()
        self._search_widget.search_submitted.connect(self._on_search_submitted)

        # workaround fix for shortcuts from the non-native menu.
        # actions don't seem to trigger so we create a hidden menu bar.
        self._ctx_menu_bar = QtWidgets.QMenuBar(self)
        self._ctx_menu_bar.setNativeMenuBar(False)
        # shortcuts don't work with "setVisibility(False)".
        self._ctx_menu_bar.setMaximumSize(0, 0)

        # context menus.
        self._ctx_graph_menu = BaseMenu('NodeGraph', self)
        self._ctx_node_menu = BaseMenu('Nodes', self)

        if undo_stack:
            self._undo_action = undo_stack.createUndoAction(self, '&Undo')
            self._redo_action = undo_stack.createRedoAction(self, '&Redo')
        else:
            self._undo_action = None
            self._redo_action = None

        self._build_context_menus()

        self.acyclic = True
        self.pipe_collision = False
        self.pipe_slicing = True

        self.LMB_state = False
        self.RMB_state = False
        self.MMB_state = False
        self.ALT_state = False
        self.CTRL_state = False
        self.SHIFT_state = False
        self.COLLIDING_state = False

        # connection constrains.
        self.accept_connection_types = None
        self.reject_connection_types = None

    def set_navigation_mode(self, enabled):
        """设置是否为拖拽模式"""
        self._navigation_mode = enabled
        # 切换模式时，如果正在拉框，强制取消
        if enabled and self._rubber_band.isActive:
            self._rubber_band.hide()
            self._rubber_band.isActive = False

    # --- 处理对齐逻辑 ---
    def _handle_snapping(self, moving_nodes):
        """
        计算吸附并更新对齐虚线
        """
        if not moving_nodes:
            self._snap_lines_item.hide()
            return

        # 1. 获取主节点（只以第一个选中的节点作为参考，避免逻辑冲突）
        primary_node = moving_nodes[0]
        primary_rect = primary_node.sceneBoundingRect()

        # 2. 性能优化：只搜索当前视口范围内的其他节点，而不是全图搜索
        view_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        # 稍微扩大一点搜索范围，提升体验
        search_rect = view_rect.adjusted(-50, -50, 50, 50)
        nearby_items = self.scene().items(search_rect)

        target_nodes = []
        for item in nearby_items:
            # 排除自己、排除不可见节点、排除非节点对象
            if isinstance(item, AbstractNodeItem) and item not in moving_nodes and item.isVisible():
                target_nodes.append(item)

        if not target_nodes:
            self._snap_lines_item.hide()
            return

        # 3. 计算阈值（随缩放调整，保证视觉距离一致）
        zoom = self.get_zoom()
        # 避免 zoom 为 -1 (极小) 导致除零
        scale_factor = max(0.1, 1.0 + zoom) if zoom >= 0 else max(0.1, 1.0 / (1.0 + abs(zoom)))
        current_threshold = SNAP_THRESHOLD / scale_factor

        offset_x, offset_y = 0.0, 0.0
        snapped_x = False
        snapped_y = False

        # 存储线段数据用于绘制
        lines_to_draw = []

        p_center = primary_rect.center()

        # --- X轴对齐 (左、右、中) ---
        for target in target_nodes:
            t_rect = target.sceneBoundingRect()
            t_center = t_rect.center()

            # 左对左
            if abs(primary_rect.left() - t_rect.left()) < current_threshold:
                offset_x = t_rect.left() - primary_rect.left()
                lines_to_draw.append((t_rect.left(), primary_rect, t_rect, 'vertical'))
                snapped_x = True
            # 右对右
            elif abs(primary_rect.right() - t_rect.right()) < current_threshold:
                offset_x = t_rect.right() - primary_rect.right()
                lines_to_draw.append((t_rect.right(), primary_rect, t_rect, 'vertical'))
                snapped_x = True
            # 中对中
            elif abs(p_center.x() - t_center.x()) < current_threshold:
                offset_x = t_center.x() - p_center.x()
                lines_to_draw.append((t_center.x(), primary_rect, t_rect, 'vertical'))
                snapped_x = True

            if snapped_x: break

        # --- Y轴对齐 (顶、底、中) ---
        for target in target_nodes:
            t_rect = target.sceneBoundingRect()
            t_center = t_rect.center()

            # 顶对顶
            if abs(primary_rect.top() - t_rect.top()) < current_threshold:
                offset_y = t_rect.top() - primary_rect.top()
                lines_to_draw.append((t_rect.top(), primary_rect, t_rect, 'horizontal'))
                snapped_y = True
            # 底对底
            elif abs(primary_rect.bottom() - t_rect.bottom()) < current_threshold:
                offset_y = t_rect.bottom() - primary_rect.bottom()
                lines_to_draw.append((t_rect.bottom(), primary_rect, t_rect, 'horizontal'))
                snapped_y = True
            # 中对中
            elif abs(p_center.y() - t_center.y()) < current_threshold:
                offset_y = t_center.y() - p_center.y()
                lines_to_draw.append((t_center.y(), primary_rect, t_rect, 'horizontal'))
                snapped_y = True

            if snapped_y: break

        # 4. 应用位置吸附
        if snapped_x or snapped_y:
            for node in moving_nodes:
                node.setPos(node.pos() + QtCore.QPointF(offset_x, offset_y))

            # 5. 绘制虚线
            path = QtGui.QPainterPath()
            for pos_val, r1, r2, orientation in lines_to_draw:
                if orientation == 'vertical':
                    # 计算垂直线的上下端点
                    top = min(r1.top(), r2.top()) - 20
                    bottom = max(r1.bottom(), r2.bottom()) + 20
                    # 校正视觉位置（加上吸附的偏移量，让线看起来是对准的）
                    vis_x = pos_val
                    path.moveTo(vis_x, top)
                    path.lineTo(vis_x, bottom)
                else:
                    # 计算水平线的左右端点
                    left = min(r1.left(), r2.left()) - 20
                    right = max(r1.right(), r2.right()) + 20
                    vis_y = pos_val
                    path.moveTo(left, vis_y)
                    path.lineTo(right, vis_y)

            self._snap_lines_item.setPath(path)
            self._snap_lines_item.show()
        else:
            self._snap_lines_item.hide()

    # ---------------------------

    def wheelEvent(self, event):
        # 保持你原本的逻辑不变
        pos = event.pos()
        item = self.itemAt(pos)
        if isinstance(item, CustomNodeBaseWidget):
            widget = item.widget().get_node_widget()
            if hasattr(widget, 'code_editor') and widget.code_editor.hasFocus():
                widget.code_editor.wheelEvent(event)
                return
            elif hasattr(widget, "summary_label") and widget.summary_label.hasFocus():
                widget.summary_label.wheelEvent(event)
                return
        elif isinstance(item, QtWidgets.QGraphicsProxyWidget):
            for widget in QtWidgets.QApplication.allWidgets():
                if isinstance(widget, CustomComboBox) and widget.view().window().isVisible():
                    widget.view().wheelEvent(event)
                    return

        try:
            delta = event.delta()
        except AttributeError:
            delta = event.angleDelta().y()
            if delta == 0:
                delta = event.angleDelta().x()

        try:
            self._set_viewer_zoom(delta, pos=event.pos())
        except AttributeError:
            self._set_viewer_zoom(delta, pos=event.position().toPoint())

    def establish_connection(self, start_port, end_port):
        # 保持你原本的逻辑不变
        pipe = CustomPipeItem()
        self.scene().addItem(pipe)
        pipe.set_connections(start_port, end_port)
        pipe.draw_path(pipe.input_port, pipe.output_port)
        if start_port.node.selected or end_port.node.selected:
            pipe.highlight()
        if not start_port.node.visible or not end_port.node.visible:
            pipe.hide()

    def mousePressEvent(self, event):
        # --- 性能优化：交互开始时，临时关闭抗锯齿 ---
        # ----------------------------------------
        if (event.button() == QtCore.Qt.MiddleButton or
            (event.button() == QtCore.Qt.LeftButton and event.modifiers() == QtCore.Qt.AltModifier) or
            (event.button() == QtCore.Qt.LeftButton and self._navigation_mode)  # <--- 新增条件
        ):
            self._panning = True
        if event.button() == QtCore.Qt.LeftButton:
            self.LMB_state = True
        elif event.button() == QtCore.Qt.RightButton:
            self.RMB_state = True
        elif event.button() == QtCore.Qt.MiddleButton:
            self.MMB_state = True
        if self._panning:
            # 这会让拖动帧率显著提升，而不会改变渲染架构
            self.setRenderHint(QtGui.QPainter.Antialiasing, False)

        self._origin_pos = event.pos()
        self._previous_pos = event.pos()
        (self._prev_selection_nodes,
         self._prev_selection_pipes) = self.selected_items()

        if self._search_widget.isVisible():
            self.tab_search_toggle()

        map_pos = self.mapToScene(event.pos())

        if self.pipe_slicing:
            slicer_mode = all([
                self.ALT_state, self.SHIFT_state, self.LMB_state
            ])
            if slicer_mode:
                self._SLICER_PIPE.draw_path(map_pos, map_pos)
                self._SLICER_PIPE.setVisible(True)
                return

        if self.ALT_state:
            return

        items = self._items_near(map_pos, None, 20, 20)
        pipes = []
        nodes = []
        backdrop = None
        for itm in items:
            if isinstance(itm, PipeItem):
                pipes.append(itm)
            elif isinstance(itm, AbstractNodeItem):
                if isinstance(itm, BackdropNodeItem):
                    backdrop = itm
                    continue
                nodes.append(itm)

        if nodes:
            self.MMB_state = False

        selection = set([])

        if self.LMB_state:
            if self.SHIFT_state:
                if items and backdrop == items[0]:
                    backdrop.selected = not backdrop.selected
                    if backdrop.selected:
                        selection.add(backdrop)
                    for n in backdrop.get_nodes():
                        n.selected = backdrop.selected
                        if backdrop.selected:
                            selection.add(n)
                else:
                    for node in nodes:
                        node.selected = not node.selected
                        if node.selected:
                            selection.add(node)
            elif self.CTRL_state:
                if items and backdrop == items[0]:
                    backdrop.selected = False
                else:
                    for node in nodes:
                        node.selected = False
            else:
                if backdrop:
                    selection.add(backdrop)
                    for n in backdrop.get_nodes():
                        selection.add(n)
                for node in nodes:
                    if node.selected:
                        selection.add(node)

        selection.update(self.selected_nodes())
        self._node_positions.update({n: n.xy_pos for n in selection})

        if self.LMB_state and not items and not self._navigation_mode:
            rect = QtCore.QRect(self._previous_pos, QtCore.QSize())
            rect = rect.normalized()
            map_rect = self.mapToScene(rect).boundingRect()
            self.scene().update(map_rect)
            self._rubber_band.setGeometry(rect)
            self._rubber_band.isActive = True

        if self.CTRL_state:
            return

        if self.SHIFT_state:
            if pipes:
                pipes[0].reset()
                port = pipes[0].port_from_pos(map_pos, reverse=True)
                if not port.locked and port.multi_connection:
                    self._cursor_text.setPlainText('')
                    self._cursor_text.setVisible(False)
                    self.start_live_connection(port)
            return

        if not self._LIVE_PIPE.isVisible():
            super(NodeViewer, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # import time
        # if not hasattr(self, '_last_pan_time'):
        #     self._last_pan_time = time.time()
        #     self._pan_frames = 0
        #
        # if self._panning:
        #     self._pan_frames += 1
        #     if time.time() - self._last_pan_time > 1.0:
        #         print(f"Pan FPS: {self._pan_frames}")
        #         self._last_pan_time = time.time()
        #         self._pan_frames = 0
        # 注入导航模式下的平移逻辑 (模仿 Alt+LMB)
        if self._navigation_mode and self.LMB_state and not self.ALT_state:
            previous_pos = self.mapToScene(self._previous_pos)
            current_pos = self.mapToScene(event.pos())
            delta = previous_pos - current_pos
            self._set_viewer_pan(delta.x(), delta.y())

        super(CustomNodeViewer, self).mouseMoveEvent(event)
        # 1. 修正基础条件判断：如果是导航模式，则不判定为“正在拖动节点”
        is_dragging_nodes = (
                self.LMB_state and
                not self.ALT_state and
                not self.SHIFT_state and
                not self._rubber_band.isActive and
                not self._navigation_mode
        )

        if is_dragging_nodes:
            selected_nodes = [
                i for i in self.scene().selectedItems()
                if isinstance(i, AbstractNodeItem)
            ]
            if any(getattr(n, '_is_resizing', False) for n in selected_nodes):
                if self._snap_lines_item.isVisible():
                    self._snap_lines_item.hide()
            else:
                self._handle_snapping(selected_nodes)
        else:
            if self._snap_lines_item.isVisible():
                self._snap_lines_item.hide()

    # ---------------------------------------------

    def mouseReleaseEvent(self, event):
        # --- 对齐功能：鼠标松开，立即隐藏对齐线 ---
        self._snap_lines_item.hide()
        self._snap_lines_item.setPath(QtGui.QPainterPath())  # 清空路径
        # -------------------------------------
        # 1. 记录拉线状态
        live_pipe_active = self._LIVE_PIPE.isVisible()
        # 注意：使用 self._start_port，这是 NodeGraphQt 内部记录起始端口的变量
        start_port = self._LIVE_PIPE._start_port if live_pipe_active else None

        # 2. 检测释放位置是否是空白处
        scene_pos = self.mapToScene(event.pos())
        items = self.scene().items(scene_pos)
        from NodeGraphQt.qgraphics.port import PortItem
        on_port = any(isinstance(i, PortItem) for i in items)

        # 3. ComfyUI 触发逻辑：正在拉线 且 左键松开 且 在空白处
        if live_pipe_active and start_port and not on_port and event.button() == QtCore.Qt.LeftButton:
            if hasattr(self, '_custom_menu') and self._custom_menu:
                # 暂存端口，给菜单创建节点后使用
                self._temp_connection_source = start_port

                # 手动触发你的自定义菜单显示
                self._custom_menu.show_at_cursor(event.globalPos())

                # 如果弹出菜单了，可能需要阻止基类的一些默认选择逻辑
                self.LMB_state = False
                super(CustomNodeViewer, self).mouseReleaseEvent(event)
                return
        # 处理平移
        was_panning = self._panning
        if event.button() == QtCore.Qt.LeftButton:
            self.LMB_state = False
            if event.modifiers() == QtCore.Qt.AltModifier:
                self._panning = False
        elif event.button() == QtCore.Qt.RightButton:
            self.RMB_state = False
        elif event.button() == QtCore.Qt.MiddleButton:
            self.MMB_state = False
            self._panning = False
        if was_panning:
            self.setRenderHint(QtGui.QPainter.Antialiasing, True)
        if self._SLICER_PIPE.isVisible():
            self._on_pipes_sliced(self._SLICER_PIPE.path())
            p = QtCore.QPointF(0.0, 0.0)
            self._SLICER_PIPE.draw_path(p, p)
            self._SLICER_PIPE.setVisible(False)

        if self._rubber_band.isActive:
            self._rubber_band.isActive = False
            if self._rubber_band.isVisible():
                rect = self._rubber_band.rect()
                map_rect = self.mapToScene(rect).boundingRect()
                self._rubber_band.hide()

                rect = QtCore.QRect(self._origin_pos, event.pos()).normalized()
                rect_items = self.scene().items(
                    self.mapToScene(rect).boundingRect()
                )
                node_ids = []
                for item in rect_items:
                    if isinstance(item, AbstractNodeItem):
                        node_ids.append(item.id)

                if node_ids:
                    prev_ids = [
                        n.id for n in self._prev_selection_nodes
                        if not n.selected
                    ]
                    self.node_selected.emit(node_ids[0])
                    self.node_selection_changed.emit(node_ids, prev_ids)

                self.scene().update(map_rect)
                return

        moved_nodes = {
            n: xy_pos for n, xy_pos in self._node_positions.items()
            if n.xy_pos != xy_pos
        }
        if moved_nodes and not self.COLLIDING_state:
            self.moved_nodes.emit(moved_nodes)

        self._node_positions = {}

        nodes, pipes = self.selected_items()
        if self.COLLIDING_state and nodes and pipes:
            self.insert_node.emit(pipes[0], nodes[0].id, moved_nodes)

        if not was_panning:
            prev_ids = [n.id for n in self._prev_selection_nodes if not n.selected]
            nodes, _ = self.selected_items()
            node_ids = [n.id for n in nodes if n not in self._prev_selection_nodes]
            self.node_selection_changed.emit(node_ids, prev_ids)

        self._prev_selection_nodes = [n for n in self.scene().selectedItems() if isinstance(n, AbstractNodeItem)]

        super(NodeViewer, self).mouseReleaseEvent(event)


class CustomNodeGraph(NodeGraph):

    def __init__(self, parent, **kwargs):
        super(CustomNodeGraph, self).__init__(parent, **kwargs)
        self._register_context_menu()

    def _register_context_menu(self):
        """
        Register the default context menus.
        """
        if not self._viewer:
            return
        menus = self._viewer.context_menus()
        if menus.get('graph'):
            self._context_menu['graph'] = NodeGraphMenu(self, menus['graph'])
        if menus.get('nodes'):
            self._context_menu['nodes'] = CustomNodesMenu(self, menus['nodes'])

    def _on_node_selected(self, node_id):
        """
        called when a node in the viewer is selected on left click.
        (emits the node object when the node is clicked)

        Args:
            node_id (str): node id emitted by the viewer.
        """
        node = self.get_node_by_id(node_id)
        if node is None:
            return
        self.node_selected.emit(node)

    def copy_nodes(self, nodes=None):
        """
        Copy nodes to the clipboard as a JSON formatted ``str``.

        See Also:
            :meth:`NodeGraph.cut_nodes`

        Args:
            nodes (list[NodeGraphQt.BaseNode]):
                list of nodes (default: selected nodes).
        """
        nodes = nodes or self.selected_nodes()
        if not nodes:
            return False
        clipboard = QtWidgets.QApplication.clipboard()
        serial_data = self._serialize(nodes)
        serial_str = json.dumps(serialize_for_json(serial_data))
        if serial_str:
            clipboard.setText(serial_str)
            return True
        return False

    def paste_nodes(self, adjust_graph_style=True):
        """
        Pastes nodes copied from the clipboard.

        Args:
            adjust_graph_style (bool): if true adjust the node graph properties
                                        other wise only the nodes are pasted.
        Returns:
            list[NodeGraphQt.BaseNode]: list of pasted node instances.
        """
        clipboard = QtWidgets.QApplication.clipboard()
        cb_text = clipboard.text()
        if not cb_text:
            return

        try:
            serial_data = deserialize_from_json(json.loads(cb_text))
        except json.decoder.JSONDecodeError as e:
            print('ERROR: Can\'t Decode Clipboard Data:\n'
                  '"{}"'.format(cb_text))
            return

        self._undo_stack.beginMacro('pasted nodes')
        self.clear_selection()
        nodes, _ = self._deserialize(serial_data, relative_pos=True, adjust_graph_style=adjust_graph_style)
        if nodes is None: return
        [n.set_selected(True) for n in nodes]
        self._undo_stack.endMacro()
        return nodes

    def expand_group_node(self, node):
        """
        Expands a group node session in a new tab.

        Args:
            node (NodeGraphQt.GroupNode): group node.

        Returns:
            SubGraph: sub node graph used to manage the group node session.
        """
        if not isinstance(node, GroupNode):
            return
        if self._widget is None:
            raise RuntimeError('NodeGraph.widget not initialized!')

        self.viewer().clear_key_state()
        self.viewer().clearFocus()

        if node.id in self._sub_graphs:
            sub_graph = self._sub_graphs[node.id]
            tab_index = self._widget.indexOf(sub_graph.widget)
            self._widget.setCurrentIndex(tab_index)
            return sub_graph

        # build new sub graph.
        node_factory = copy.deepcopy(self.node_factory)
        layout_direction = self.layout_direction()
        kwargs = {
            'layout_direction': self.layout_direction(),
            'pipe_style': self.pipe_style(),
        }
        sub_graph = CustomSubGraph(self,
                             node=node,
                             node_factory=node_factory,
                             **kwargs)

        # populate the sub graph.
        session = node.get_sub_graph_session()
        sub_graph.deserialize_session(session)

        # store reference to expanded.
        self._sub_graphs[node.id] = sub_graph

        # open new tab at root level.
        self.widget.add_viewer(sub_graph.widget, node.name(), node.id)
        sub_graph.viewer().zoom_to_nodes([n.view for n in sub_graph.all_nodes()])
        return sub_graph

    def _deserialize(self, data, relative_pos=False, pos=None, adjust_graph_style=True):
        """
        deserialize node data.
        (used internally by the node graph)

        Args:
            data (dict): node data.
            relative_pos (bool): position node relative to the cursor.
            pos (tuple or list): custom x, y position.
            adjust_graph_style (bool): if true adjust the node graph properties

        Returns:
            list[NodeGraphQt.Nodes]: list of node instances.
        """
        if isinstance(data, str): return
        self._viewer.scene().blockSignals(True)
        self._viewer.setUpdatesEnabled(False)
        node_resize_memory = Settings.get_instance().canvas_resize_memory.value
        # Recursive function to convert last lists to sets
        def convert_last_list_to_set(d):
            for key, value in d.items():
                if isinstance(value, dict):
                    convert_last_list_to_set(value)
                elif isinstance(value, list):
                    d[key] = set(value)  # convert list to set

        for attr_name, attr_value in data.get("graph", {}).items():
            if adjust_graph_style:
                if attr_name == "layout_direction":
                    self.set_layout_direction(attr_value)
                elif attr_name == "acyclic":
                    self.set_acyclic(attr_value)
                elif attr_name == "pipe_collision":
                    self.set_pipe_collision(attr_value)
                elif attr_name == "pipe_slicing":
                    self.set_pipe_slicing(attr_value)
                elif attr_name == "pipe_style":
                    self.set_pipe_style(attr_value)

            # connection constrains.
            if attr_name == 'accept_connection_types':
                attr_value = json.loads(attr_value)
                convert_last_list_to_set(attr_value)
                self.model.accept_connection_types = attr_value

            elif attr_name == 'reject_connection_types':
                attr_value = json.loads(attr_value)
                convert_last_list_to_set(attr_value)
                self.model.reject_connection_types = attr_value

        # 分离 backdrop 节点和其他节点
        nodes_data = data.get('nodes', {})
        non_backdrop_nodes_data = {}
        backdrop_nodes_data = {}

        for n_id, n_data in nodes_data.items():
            # 判断是否为 backdrop 节点
            node_type = n_data.get('type_', '')
            if 'control_flow' in node_type.lower():
                backdrop_nodes_data[n_id] = n_data
            else:
                non_backdrop_nodes_data[n_id] = n_data

        # 先构建非 backdrop 节点
        nodes = {}

        # 处理非 backdrop 节点
        for n_id, n_data in non_backdrop_nodes_data.items():
            identifier = n_data['type_']
            node_width, node_height = n_data.get('width'), n_data.get('height')
            node = self._node_factory.create_node_instance(identifier)
            if node:
                # 避免复制时触发重命名信号
                if hasattr(node, "block_rename_signals"):
                    node.block_rename_signals(True)
                node.NODE_NAME = n_data.get('name', node.NODE_NAME)
                if hasattr(node, "block_rename_signals"):
                    node.block_rename_signals(False)
                # set properties.
                for prop in node.model.properties.keys():
                    if prop in n_data.keys():
                        node.model.set_property(prop, n_data[prop])
                self.add_node(node, n_data.get('pos'), inherite_graph_style=adjust_graph_style)
                if n_data.get('port_deletion_allowed', None):
                    node.set_ports({
                        'input_ports': n_data['input_ports'],
                        'output_ports': n_data['output_ports']
                    })
                # set custom properties.
                for prop, val in n_data.get('custom', {}).items():
                    try:
                        node.model.set_property(prop, val)
                    except:
                        node.model.add_property(prop, val)
                    if prop == "_exec_mode":
                        node._view._toggle_exec_mode(val)
                    if prop == "_collapsed" and val:
                        node._view.toggle_collapse()
                    if isinstance(node, BaseNode):
                        if prop in node.view.widgets:
                            if GlobalVariableContext.is_variable_name(val):
                                node.view.widgets[prop].toggle_global_mode(True)
                                node.view.widgets[prop]._global_widget.set_value(val)
                            else:
                                node.view.widgets[prop].set_value(val)
                    elif node.type_ == "general.StickyNote":
                        node.set_property(prop, val)
                # 决定是否还原节点最后保存时缩放大小
                if node_resize_memory and hasattr(node.view, '_sync_size_from_model'):
                    node.view._sync_size_from_model(node_width, node_height)
                nodes[n_id] = node

        # 处理 backdrop 节点（放到最后）
        for n_id, n_data in backdrop_nodes_data.items():
            identifier = n_data['type_']
            node = self._node_factory.create_node_instance(identifier)
            if node:
                node.NODE_NAME = n_data.get('name', node.NODE_NAME)
                # set properties.
                for prop in node.model.properties.keys():
                    if prop in n_data.keys():
                        node.model.set_property(prop, n_data[prop])
                self.add_node(node, n_data.get('pos'), inherite_graph_style=adjust_graph_style)
                if n_data.get('port_deletion_allowed', None):
                    node.set_ports({
                        'input_ports': n_data['input_ports'],
                        'output_ports': n_data['output_ports']
                    })
                # set custom properties.
                for prop, val in n_data.get('custom', {}).items():
                    try:
                        node.model.set_property(prop, val)
                    except:
                        pass
                    if prop == "_collapsed" and val:
                        node._view.toggle_collapse()
                    if isinstance(node, BaseNode):
                        if prop in node.view.widgets:
                            node.view.widgets[prop].set_value(val)
                if node_resize_memory and hasattr(node.view, '_sync_size_from_model'):
                    node.view._sync_size_from_model(node_width, node_height)
                nodes[n_id] = node
        node_objs = nodes.values()
        if relative_pos:
            self._viewer.move_nodes([n.view for n in node_objs])
            [setattr(n.model, 'pos', n.view.xy_pos) for n in node_objs]
        elif pos:
            self._viewer.move_nodes([n.view for n in node_objs], pos=pos)
            [setattr(n.model, 'pos', n.view.xy_pos) for n in node_objs]
        QtCore.QTimer.singleShot(150, lambda: self.build_connections(data, nodes))

        return node_objs, nodes

    def build_connections(self, data, nodes, attempts=0):
        """
        带重试机制的连接构建器。

        Args:
            data (dict): 原始序列化数据。
            nodes (dict): 当前已创建的节点字典 {id: node_obj}。
            attempts (int): 当前重试次数。
        """
        max_attempts = 10  # 最大重试次数
        retry_interval = 100  # 每次重试间隔 (ms)

        pending_connections = []
        all_connections = data.get('connections', [])

        for connection in all_connections:
            in_nid, in_pname = connection.get('in', ('', ''))
            out_nid, out_pname = connection.get('out', ('', ''))

            in_node = nodes.get(in_nid)
            out_node = nodes.get(out_nid)

            if not in_node or not out_node:
                continue

            # 核心检查：尝试获取端口
            in_port = in_node.inputs().get(in_pname)
            out_port = out_node.outputs().get(out_pname)

            if in_port and out_port:
                # 端口已就绪，尝试连接
                if not in_port.model.connected_ports or in_port.model.multi_connection:
                    try:
                        in_port.connect_to(out_port)
                        in_node.on_input_connected(in_port, out_port)
                    except Exception as e:
                        print(f"Connection failed: {e}")
            else:
                # 端口还没出来，加入待处理列表
                pending_connections.append(connection)

        # 如果还有没连上的线，并且没超过最大尝试次数
        if pending_connections and attempts < max_attempts:
            # 构造一个临时的 data 结构用于下次重试
            retry_data = {'connections': pending_connections}

            # 延迟重试
            QtCore.QTimer.singleShot(
                retry_interval,
                lambda: self.build_connections(retry_data, nodes, attempts + 1)
            )
        else:
            # 全部连完或彻底失败后的清理工作
            if pending_connections:
                print(f"Warning: Failed to connect {len(pending_connections)} lines after {max_attempts} attempts.")

            # 恢复 UI 更新
            self._viewer.setUpdatesEnabled(True)
            self._viewer.scene().blockSignals(False)
            for n in nodes.values():
                n.view.draw_node()


class CustomSubGraph(CustomNodeGraph):
    """
    The ``SubGraph`` class is just like the ``NodeGraph`` but is the main
    controller for managing the expanded node graph for a
    :class:`NodeGraphQt.GroupNode`.

    .. inheritance-diagram:: NodeGraphQt.SubGraph
        :top-classes: PySide2.QtCore.QObject

    .. image:: ../_images/sub_graph.png
        :width: 70%

    -
    """

    def __init__(self, parent=None, node=None, node_factory=None, **kwargs):
        """
        Args:
            parent (object): object parent.
            node (GroupNode): group node related to this sub graph.
            node_factory (NodeFactory): override node factory.
            **kwargs (dict): additional kwargs.
        """
        super(CustomSubGraph, self).__init__(
            parent, node_factory=node_factory, **kwargs
        )

        # sub graph attributes.
        self._node = node
        self._parent_graph = parent
        self._subviewer_widget = None

        if self._parent_graph.is_root:
            self._initialized_graphs = [self]
            self._sub_graphs[self._node.id] = self
        else:
            # delete attributes if not top level sub graph.
            del self._widget
            del self._sub_graphs

        # clone context menu from the parent node graph.
        self._clone_context_menu_from_parent()

    def __repr__(self):
        return '<{}("{}") object at {}>'.format(
            self.__class__.__name__, self._node.name(), hex(id(self)))

    def _register_builtin_nodes(self):
        """
        Register the default builtin nodes to the :meth:`NodeGraph.node_factory`
        """
        return

    def _clone_context_menu_from_parent(self):
        """
        Clone the context menus from the parent node graph.
        """
        graph_menu = self.get_context_menu('graph')
        parent_menu = self.parent_graph.get_context_menu('graph')
        parent_viewer = self.parent_graph.viewer()
        excl_actions = [parent_viewer.qaction_for_undo(),
                        parent_viewer.qaction_for_redo()]

        def clone_menu(menu, menu_to_clone):
            """
            Args:
                menu (NodeGraphQt.NodeGraphMenu):
                menu_to_clone (NodeGraphQt.NodeGraphMenu):
            """
            sub_items = []
            for item in menu_to_clone.get_items():
                if item is None:
                    menu.add_separator()
                    continue
                name = item.name()
                if isinstance(item, NodeGraphMenu):
                    sub_menu = menu.add_menu(name)
                    sub_items.append([sub_menu, item])
                    continue

                if item in excl_actions:
                    continue

                menu.add_command(
                    name,
                    func=item.slot_function,
                    shortcut=item.qaction.shortcut()
                )

            for sub_menu, to_clone in sub_items:
                clone_menu(sub_menu, to_clone)

        # duplicate the menu items.
        clone_menu(graph_menu, parent_menu)

    def _build_port_nodes(self):
        """
        Build the corresponding input & output nodes from the parent node ports
        and remove any port nodes that are outdated..

        Returns:
             tuple(dict, dict): input nodes, output nodes.
        """
        node_layout_direction = self._viewer.get_layout_direction()

        # build the parent input port nodes.
        input_nodes = {n.name(): n for n in
                       self.get_nodes_by_type(GroupPortInputNode.type_)}
        for port in self.node.input_ports():
            if port.name() not in input_nodes:
                input_node = GroupPortInputNode(parent_port=port)
                input_node.NODE_NAME = port.name()
                input_node.model.set_property('name', port.name())
                input_node.add_output(port.name())
                input_nodes[port.name()] = input_node
                self.add_node(input_node, selected=False, push_undo=False)
                x, y = input_node.pos()
                if node_layout_direction is LayoutDirectionEnum.HORIZONTAL.value:
                    x -= 100
                elif node_layout_direction is LayoutDirectionEnum.VERTICAL.value:
                    y -= 100
                input_node.set_property('pos', [x, y], push_undo=False)

        # build the parent output port nodes.
        output_nodes = {n.name(): n for n in
                        self.get_nodes_by_type(GroupPortOutputNode.type_)}
        for port in self.node.output_ports():
            if port.name() not in output_nodes:
                output_node = GroupPortOutputNode(parent_port=port)
                output_node.NODE_NAME = port.name()
                output_node.model.set_property('name', port.name())
                output_node.add_input(port.name())
                output_nodes[port.name()] = output_node
                self.add_node(output_node, selected=False, push_undo=False)
                x, y = output_node.pos()
                if node_layout_direction is LayoutDirectionEnum.HORIZONTAL.value:
                    x += 100
                elif node_layout_direction is LayoutDirectionEnum.VERTICAL.value:
                    y += 100
                output_node.set_property('pos', [x, y], push_undo=False)

        return input_nodes, output_nodes

    def deserialize_session(self, layout_data, clear_session=True,
                            clear_undo_stack=True):
        """
        Load node graph session from a dictionary object.

        See Also:
            :meth:`NodeGraph.serialize_session`,
            :meth:`NodeGraph.load_session`,
            :meth:`NodeGraph.save_session`

        Args:
            layout_data (dict): dictionary object containing a node session.
            clear_session (bool): clear current session.
            clear_undo_stack (bool): clear the undo stack.
        """
        if clear_session:
            self.clear_session()
        input_nodes, output_nodes = self._build_port_nodes()
        nodes = {}
        for n_id, n_data in layout_data.get('nodes', {}).items():
            identifier = n_data['type_']
            name = n_data.get('name')
            if identifier == PortInputNode.type_:
                nodes[n_id] = input_nodes[name]
                nodes[n_id].set_pos(*(n_data.get('pos') or [0, 0]))
                continue
            elif identifier == PortOutputNode.type_:
                nodes[n_id] = output_nodes[name]
                nodes[n_id].set_pos(*(n_data.get('pos') or [0, 0]))
                continue

        _, internal_nodes = self._deserialize(layout_data)

        full_nodes_map = nodes | internal_nodes
        QTimer.singleShot(200, lambda: self.build_subgraph_connections(layout_data, full_nodes_map))
        self.clear_selection()
        if clear_undo_stack:
            self._undo_stack.clear()

    def build_subgraph_connections(self, data, nodes):
        # build the connections.
        for connection in data.get('connections', []):
            nid, pname = connection.get('in', ('', ''))
            in_node = nodes.get(nid)
            if not in_node:
                continue
            in_port = in_node.inputs().get(pname) if in_node else None

            nid, pname = connection.get('out', ('', ''))
            out_node = nodes.get(nid)
            if not out_node:
                continue
            out_port = out_node.outputs().get(pname) if out_node else None
            if in_port and out_port:
                self._undo_stack.push(
                    PortConnectedCmd(in_port, out_port, emit_signal=False)
                )

    def _on_navigation_changed(self, node_id, rm_node_ids):
        """
        Slot when the node navigation widget has changed.

        Args:
            node_id (str): selected group node id.
            rm_node_ids (list[str]): list of group node id to remove.
        """
        # collapse child sub graphs.
        for rm_node_id in rm_node_ids:
            child_node = self.sub_graphs[rm_node_id].node
            self.collapse_group_node(child_node)

        # show the selected node id sub graph.
        sub_graph = self.sub_graphs.get(node_id)
        if sub_graph:
            self.widget.show_viewer(sub_graph.subviewer_widget)
            sub_graph.viewer().setFocus()

    @property
    def is_root(self):
        """
        Returns if the node graph controller is the main root graph.

        Returns:
            bool: true is the node graph is root.
        """
        return False

    @property
    def sub_graphs(self):
        """
        Returns expanded group node sub graphs.

        Returns:
            dict: {<node_id>: <sub_graph>}
        """
        if self.parent_graph.is_root:
            return self._sub_graphs
        return self.parent_graph.sub_graphs

    @property
    def initialized_graphs(self):
        """
        Returns a list of the sub graphs in the order they were initialized.

        Returns:
            list[NodeGraphQt.SubGraph]: list of sub graph objects.
        """
        if self._parent_graph.is_root:
            return self._initialized_graphs
        return self._parent_graph.initialized_graphs

    @property
    def widget(self):
        """
        The sub graph widget from the top most sub graph.

        Returns:
            SubGraphWidget: node graph widget.
        """
        if self.parent_graph.is_root:
            if self._widget is None:
                self._widget = SubGraphWidget()
                self._widget.add_viewer(self.subviewer_widget,
                                        self.node.name(),
                                        self.node.id)
                # connect the navigator widget signals.
                navigator = self._widget.navigator
                navigator.navigation_changed.connect(
                    self._on_navigation_changed
                )
            return self._widget
        return self.parent_graph.widget

    @property
    def navigation_widget(self):
        """
        The navigation widget from the top most sub graph.

        Returns:
            NodeNavigationWidget: navigation widget.
        """
        if self.parent_graph.is_root:
            return self.widget.navigator
        return self.parent_graph.navigation_widget

    @property
    def subviewer_widget(self):
        """
        The widget to the sub graph.

        Returns:
            PySide2.QtWidgets.QWidget: node graph widget.
        """
        if self._subviewer_widget is None:
            self._subviewer_widget = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(self._subviewer_widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(1)
            layout.addWidget(self._viewer)
        return self._subviewer_widget

    @property
    def parent_graph(self):
        """
        The parent node graph controller.

        Returns:
            NodeGraphQt.NodeGraph or NodeGraphQt.SubGraph: parent graph.
        """
        return self._parent_graph

    @property
    def node(self):
        """
        Returns the parent node to the sub graph.

        .. image:: ../_images/group_node.png
            :width: 250px

        Returns:
            NodeGraphQt.GroupNode: group node.
        """
        return self._node

    def delete_node(self, node, push_undo=True):
        """
        Remove the node from the node sub graph.

        Note:
            :class:`.PortInputNode` & :class:`.PortOutputNode` can't be deleted
            as they are connected to a :class:`.Port` to remove these port nodes
            see :meth:`BaseNode.delete_input`, :meth:`BaseNode.delete_output`.

        Args:
            node (NodeGraphQt.BaseNode): node object.
            push_undo (bool): register the command to the undo stack. (default: True)
        """
        port_nodes = self.get_input_port_nodes() + self.get_output_port_nodes()
        if node in port_nodes and node.parent_port is not None:
            # note: port nodes can only be deleted by deleting the parent
            #       port object.
            raise NodeDeletionError(
                '{} can\'t be deleted as it is attached to a port!'.format(node)
            )
        super(CustomSubGraph, self).delete_node(node, push_undo=push_undo)

    def delete_nodes(self, nodes, push_undo=True):
        """
        Remove a list of specified nodes from the node graph.

        Args:
            nodes (list[NodeGraphQt.BaseNode]): list of node instances.
            push_undo (bool): register the command to the undo stack. (default: True)
        """
        if not nodes:
            return

        port_nodes = self.get_input_port_nodes() + self.get_output_port_nodes()
        for node in nodes:
            if node in port_nodes and node.parent_port is not None:
                # note: port nodes can only be deleted by deleting the parent
                #       port object.
                raise NodeDeletionError(
                    '{} can\'t be deleted as it is attached to a port!'
                    .format(node)
                )

        super(CustomSubGraph, self).delete_nodes(nodes, push_undo=push_undo)

    def collapse_graph(self, clear_session=True):
        """
        Collapse the current sub graph and hide its widget.

        Args:
            clear_session (bool): clear the current session.
        """
        # update the group node.
        serialized_session = self.serialize_session()
        self.node.set_sub_graph_session(serialized_session)

        # close the visible widgets.
        if self._undo_view:
            self._undo_view.close()

        if self._subviewer_widget:
            self.widget.hide_viewer(self._subviewer_widget)

        if clear_session:
            self.clear_session()

    def expand_group_node(self, node):
        """
        Expands a group node session in current sub view.

        Args:
            node (NodeGraphQt.GroupNode): group node.

        Returns:
            SubGraph: sub node graph used to manage the group node session.
        """
        assert isinstance(node, GroupNode), 'node must be a GroupNode instance.'
        if self._subviewer_widget is None:
            raise RuntimeError('SubGraph.widget not initialized!')

        self.viewer().clear_key_state()
        self.viewer().clearFocus()

        if node.id in self.sub_graphs:
            sub_graph_viewer = self.sub_graphs[node.id].viewer()
            sub_graph_viewer.setFocus()
            return self.sub_graphs[node.id]

        # collapse expanded child sub graphs.
        group_ids = [n.id for n in self.all_nodes() if isinstance(n, GroupNode)]
        for grp_node_id, grp_sub_graph in self.sub_graphs.items():
            # collapse current group node.
            if grp_node_id in group_ids:
                grp_node = self.get_node_by_id(grp_node_id)
                self.collapse_group_node(grp_node)

            # close the widgets
            grp_sub_graph.collapse_graph(clear_session=False)

        # build new sub graph.
        node_factory = copy.deepcopy(self.node_factory)
        sub_graph = CustomSubGraph(self,
                             node=node,
                             node_factory=node_factory,
                             layout_direction=self.layout_direction())

        # populate the sub graph.
        serialized_session = node.get_sub_graph_session()
        sub_graph.deserialize_session(serialized_session)

        # open new sub graph view.
        self.widget.add_viewer(sub_graph.subviewer_widget,
                               node.name(),
                               node.id)

        # store the references.
        self.sub_graphs[node.id] = sub_graph
        self.initialized_graphs.append(sub_graph)

        return sub_graph

    def collapse_group_node(self, node):
        """
        Collapse a group node session and it's expanded child sub graphs.

        Args:
            node (NodeGraphQt.GroupNode): group node.
        """
        # update the references.
        sub_graph = self.sub_graphs.pop(node.id, None)
        if not sub_graph:
            return

        init_idx = self.initialized_graphs.index(sub_graph) + 1
        for sgraph in reversed(self.initialized_graphs[init_idx:]):
            self.initialized_graphs.remove(sgraph)

        # collapse child sub graphs here.
        child_ids = [
            n.id for n in sub_graph.all_nodes() if isinstance(n, GroupNode)
        ]
        for child_id in child_ids:
            if self.sub_graphs.get(child_id):
                child_graph = self.sub_graphs.pop(child_id)
                child_graph.collapse_graph(clear_session=True)
                # remove child viewer widget.
                self.widget.remove_viewer(child_graph.subviewer_widget)

        sub_graph.collapse_graph(clear_session=True)
        self.widget.remove_viewer(sub_graph.subviewer_widget)

    def get_input_port_nodes(self):
        """
        Return all the port nodes related to the group node input ports.

        .. image:: ../_images/port_in_node.png
            :width: 150px

        -

        See Also:
            :meth:`NodeGraph.get_nodes_by_type`,
            :meth:`SubGraph.get_output_port_nodes`

        Returns:
            list[NodeGraphQt.PortInputNode]: input nodes.
        """
        return self.get_nodes_by_type(PortInputNode.type_)

    def get_output_port_nodes(self):
        """
        Return all the port nodes related to the group node output ports.

        .. image:: ../_images/port_out_node.png
            :width: 150px

        -

        See Also:
            :meth:`NodeGraph.get_nodes_by_type`,
            :meth:`SubGraph.get_input_port_nodes`

        Returns:
            list[NodeGraphQt.PortOutputNode]: output nodes.
        """
        return self.get_nodes_by_type(PortOutputNode.type_)

    def get_node_by_port(self, port):
        """
        Returns the node related to the parent group node port object.

        Args:
            port (NodeGraphQt.Port): parent node port object.

        Returns:
            PortInputNode or PortOutputNode: port node object.
        """
        func_type = {
            PortTypeEnum.IN.value: self.get_input_port_nodes,
            PortTypeEnum.OUT.value: self.get_output_port_nodes
        }
        for n in func_type.get(port.type_(), []):
            if port == n.parent_port:
                return n
