# -*- coding: utf-8 -*-
import copy
import json
import traceback

from NodeGraphQt import NodeGraph, BaseNode, NodeGraphMenu, GroupNode, SubGraph
from NodeGraphQt.constants import (
    Z_VAL_PIPE, )
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem
from NodeGraphQt.qgraphics.pipe import PipeItem
from NodeGraphQt.widgets.scene import NodeScene
from NodeGraphQt.widgets.viewer import NodeViewer
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QTextEdit, QLineEdit
from Qt import QtGui, QtCore, QtWidgets
from loguru import logger
from qtpy import QtGui, QtCore, QtWidgets

from app.components.base import GlobalVariableContext
from app.nodes.status_node import NodeStatus
from app.utils.config import Settings
from app.utils.utils import serialize_for_json, deserialize_from_json
from app.widgets.basic_widget.combo_widget import CustomComboBox
from app.widgets.custom_nodegraphqt.custom_node_menu import CustomNodesMenu
from app.widgets.custom_nodegraphqt.custom_pipe_item import CustomPipeItem
from app.widgets.custom_nodegraphqt.node_action_buttons import NodeActionButton
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


class SelectionLabelItem(QtWidgets.QGraphicsWidget):
    """左上角显示选中数量"""

    def __init__(self, parent=None):
        super(SelectionLabelItem, self).__init__(parent)
        self.setZValue(Z_VAL_PIPE + 201)
        self.count = 0
        self.bg_color = QtGui.QColor(30, 30, 35, 200)
        self.border_color = QtGui.QColor(255, 180, 0, 255)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        self.label = QtWidgets.QGraphicsTextItem(self)
        self.label.setDefaultTextColor(QtGui.QColor(255, 255, 255, 220))
        font = QtGui.QFont("Segoe UI", 9, QtGui.QFont.Bold)
        self.label.setFont(font)

    def update_count(self, count):
        self.count = count
        self.label.setPlainText(f" {count} NODES SELECTED ")
        self.prepareGeometryChange()

    def boundingRect(self):
        return self.label.boundingRect().adjusted(0, 0, 10, 0)

    def paint(self, painter, option, widget):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.boundingRect()

        # 1. 绘制背景矩形 (传入 QRectF 对象以支持 float)
        painter.setBrush(self.bg_color)
        painter.setPen(QtGui.QPen(self.border_color, 1.0))
        painter.drawRoundedRect(rect, 5, 5)

        # 2. 绘制左侧的小装饰条 (修复点：使用 QRectF 包裹参数)
        painter.setBrush(self.border_color)
        painter.setPen(QtCore.Qt.NoPen)
        # 错误原因修复：drawRect 需要 (QRectF) 或 (int, int, int, int)
        side_bar = QtCore.QRectF(rect.left(), rect.top() + 4, 3, rect.height() - 8)
        painter.drawRect(side_bar)

        painter.restore()


class SelectionActionToolbar(QtWidgets.QGraphicsWidget):
    """右上角动作按钮组"""

    def __init__(self, viewer, parent=None):
        super(SelectionActionToolbar, self).__init__(parent)
        self.viewer = viewer
        self.setZValue(Z_VAL_PIPE + 201)
        # 确保工具栏本身不响应选择，这样它不会干扰节点选择逻辑
        self.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsFocusable, False)
        # --- 1. 创建按钮并绑定点击函数 ---
        # 执行：执行选中节点
        self.btn_run = NodeActionButton(self, "run", "执行", "#27ae60", "#2ecc71", False)
        self.btn_run.clicked_func = self.on_run
        # 注释：创建背景框
        self.btn_comment = NodeActionButton(self, "comment", "添加注释背景", "#34495e", "#2c3e50", True)
        self.btn_comment.clicked_func = self._on_comment

        # 居中：聚焦选中区域
        self.btn_center = NodeActionButton(self, "zoom", "聚焦选中内容", "#3498db", "#2980b9", True)
        self.btn_center.clicked_func = self._on_center

        # 克隆：复制并粘贴
        self.btn_clone = NodeActionButton(self, "clone", "克隆选中节点", "#27ae60", "#2ecc71", True)
        self.btn_clone.clicked_func = self._on_clone

        # 模板：保存到模板库
        self.btn_template = NodeActionButton(self, "template", "加入模板库", "#9b59b6", "#8e44ad", True)
        self.btn_template.clicked_func = self._on_template

        self._close_btn = NodeActionButton(self, "close", "删除", "#c0392b", "#e74c3c", False)
        self._close_btn.clicked_func = self._on_close
        # --- 2. 布局逻辑 (保持不变) ---
        self.buttons = [self.btn_run, self.btn_comment, self.btn_center, self.btn_clone, self.btn_template, self._close_btn]
        spacing = 6
        btn_w = 28
        for i, btn in enumerate(self.buttons):
            btn.setParentItem(self)
            btn.setPos(i * (btn_w + spacing), 0)
        self._total_width = (btn_w * len(self.buttons)) + (spacing * (len(self.buttons) - 1))

    def boundingRect(self):
        return QtCore.QRectF(0, 0, self._total_width, 28)

    # --- 3. 功能具体实现 ---
    def on_run(self):
        """功能：执行选中的节点"""
        self.viewer.home_window.canvas_runner.run_full()

    def _on_comment(self):
        """功能：为选中的节点创建一个 Backdrop (背景框)"""
        # 如果你的 node_operations 已经有这个方法，直接调用：
        if hasattr(self.viewer.home_window, 'node_operations'):
            # 这是一个常见的 NodeGraphQt 操作：创建一个包围选中节点的背景框
            self.viewer.home_window.create_backdrop_node("general.StickyNote", init_io=False)

    def _on_center(self):
        """功能：将视图中心对准并缩放到选中节点"""
        self.viewer.zoom_to_nodes(self.viewer.selected_nodes())

    def _on_clone(self):
        """功能：快速克隆选中的节点"""
        # 调用主窗口现有的复制粘贴逻辑
        if hasattr(self.viewer.home_window, 'node_operations'):
            ops = self.viewer.home_window.node_operations
            ops._copy_selected_nodes()
            ops._paste_nodes()
            # 粘贴后更新一下多选框
            self.viewer._selection_overlay.update()

    def _on_template(self):
        """功能：将当前选择保存为代码段/模板库"""
        self.viewer.home_window.add_template()

    def _on_close(self):
        """功能：删除选中的节点"""
        # 获取选中的节点
        selected_nodes = self.viewer.selected_nodes()
        if selected_nodes:
            # 删除节点
            self.viewer.home_window.node_operations.delete_selected_nodes(self.viewer.graph)
            # 更新多选框
            self.viewer._selection_overlay.update()


class SelectionOverlayManager:
    def __init__(self, viewer):
        self.viewer = viewer
        self.scene = viewer.scene()
        self._visible = False
        # 1. 虚线框
        self.rect_item = QtWidgets.QGraphicsPathItem()
        self.rect_item.setZValue(Z_VAL_PIPE + 190)
        pen = QtGui.QPen(QtGui.QColor(255, 180, 0, 150), 1.5, QtCore.Qt.DashLine)
        pen.setCosmetic(True)
        self.rect_item.setPen(pen)
        self.scene.addItem(self.rect_item)
        self.rect_item.hide()
        # 3. 右上角动作栏
        self.toolbar = SelectionActionToolbar(viewer)
        self.scene.addItem(self.toolbar)
        self.toolbar.hide()

    def update(self):
        selected_nodes = [
            i for i in self.scene.selectedItems()
            if isinstance(i, AbstractNodeItem) and i.isVisible()
        ]

        if len(selected_nodes) < 2:
            self.hide()
            return
        self._visible = True
        # 1. 计算场景中的并集矩形
        rect = selected_nodes[0].sceneBoundingRect()
        for node in selected_nodes[1:]:
            rect = rect.united(node.sceneBoundingRect())

        # 虚线框跟随场景缩放，所以 padding 使用场景单位
        padding = 20
        rect.adjust(-padding, -padding, padding, padding)

        # 2. 更新虚线框路径
        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        self.rect_item.setPath(path)
        self.rect_item.show()

        # 3. 计算当前的视图缩放比例 (Scale)
        # transform().m11() 返回的是当前的缩放倍数
        view_scale = self.viewer.transform().m11()

        # 在场景中的间距 = 屏幕像素 / 缩放比例
        scene_gap = 10 / view_scale

        # --- 更新右上角工具栏位置 ---
        toolbar_w_pixel = self.toolbar.boundingRect().width()
        toolbar_h_pixel = self.toolbar.boundingRect().height()

        # x轴位置：矩形右侧 - (自身像素宽度 / view_scale)
        toolbar_x = rect.right() - (toolbar_w_pixel / view_scale)
        # y轴位置：矩形上方
        toolbar_y = rect.top() - scene_gap - (toolbar_h_pixel / view_scale)

        self.toolbar.setPos(toolbar_x, toolbar_y)
        self.toolbar.show()

    def hide(self):
        self.rect_item.hide()
        self.toolbar.hide()
        self._visible = False


class CustomNodeViewer(NodeViewer):

    def __init__(self, parent=None, undo_stack=None):
        super(CustomNodeViewer, self).__init__(parent)
        self.home_window = parent
        self._panning = False
        self.graph = None
        self._navigation_mode = False
        self._last_drag_target = None  # 记录当前正在高亮的代理控件
        self._custom_menu = None  # 用于存放 CustomGraphMenu 的引用
        self._temp_connection_source = None  # 用于存放拉线的起始端口
        self.setScene(CustomNodeScene(self))
        # --- 性能优化：初始开启抗锯齿 ---
        self.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
        self.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)

        # --- 性能优化：微调 View 参数 ---
        # 优化拖动时的重绘策略
        self.setOptimizationFlag(QtWidgets.QGraphicsView.DontAdjustForAntialiasing)

        # --- 新增：对齐线对象 (初始化一次，复用) ---
        self._snap_lines_item = QtWidgets.QGraphicsPathItem()
        self._snap_lines_item.setZValue(Z_VAL_PIPE + 100)  # 最顶层
        snap_pen = QtGui.QPen(SNAP_COLOR, 1.0, QtCore.Qt.DashLine)
        snap_pen.setCosmetic(True)  # 缩放时不改变线宽
        self._snap_lines_item.setPen(snap_pen)
        self.scene().addItem(self._snap_lines_item)
        self._snap_lines_item.hide()
        # -------------------------------------
        self._selection_overlay = SelectionOverlayManager(self)

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
        if hasattr(self, '_selection_overlay') and self._selection_overlay._visible:
            self._selection_overlay.update()

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
        item = self.itemAt(event.pos())
        if isinstance(item, NodeActionButton):
            # 如果点的是按钮，直接让基类处理分发，不要执行后续的隐藏和拉框逻辑
            super(NodeViewer, self).mousePressEvent(event)
            return
        if event.button() == QtCore.Qt.LeftButton:
            # 开始新操作前先隐藏
            self._selection_overlay.hide()
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
        # 1. 注入导航模式下的平移逻辑
        if self._navigation_mode and self.LMB_state and not self.ALT_state:
            previous_pos = self.mapToScene(self._previous_pos)
            current_pos = self.mapToScene(event.pos())
            delta = previous_pos - current_pos
            self._set_viewer_pan(delta.x(), delta.y())

        # 2. 执行父类逻辑 (NodeGraphQt 在这里处理节点的拖动计算)
        super(CustomNodeViewer, self).mouseMoveEvent(event)

        # 3. 判定是否正在拖拽节点
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

            # 排除正在缩放节点的情况
            if any(getattr(n, '_is_resizing', False) for n in selected_nodes):
                self._snap_lines_item.hide()
                self._selection_overlay.hide()
            else:
                # 处理对齐线
                self._handle_snapping(selected_nodes)
                # --- 新增：更新多选虚线框和工具栏 ---
                self._selection_overlay.update()
        else:
            if self._snap_lines_item.isVisible():
                self._snap_lines_item.hide()

            # 如果是在拉框选择，实时更新虚线框 (体验更好)
            if self._rubber_band.isActive:
                self._selection_overlay.update()

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
                self._temp_connection_source = None
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
                    if prev_ids != node_ids and event.button() != QtCore.Qt.MiddleButton and not self._navigation_mode:
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
            if prev_ids != node_ids and event.button() != QtCore.Qt.MiddleButton and not self._navigation_mode:
                self.node_selection_changed.emit(node_ids, prev_ids)

        self._prev_selection_nodes = [n for n in self.scene().selectedItems() if isinstance(n, AbstractNodeItem)]

        super(CustomNodeViewer, self).mouseReleaseEvent(event)
        # self._selection_overlay.update()

    def keyPressEvent(self, event):
        focused_widget = QApplication.focusWidget()
        if focused_widget:
            if hasattr(focused_widget, 'code_editor'):
                QApplication.sendEvent(focused_widget.code_editor, event)
                return
            elif isinstance(focused_widget, (QTextEdit, QLineEdit)):
                QApplication.sendEvent(focused_widget, event)
                return

        self.ALT_state = event.modifiers() == QtCore.Qt.AltModifier
        self.CTRL_state = event.modifiers() == QtCore.Qt.ControlModifier
        self.SHIFT_state = event.modifiers() == QtCore.Qt.ShiftModifier
        if event.modifiers() == (QtCore.Qt.AltModifier | QtCore.Qt.ShiftModifier):
            self.ALT_state = True
            self.SHIFT_state = True
        if self._LIVE_PIPE.isVisible():
            super(CustomNodeViewer, self).keyPressEvent(event)
            return

        # 国际化悬浮提示文字
        overlay_text = None
        self._cursor_text.setVisible(False)
        if not self.ALT_state:
            if self.SHIFT_state:
                overlay_text = self.tr("\n    SHIFT:\n    扩展节点选择")
            elif self.CTRL_state:
                overlay_text = self.tr("\n    CTRL:\n    取消节点选择")
        elif self.ALT_state and self.SHIFT_state:
            if self.pipe_slicing:
                overlay_text = self.tr("\n    ALT + SHIFT:\n    连线删除模式")

        if overlay_text:
            self._cursor_text.setPlainText(overlay_text)
            self._cursor_text.setFont(QtGui.QFont('Arial', 10))
            self._cursor_text.setDefaultTextColor(Qt.white)
            self._cursor_text.setPos(self.mapToScene(self._previous_pos))
            self._cursor_text.setVisible(True)

        if event.modifiers() == QtCore.Qt.ControlModifier:
            if event.key() == QtCore.Qt.Key_C:
                self.home_window.node_operations._copy_selected_nodes()
            elif event.key() == QtCore.Qt.Key_V:
                self.home_window.node_operations._paste_nodes()

        super(CustomNodeViewer, self).keyPressEvent(event)

    def dragEnterEvent(self, event):
        event.accept()

    def dragMoveEvent(self, event):
        mime_data = event.mimeData()

        # 只有在拖拽全局变量时才触发高亮逻辑
        if mime_data.hasFormat("application/x-global-variable"):
            # 1. 查找鼠标下的项
            pos = event.pos()
            items = self.items(pos)

            target_widget = None
            for item in items:
                if isinstance(item, CustomNodeBaseWidget):
                    target_widget = item
                    break

            # 2. 状态切换逻辑
            if target_widget != self._last_drag_target:
                # 移出旧控件，重置样式
                if self._last_drag_target:
                    group_box = self._last_drag_target.widget()
                    if hasattr(group_box, 'reset'):
                        group_box.reset()

                # 进入新控件，高亮样式
                if target_widget:
                    group_box = target_widget.widget()
                    if hasattr(group_box, 'highlight'):
                        group_box.highlight()

                self._last_drag_target = target_widget

            event.accept()

        else:
            # 处理普通的节点创建拖拽 以及 我们的子图模板拖拽
            # 在列表里增加 'application/x-subgraph-template'
            is_acceptable = any([
                mime_data.hasFormat(i) for i in
                ['nodegraphqt/nodes', 'text/plain', 'application/x-subgraph-template']
            ])

            if is_acceptable:
                event.accept()
            else:
                event.ignore()

    def dragLeaveEvent(self, event):
        """当拖拽彻底离开画布区域时，重置所有高亮"""
        if self._last_drag_target:
            group_box = self._last_drag_target.widget()
            if hasattr(group_box, 'reset'):
                group_box.reset()
            self._last_drag_target = None
        event.accept()

    def dropEvent(self, event):
        try:
            mime_data = event.mimeData()
            pos = event.pos()
            scene_pos = self.mapToScene(pos)
            # --- 情况 A：如果是画布模板，且鼠标下有属性控件 -> 创建节点组 ---
            if mime_data.hasFormat("application/x-subgraph-template"):
                tid = bytes(mime_data.data("application/x-subgraph-template")).decode('utf-8')
                # 找到 template_panel 实例（假设它在 home_window 下）
                template_panel = getattr(self.home_window, 'template_manager', None)
                if template_panel:
                    template_panel.apply_template(tid, pos=scene_pos)
                    event.accept()
                    return

            if self._last_drag_target:
                group_box = self._last_drag_target.widget()
                if hasattr(group_box, 'reset'):
                    group_box.reset()
                self._last_drag_target = None

            full_path = mime_data.text()
            pos = event.pos()

            # 查找鼠标点击位置下的所有图形项
            items = self.items(pos)
            target_widget = None
            for item in items:
                if isinstance(item, CustomNodeBaseWidget):
                    target_widget = item
                    break

            # --- 情况 B：如果是变量，且鼠标下有属性控件 -> 执行绑定 ---
            if mime_data.hasFormat("application/x-global-variable") and target_widget:
                data_bytes = bytes(mime_data.data("application/x-global-variable"))
                drag_data = json.loads(data_bytes.decode('utf-8'))
                # 调用我们之前写好的完美版 set_value
                if not target_widget._is_using_global:
                    target_widget.toggle_global_mode()
                target_widget._global_widget.set_value(f"{drag_data['var_type']}.{drag_data['var_name']}")
                event.accept()
                return

            node_type = self.home_window.node_type_map.get(full_path)
            if node_type:
                node = self.home_window.graph.create_node(node_type)
                self.home_window.nav_view.record_usage(full_path)
                node.set_pos(scene_pos.x(), scene_pos.y())
                QtCore.QTimer.singleShot(0, lambda: self.home_window.property_panel.update_properties(node))
                self.home_window.node_status[node.id] = NodeStatus.NODE_STATUS_UNRUN
                if hasattr(node, 'status'):
                    node.status = NodeStatus.NODE_STATUS_UNRUN

                # 变量节点自动设置部分属性，便于与普通节点区分
                if mime_data.hasFormat("application/x-global-variable"):
                    data_bytes = bytes(mime_data.data("application/x-global-variable"))
                    drag_data = json.loads(data_bytes.decode('utf-8'))
                    node.set_icon(":/icons/变量.svg")
                    node.set_property("var_name", f"{drag_data['var_type']}.{drag_data['var_name']}")
                    node.set_name("\n".join(drag_data['var_name'].split("__")))
                    node.view.toggle_collapse()
                    self.home_window.canvas_runner.run_node(node)
                event.accept()
            else:
                event.ignore()
        except Exception as e:
            logger.error(traceback.format_exc())

    def resizeEvent(self, event):
        self.home_window.ui_manager.update_position()
        return super().resizeEvent(event)


class CustomNodeGraph(NodeGraph):

    def __init__(self, parent, **kwargs):
        super(CustomNodeGraph, self).__init__(parent, **kwargs)
        self._register_context_menu()
        self._viewer.graph = self

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

        # if node.id in self._sub_graphs:
        #     sub_graph = self._sub_graphs[node.id]
        #     tab_index = self._widget.indexOf(sub_graph.widget)
        #     self._widget.setCurrentIndex(tab_index)
        #     return sub_graph

        # build new sub graph.
        node_factory = copy.deepcopy(self.node_factory)
        layout_direction = self.layout_direction()
        kwargs = {
            'layout_direction': self.layout_direction(),
            'pipe_style': self.pipe_style(),
        }
        sub_graph = SubGraph(self,
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