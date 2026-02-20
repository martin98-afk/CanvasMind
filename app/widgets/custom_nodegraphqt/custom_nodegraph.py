# -*- coding: utf-8 -*-
import copy
import orjson
import traceback

from NodeGraphQt import NodeGraph, BaseNode, NodeGraphMenu, GroupNode, SubGraph
from NodeGraphQt.constants import (
    Z_VAL_PIPE, ViewerEnum, PortTypeEnum, )
from NodeGraphQt.qgraphics.port import PortItem
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem
from NodeGraphQt.qgraphics.pipe import PipeItem
from NodeGraphQt.qgraphics.slicer import SlicerPipeItem
from NodeGraphQt.widgets.scene import NodeScene
from NodeGraphQt.widgets.viewer import NodeViewer
from PyQt5 import sip
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
from app.widgets.custom_nodegraphqt.custom_node_menu import CustomNodesMenu, BaseMenu
from app.widgets.custom_nodegraphqt.custom_pipe_item import CustomPipeItem, CustomLivePipeItem
from app.widgets.custom_nodegraphqt.node_action_buttons import NodeActionButton, BaseCanvasToolbar
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


class SelectionOverlayItem(QtWidgets.QGraphicsItem):
    """
    高性能悬浮遮罩项
    将虚线框和工具栏整合，减少 Scene 管理开销
    """

    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.setZValue(Z_VAL_PIPE + 190)
        self.setCacheMode(QtWidgets.QGraphicsItem.DeviceCoordinateCache)

        # 内部状态缓存
        self._current_rect = QtCore.QRectF()
        self._padding = 20
        self._visible = False

        # 笔刷缓存
        self._pen = QtGui.QPen(QtGui.QColor(255, 180, 0, 150), 1.5, QtCore.Qt.DashLine)
        self._pen.setCosmetic(True)  # 极致性能的关键：缩放时不重绘线宽

    def boundingRect(self):
        return self._current_rect.adjusted(-2, -2, 2, 2)

    def paint(self, painter, option, widget):
        if not self._visible or self._current_rect.isEmpty():
            return
        painter.setPen(self._pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRoundedRect(self._current_rect, 10, 10)

    def update_geometry(self, selected_nodes):
        """仅在节点增减或停止移动时调用：重算并集矩形"""
        if not selected_nodes:
            self._visible = False
            self.hide()
            return

        self.prepareGeometryChange()

        # 优化：直接获取第一个节点的并集，减少循环内开销
        rect = selected_nodes[0].sceneBoundingRect()
        for i in range(1, len(selected_nodes)):
            rect = rect.united(selected_nodes[i].sceneBoundingRect())

        rect.adjust(-self._padding, -self._padding, self._padding, self._padding)
        self._current_rect = rect
        self._visible = True
        self.show()
        self.update()

    def quick_move(self, delta):
        """拖拽节点时调用：仅平移，不重算矩形并集"""
        self.prepareGeometryChange()
        self._current_rect.translate(delta)
        self.update()


class SelectionActionToolbar(BaseCanvasToolbar):
    def __init__(self, viewer, parent=None):
        super(SelectionActionToolbar, self).__init__(viewer, parent)

        # --- 按钮创建 (按你原来的顺序) ---
        self.btn_run = self.add_button("run", "执行", "#27ae60", "#2ecc71", True)
        self.btn_run.clicked_func = self.on_run
        self.add_separator()
        self.btn_center = self.add_button("zoom", "聚焦选中内容", "#3498db", "#2980b9", False)
        self.btn_center.clicked_func = self._on_center

        self.btn_layout = self.add_button("layout", "自动排布节点", "#3498db", "#2980b9", False)
        self.btn_layout.clicked_func = self._on_auto_layout
        self.add_separator()
        self.btn_clone = self.add_button("clone", "克隆选中节点", "#27ae60", "#2ecc71", False)
        self.btn_clone.clicked_func = self._on_clone

        self.btn_template = self.add_button("template", "加入模板库", "#9b59b6", "#8e44ad", False)
        self.btn_template.clicked_func = self._on_template
        self.add_separator()
        self.btn_more = self.add_button("more", "更多操作", "#7f8c8d", "#95a5a6", False)
        self.btn_more.clicked_func = self._on_more_menu

        self._close_btn = self.add_button("close", "删除", "#c0392b", "#e74c3c", True)
        self._close_btn.clicked_func = self._on_close

    # --- 逻辑功能 (一个字不少，原样保留) ---
    def on_run(self):
        self.viewer.home_window.canvas_runner.run_workflow()

    def _on_auto_layout(self):
        from .node_layout_handler import NodeLayoutHandler
        NodeLayoutHandler.auto_layout(self.viewer.graph)
        self.viewer._selection_overlay.refresh(full_recalc=False)

    def _on_comment(self):
        if hasattr(self.viewer.home_window, 'node_operations'):
            self.viewer.home_window.create_backdrop_node("general.StickyNote", init_io=False)

    def _on_center(self):
        self.viewer.zoom_to_nodes(self.viewer.selected_nodes())
        self.viewer._selection_overlay.refresh(full_recalc=False)

    def _on_clone(self):
        if hasattr(self.viewer.home_window, 'node_operations'):
            ops = self.viewer.home_window.node_operations
            ops._copy_selected_nodes()
            ops._paste_nodes()
            self.viewer._selection_overlay.refresh(full_recalc=False)

    def _on_template(self):
        self.viewer.home_window.add_template()

    def _on_more_menu(self):
        # --- 完全保留你喜欢的 QSS 样式 ---
        menu = QtWidgets.QMenu()
        menu.setWindowFlags(QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        menu.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(45, 45, 45, 230);
                color: #E0E0E0;
                border: 1px solid #555555;
                border-radius: 8px;
                padding: 6px 0px;
            }
            QMenu::item {
                padding: 8px 28px 8px 15px;
                background-color: transparent;
                margin: 2px 6px;
                border-radius: 4px;
                font-size: 13px;
            }
            QMenu::item:selected {
                background-color: #3d77ff;
                color: white;
            }
            QMenu::separator {
                height: 1px;
                background-color: #555555;
                margin: 6px 12px;
            }
        """)

        # 动作集成 (全部保留)
        menu.addAction("📝 添加注释背景").triggered.connect(self._on_comment)
        menu.addSeparator()

        ops = self.viewer.home_window.node_operations
        menu.addAction("🔄 创建循环结构").triggered.connect(
            lambda: ops.create_backdrop_node("control_flow.ControlFlowLoopNode"))
        menu.addAction("🔁 创建迭代结构").triggered.connect(
            lambda: ops.create_backdrop_node("control_flow.ControlFlowIterateNode"))

        menu.addSeparator()
        menu.addAction("📦 批量转为子进程").triggered.connect(self._on_batch_subprocess)
        menu.addAction("⚡ 批量内存驻留").triggered.connect(self._on_batch_ipython)

        menu.addSeparator()
        menu.addAction("➕ 批量展开节点").triggered.connect(self._on_batch_unfold)
        menu.addAction("➖ 批量折叠节点").triggered.connect(self._on_batch_fold)

        from .node_layout_handler import NodeLayoutHandler
        menu.addAction("📏 吸附至网格").triggered.connect(lambda: NodeLayoutHandler.snap_to_grid(self.viewer.graph))

        # 对齐子菜单
        align_menu = menu.addMenu("📐 对齐方式")
        for mode in ['left', 'right', 'top', 'bottom', 'center_h']:
            align_menu.addAction(mode).triggered.connect(
                lambda checked, m=mode: NodeLayoutHandler.align_nodes(self.viewer.graph, m))

        dist_menu = menu.addMenu("↔️ 等间距排列")
        dist_menu.addAction("水平等距").triggered.connect(
            lambda: NodeLayoutHandler.distribute_nodes(self.viewer.graph, 'horizontal'))
        dist_menu.addAction("垂直等距").triggered.connect(
            lambda: NodeLayoutHandler.distribute_nodes(self.viewer.graph, 'vertical'))

        button_scene_pos = self.btn_more.scenePos()
        view_pos = self.viewer.mapFromScene(button_scene_pos)
        global_pos = self.viewer.viewport().mapToGlobal(view_pos)
        menu.exec_(global_pos + QtCore.QPoint(0, 30))

    def _on_batch_subprocess(self):
        for node in self.viewer.selected_nodes():
            if hasattr(node, '_toggle_exec_mode'): node._toggle_exec_mode("subprocess")

    def _on_batch_ipython(self):
        for node in self.viewer.selected_nodes():
            if hasattr(node, '_toggle_exec_mode'): node._toggle_exec_mode("ipython")

    def _on_batch_fold(self):
        for node in self.viewer.selected_nodes():
            if hasattr(node, 'toggle_collapse'): node.toggle_collapse(True)

    def _on_batch_unfold(self):
        for node in self.viewer.selected_nodes():
            if hasattr(node, 'toggle_collapse'): node.toggle_collapse(False)

    def _on_close(self):
        self.viewer.home_window.node_operations.delete_selected_nodes(self.viewer.graph)
        self.viewer._selection_overlay.refresh(full_recalc=False)

    def update_position(self, scene_rect):
        """核心：计算抗缩放后的偏移位置"""
        if not self.isVisible(): return
        view_scale = self.viewer.transform().m11()
        # 将物理像素转换为场景坐标进行定位
        target_x = scene_rect.center().x() - (self._total_width / 2 / view_scale)
        target_y = scene_rect.top() - (40 / view_scale) - (10 / view_scale)
        self.setPos(target_x, target_y)


class SelectionOverlayManager:
    def __init__(self, viewer):
        self.viewer = viewer
        self.scene = viewer.scene()
        self._visible = False  # <<< 确保这个属性存在

        # 1. 虚线框项 (使用之前建议的高性能 Item)
        self.rect_item = SelectionOverlayItem(viewer)
        self.scene.addItem(self.rect_item)

        # 2. 工具栏
        self.toolbar = SelectionActionToolbar(viewer)
        self.scene.addItem(self.toolbar)

        self.hide()  # 初始状态隐藏

    def refresh(self, full_recalc=True):
        selected_nodes = [
            i for i in self.scene.selectedItems()
            if isinstance(i, AbstractNodeItem) and i.isVisible()
        ]

        if len(selected_nodes) < 2:
            self.hide()
            return

        # 更新状态
        self._visible = True

        if full_recalc:
            self.rect_item.update_geometry(selected_nodes)

        self.toolbar.show()
        # 传入当前的矩形区域进行位置锚定
        self.toolbar.update_position(self.rect_item._current_rect)

    def on_drag(self, delta):
        """节点拖动时的极速刷新"""
        if self._visible:
            self.rect_item.quick_move(delta)
            self.toolbar.update_position(self.rect_item._current_rect)

    def hide(self):
        self._visible = False
        self.rect_item.hide()
        self.toolbar.hide()

    def is_visible(self):
        """安全获取可见性状态"""
        return self._visible


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
        # context menus.
        self._ctx_graph_menu = BaseMenu('NodeGraph', self)
        self._ctx_node_menu = BaseMenu('Nodes', self)
        self._LIVE_PIPE = CustomLivePipeItem()
        self._LIVE_PIPE.setVisible(False)
        self.scene().addItem(self._LIVE_PIPE)
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
        self._SLICER_PIPE = SlicerPipeItem()
        self._SLICER_PIPE.setVisible(False)
        self.scene().addItem(self._SLICER_PIPE)
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
        if self._selection_overlay.is_visible():
            self._selection_overlay.refresh(full_recalc=False)

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
                self._selection_overlay.refresh(full_recalc=True)
            elif self.CTRL_state:
                if items and backdrop == items[0]:
                    backdrop.selected = False
                else:
                    for node in nodes:
                        node.selected = False
                self._selection_overlay.refresh(full_recalc=True)
            else:
                select_changed = False
                if backdrop:
                    selection.add(backdrop)
                    for n in backdrop.get_nodes():
                        selection.add(n)
                        select_changed = True
                for node in nodes:
                    if node.selected:
                        selection.add(node)
                        select_changed = True
                if select_changed:
                    self._selection_overlay.refresh(full_recalc=False)

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
                self._selection_overlay.refresh()
        else:
            if self._snap_lines_item.isVisible():
                self._snap_lines_item.hide()

            # 如果是在拉框选择，实时更新虚线框 (体验更好)
            if self._rubber_band.isActive:
                self._selection_overlay.refresh(full_recalc=True)

    # ---------------------------------------------

    def mouseReleaseEvent(self, event):
        # -------------------------------------
        # 1. 记录拉线状态
        live_pipe_active = self._LIVE_PIPE.isVisible()
        # 注意：使用 self._start_port，这是 NodeGraphQt 内部记录起始端口的变量
        start_port = self._LIVE_PIPE._start_port if live_pipe_active else None

        # 2. 检测释放位置是否是空白处
        scene_pos = self.mapToScene(event.pos())
        items = self.scene().items(scene_pos)

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

                self.scene().update(map_rect)

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
            if prev_ids != node_ids:
                self.node_selection_changed.emit(node_ids, prev_ids)

        self._prev_selection_nodes = [n for n in self.scene().selectedItems() if isinstance(n, AbstractNodeItem)]

        super(CustomNodeViewer, self).mouseReleaseEvent(event)

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
                drag_data = orjson.loads(data_bytes.decode('utf-8'))
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
                if hasattr(node, 'status'):
                    node.status = NodeStatus.NODE_STATUS_UNRUN

                # 变量节点自动设置部分属性，便于与普通节点区分
                if mime_data.hasFormat("application/x-global-variable"):
                    data_bytes = bytes(mime_data.data("application/x-global-variable"))
                    drag_data = orjson.loads(data_bytes.decode('utf-8'))
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
        if hasattr(self, '_selection_overlay') and self._selection_overlay._visible:
            self._selection_overlay.refresh(full_recalc=False)
        return super().resizeEvent(event)

    def zoom_to_nodes(self, nodes, duration=None):
        # --- 精确计算可见区域 (解决对齐问题) ---
        def get_tight_bbox(item_list):
            rect = QtCore.QRectF()
            first = True
            for node in item_list:
                # 获取节点自身在场景中的坐标
                node_scene_rect = node.sceneBoundingRect()

                # 1. 先拿节点自身的 boundingRect (通常是背景框)
                tight_rect = node.mapRectToScene(node.boundingRect())

                # 2. 遍历子项，只合并可见的
                if hasattr(node, 'childItems'):
                    for child in node.childItems():
                        if child.isVisible():
                            # 将子项的包围盒映射到场景并合并
                            tight_rect = tight_rect.united(child.sceneBoundingRect())
                else:
                    # 如果没有子项接口，回退到默认
                    tight_rect = node_scene_rect

                if first:
                    rect = tight_rect
                    first = False
                else:
                    rect = rect.united(tight_rect)
            return rect

        if not Settings.get_instance().node_animation.value:
            self._scene_range = get_tight_bbox(nodes)
            self._update_scene()

            if self.get_zoom() > 0.1:
                self.reset_zoom(self._scene_range.center())
            return
        if not nodes:
            return

        # --- 优化 1: 性能设置 ---
        # 动画期间不仅关闭抗锯齿，建议暂时将视口更新模式设为全视口更新或智能更新，防止局部重绘闪烁
        # 注意：这里假设 self 是 QGraphicsView 的子类
        original_render_hint = self.renderHints()
        self.setRenderHint(QtGui.QPainter.Antialiasing, False)
        # 这一步能显著提高大场景缩放时的帧率
        self.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, False)

        # --- 优化 2: 安全清理旧动画 ---
        if hasattr(self, '_zoom_anim_group') and self._zoom_anim_group:
            if self._zoom_anim_group.state() == QtCore.QAbstractAnimation.Running:
                self._zoom_anim_group.stop()
            # 显式删除以防内存泄漏
            self._zoom_anim_group.deleteLater()
            self._zoom_anim_group = None

        start_rect = QtCore.QRectF(self._scene_range)
        target_rect = get_tight_bbox(nodes)

        # 如果没有选中有效节点，直接返回
        if target_rect.isNull():
            self.setRenderHints(original_render_hint)
            return

        # 增加 Padding (根据目标大小动态调整，而不是固定的 60，视觉更舒适)
        # 基础 Padding 50px，外加目标宽度的 5%
        padding = 50 + (target_rect.width() * 0.05)
        target_rect.adjust(-padding, -padding, padding, padding)

        # --- 修正视口比例 (防止变形或过度贴边) ---
        # 确保 target_rect 的长宽比至少匹配视口，这样缩放后节点会居中而不是靠在角落
        view_rect = self.viewport().rect()
        if view_rect.width() > 0 and view_rect.height() > 0:
            view_ratio = view_rect.width() / view_rect.height()
            target_ratio = target_rect.width() / target_rect.height()

            if target_ratio > view_ratio:
                # 目标太宽，增加高度以匹配视口比例
                new_height = target_rect.width() / view_ratio
                delta = (new_height - target_rect.height()) / 2
                target_rect.adjust(0, -delta, 0, delta)
            else:
                # 目标太高，增加宽度以匹配视口比例
                new_width = target_rect.height() * view_ratio
                delta = (new_width - target_rect.width()) / 2
                target_rect.adjust(-delta, 0, delta, 0)

        # --- 优化 4: 智能时长计算 ---
        dist = (start_rect.center() - target_rect.center()).manhattanLength()
        needs_flyover = dist > start_rect.width() * 2.0  # 稍微降低 Flyover 的触发阈值

        if duration is None:
            zoom_diff = abs(start_rect.width() - target_rect.width())
            # 稍微加快节奏：减少基础时间，增加距离权重
            # 让短距离极快(350ms)，长距离平滑(最长 1000ms)
            calc_duration = 550 + (dist * 0.15) + (zoom_diff * 0.05)
            duration = int(max(600, min(calc_duration, 1000)))

        self._zoom_anim_group = QtCore.QSequentialAnimationGroup(self)

        def on_finished():
            # 恢复原始渲染提示
            self.setRenderHints(original_render_hint)
            # 强制刷新一次以确保抗锯齿生效
            self.viewport().update()
            self._zoom_anim_group = None

        self._zoom_anim_group.finished.connect(on_finished)

        def n_update(value):
            # 直接更新属性，减少 try-except 开销（除非多线程销毁）
            if not sip.isdeleted(self):
                self._scene_range = value
                self._update_scene()

                # --- 优化 5: 动画曲线与构建 ---

        # 使用 OutQuart 或 OutExpo 替代 OutCubic，这会让动画在结尾处“刹车”得更干脆，
        # 中间过程更快，给人的“流畅感”更强。
        easing_curve = QtCore.QEasingCurve.OutQuart

        if needs_flyover:
            # Flyover: 先拉远再推近
            overview_rect = start_rect.united(target_rect)
            # 动态调整拉远的范围，不要拉得太远导致看不清
            margin = overview_rect.width() * 0.1
            overview_rect.adjust(-margin, -margin, margin, margin)

            anim_out = QtCore.QVariantAnimation(self._zoom_anim_group)
            anim_out.setDuration(int(duration * 0.4))  # 拉远稍快
            anim_out.setStartValue(start_rect)
            anim_out.setEndValue(overview_rect)
            anim_out.setEasingCurve(QtCore.QEasingCurve.OutQuad)  # 拉远用 Quad，比较柔和
            anim_out.valueChanged.connect(n_update)

            anim_in = QtCore.QVariantAnimation(self._zoom_anim_group)
            anim_in.setDuration(int(duration * 0.6))  # 推近稍慢，便于人眼聚焦
            anim_in.setStartValue(overview_rect)
            anim_in.setEndValue(target_rect)
            anim_in.setEasingCurve(QtCore.QEasingCurve.OutQuart)  # 推近用 Quart，精准停靠
            anim_in.valueChanged.connect(n_update)

            self._zoom_anim_group.addAnimation(anim_out)
            # 移除暂停或极大缩短暂停，暂停会产生卡顿感
            self._zoom_anim_group.addAnimation(anim_in)
        else:
            # 直接平移
            anim_direct = QtCore.QVariantAnimation(self._zoom_anim_group)
            anim_direct.setDuration(duration)
            anim_direct.setStartValue(start_rect)
            anim_direct.setEndValue(target_rect)
            anim_direct.setEasingCurve(easing_curve)
            anim_direct.valueChanged.connect(n_update)
            self._zoom_anim_group.addAnimation(anim_direct)

        self._zoom_anim_group.start(QtCore.QAbstractAnimation.DeleteWhenStopped)


class CustomNodeGraph(NodeGraph):

    def __init__(self, parent, **kwargs):
        super(CustomNodeGraph, self).__init__(parent, **kwargs)
        self._register_context_menu()
        self._viewer.graph = self
        self.global_variables = GlobalVariableContext()  # 画布全局变量

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
        serial_str = orjson.dumps(serialize_for_json(serial_data)).decode("utf-8")
        if serial_str:
            clipboard.setText(serial_str)
            return True
        return False

    def paste_nodes(self, cb_data, adjust_graph_style=True):
        """
        Pastes nodes copied from the clipboard.

        Args:
            adjust_graph_style (bool): if true adjust the node graph properties
                                        other wise only the nodes are pasted.
        Returns:
            list[NodeGraphQt.BaseNode]: list of pasted node instances.
        """

        serial_data = deserialize_from_json(cb_data)
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

    def serialize_session(self, exclude_keys: list[str]=[]):
        """
        Serializes the current node graph layout to a dictionary.

        See Also:
            :meth:`NodeGraph.deserialize_session`,
            :meth:`NodeGraph.save_session`,
            :meth:`NodeGraph.load_session`

        Returns:
            dict: serialized session of the current node layout.
        """
        return self._serialize(self.all_nodes(), exclude_keys)

    def _serialize(self, nodes, exclude_keys: list[str]=[]):
        """
        serialize nodes to a dict.
        (used internally by the node graph)

        Args:
            nodes (list[NodeGraphQt.Nodes]): list of node instances.

        Returns:
            dict: serialized data.
        """
        serial_data = {'graph': {}, 'nodes': {}, 'connections': []}
        nodes_data = {}

        # serialize graph session.
        serial_data['graph']['layout_direction'] = self.layout_direction()
        serial_data['graph']['acyclic'] = self.acyclic()
        serial_data['graph']['pipe_collision'] = self.pipe_collision()
        serial_data['graph']['pipe_slicing'] = self.pipe_slicing()
        serial_data['graph']['pipe_style'] = self.pipe_style()

        # serialize nodes.
        for n in nodes:
            # update the node model.
            n.update_model()

            node_dict = n.model.to_dict
            n_id = list(node_dict.keys())[0]
            node_dict[n_id].update(
                {
                    "input_ports": [{"name": p.name(), "multi_connection": p.model.multi_connection} for p in n.input_ports()],
                    "output_ports": [{"name": p.name(), "multi_connection": p.model.multi_connection} for p in
                                    n.output_ports()],
                    "output_values": {} if not hasattr(n, "_output_values") else serialize_for_json(n._output_values)
                }
            )
            node_dict[n_id]["custom"]["FULL_PATH"] = n.FULL_PATH
            # 过滤不需要的字段
            node_dict[n_id] = {k: v for k, v in node_dict[n_id].items() if k not in exclude_keys}
            nodes_data.update(node_dict)

        for n_id, n_data in nodes_data.items():
            serial_data['nodes'][n_id] = n_data

            # serialize connections
            inputs = n_data.pop('inputs') if n_data.get('inputs') else {}
            outputs = n_data.pop('outputs') if n_data.get('outputs') else {}

            for pname, conn_data in inputs.items():
                for conn_id, prt_names in conn_data.items():
                    for conn_prt in prt_names:
                        pipe = {
                            PortTypeEnum.IN.value: [n_id, pname],
                            PortTypeEnum.OUT.value: [conn_id, conn_prt]
                        }
                        if pipe not in serial_data['connections']:
                            serial_data['connections'].append(pipe)

            for pname, conn_data in outputs.items():
                for conn_id, prt_names in conn_data.items():
                    for conn_prt in prt_names:
                        pipe = {
                            PortTypeEnum.OUT.value: [n_id, pname],
                            PortTypeEnum.IN.value: [conn_id, conn_prt]
                        }
                        if pipe not in serial_data['connections']:
                            serial_data['connections'].append(pipe)

        if not serial_data['connections']:
            serial_data.pop('connections')
        # 全局变量序列化
        serial_data['global_variables'] = self.global_variables.serialize()

        return serial_data

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
        try:
            if isinstance(data, str): return
            self._viewer.scene().blockSignals(True)
            self._viewer.setUpdatesEnabled(False)
            # 反序列化 全局变量
            if data.get("global_variables"):
                self.global_variables.deserialize(data.get("global_variables"))
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
                node._output_values = deserialize_from_json(n_data.get('output_values', {}))
                if node:
                    # 避免复制时触发重命名信号
                    node.NODE_NAME = n_data.get('name', node.NODE_NAME)
                    # set properties.
                    for prop in node.model.properties.keys():
                        if prop in n_data.keys():
                            node.model.set_property(prop, n_data[prop])
                    self.add_node(node, n_data.get('pos'), inherite_graph_style=adjust_graph_style)
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
                                var_type = getattr(node.view.widgets[prop], "var_type")\
                                        if hasattr(node.view.widgets[prop], "var_type") else None
                                if GlobalVariableContext.is_variable_name(val) and var_type != "全局变量":
                                    node.view.widgets[prop].toggle_global_mode(True)
                                node.view.widgets[prop].set_value(val)
                        elif node.type_ == "general.StickyNote":
                            node.set_property(prop, val)
                    # 决定是否还原节点最后保存时缩放大小
                    if node_resize_memory and hasattr(node.view, '_sync_size_from_model'):
                        node.view._sync_size_from_model(node_width, node_height)
                    # 改变节点状态，成功状态改为上次成功状态进行区分
                    if n_data["custom"].get("_status") == NodeStatus.NODE_STATUS_SUCCESS:
                        n_data["custom"]["_status"] = NodeStatus.NODE_STATUS_LAST_SUCCESS
                    if hasattr(node, "status"):
                        node.status = n_data["custom"].get("_status")
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

                    # 改变节点状态，成功状态改为上次成功状态进行区分
                    if n_data["custom"].get("_status") == NodeStatus.NODE_STATUS_SUCCESS:
                        n_data["custom"]["_status"] = NodeStatus.NODE_STATUS_LAST_SUCCESS
                    if hasattr(node, "status"):
                        node.status = n_data["custom"].get("_status")

            node_objs = nodes.values()
            if relative_pos:
                self._viewer.move_nodes([n.view for n in node_objs])
                [setattr(n.model, 'pos', n.view.xy_pos) for n in node_objs]
            elif pos:
                self._viewer.move_nodes([n.view for n in node_objs], pos=pos)
                [setattr(n.model, 'pos', n.view.xy_pos) for n in node_objs]
            QtCore.QTimer.singleShot(150, lambda: self.build_connections(data, nodes))
        except:
            logger.exception("Error while building nodes")
            return

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

    def get_node_by_uuid(self, uuid):
        """
        Returns node that matches the name.

        Args:
            name (str): name of the node.
        Returns:
            NodeGraphQt.NodeObject: node object.
        """
        for node_id, node in self._model.nodes.items():
            if node.persistent_id == uuid:
                return node