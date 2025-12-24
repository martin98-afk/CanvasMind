import json

from NodeGraphQt import NodeGraph, BaseNode, NodeGraphMenu
from NodeGraphQt.constants import LayoutDirectionEnum, PipeLayoutEnum, ViewerEnum, Z_VAL_PIPE
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem
from NodeGraphQt.qgraphics.pipe import PipeItem
from NodeGraphQt.qgraphics.slicer import SlicerPipeItem
from NodeGraphQt.widgets.scene import NodeScene
from NodeGraphQt.widgets.tab_search import TabSearchMenuWidget
from NodeGraphQt.widgets.viewer import NodeViewer
from qtpy import QtGui, QtCore, QtWidgets

from app.widgets.custom_nodegraphqt.custom_node_menu import CustomNodesMenu, BaseMenu
from app.widgets.custom_nodegraphqt.custom_pipe_item import CustomLivePipeItem, CustomPipeItem


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
        self.setScene(CustomNodeScene(self))
        self.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.BoundingRectViewportUpdate)
        self.setCacheMode(QtWidgets.QGraphicsView.CacheBackground)

        self.setAcceptDrops(True)
        self.resize(850, 800)

        self._scene_range = QtCore.QRectF(
            0, 0, self.size().width(), self.size().height())
        self._update_scene()
        self._last_size = self.size()

        self._layout_direction = LayoutDirectionEnum.HORIZONTAL.value

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

    def establish_connection(self, start_port, end_port):
        """
        establish a new pipe connection.
        (adds a new pipe item to draw between 2 ports)
        """
        pipe = CustomPipeItem()
        self.scene().addItem(pipe)
        pipe.set_connections(start_port, end_port)
        pipe.draw_path(pipe.input_port, pipe.output_port)
        if start_port.node.selected or end_port.node.selected:
            pipe.highlight()
        if not start_port.node.visible or not end_port.node.visible:
            pipe.hide()

    def mousePressEvent(self, event):
        # 检查是否是平移操作
        if (event.button() == QtCore.Qt.MiddleButton or
                (event.button() == QtCore.Qt.LeftButton and event.modifiers() == QtCore.Qt.AltModifier)):
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

        # close tab search
        if self._search_widget.isVisible():
            self.tab_search_toggle()

        # cursor pos.
        map_pos = self.mapToScene(event.pos())

        # pipe slicer enabled.
        if self.pipe_slicing:
            slicer_mode = all([
                self.ALT_state, self.SHIFT_state, self.LMB_state
            ])
            if slicer_mode:
                self._SLICER_PIPE.draw_path(map_pos, map_pos)
                self._SLICER_PIPE.setVisible(True)
                return

        # pan mode.
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

        # record the node selection as "self.selected_nodes()" is not updated
        # here on the mouse press event.
        selection = set([])

        if self.LMB_state:
            # toggle extend node selection.
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
            # unselected nodes with the "ctrl" key.
            elif self.CTRL_state:
                if items and backdrop == items[0]:
                    backdrop.selected = False
                else:
                    for node in nodes:
                        node.selected = False
            # if no modifier keys then add to selection set.
            else:

                if backdrop:
                    selection.add(backdrop)
                    for n in backdrop.get_nodes():
                        selection.add(n)
                for node in nodes:
                    if node.selected:
                        selection.add(node)


        selection.update(self.selected_nodes())

        # update the recorded node positions.
        self._node_positions.update({n: n.xy_pos for n in selection})

        # show selection marquee.
        if self.LMB_state and not items:
            rect = QtCore.QRect(self._previous_pos, QtCore.QSize())
            rect = rect.normalized()
            map_rect = self.mapToScene(rect).boundingRect()
            self.scene().update(map_rect)
            self._rubber_band.setGeometry(rect)
            self._rubber_band.isActive = True

        # stop here so we don't select a node.
        # (ctrl modifier can be used for something else in future.)
        if self.CTRL_state:
            return

        # allow new live pipe with the shift modifier on port that allow
        # for multi connection.
        if self.SHIFT_state:
            if pipes:
                pipes[0].reset()
                port = pipes[0].port_from_pos(map_pos, reverse=True)
                if not port.locked and port.multi_connection:
                    self._cursor_text.setPlainText('')
                    self._cursor_text.setVisible(False)
                    self.start_live_connection(port)

            # return here as the default behaviour unselects nodes with
            # the shift modifier.
            return

        if not self._LIVE_PIPE.isVisible():
            super(NodeViewer, self).mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        was_panning = self._panning  # 记录是否刚结束平移
        if event.button() == QtCore.Qt.LeftButton:
            self.LMB_state = False
            if event.modifiers() == QtCore.Qt.AltModifier:
                self._panning = False
        elif event.button() == QtCore.Qt.RightButton:
            self.RMB_state = False
        elif event.button() == QtCore.Qt.MiddleButton:
            self.MMB_state = False
            self._panning = False

        # hide pipe slicer.
        if self._SLICER_PIPE.isVisible():
            self._on_pipes_sliced(self._SLICER_PIPE.path())
            p = QtCore.QPointF(0.0, 0.0)
            self._SLICER_PIPE.draw_path(p, p)
            self._SLICER_PIPE.setVisible(False)

        # hide selection marquee
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

                # emit the node selection signals.
                if node_ids:
                    prev_ids = [
                        n.id for n in self._prev_selection_nodes
                        if not n.selected
                    ]
                    self.node_selected.emit(node_ids[0])
                    self.node_selection_changed.emit(node_ids, prev_ids)

                self.scene().update(map_rect)
                return

        # find position changed nodes and emit signal.
        moved_nodes = {
            n: xy_pos for n, xy_pos in self._node_positions.items()
            if n.xy_pos != xy_pos
        }
        # only emit of node is not colliding with a pipe.
        if moved_nodes and not self.COLLIDING_state:
            self.moved_nodes.emit(moved_nodes)

        # reset recorded positions.
        self._node_positions = {}

        # emit signal if selected node collides with pipe.
        # Note: if collide state is true then only 1 node is selected.
        nodes, pipes = self.selected_items()
        if self.COLLIDING_state and nodes and pipes:
            self.insert_node.emit(pipes[0], nodes[0].id, moved_nodes)

        # 关键：只有在非平移操作时才检查选中变化
        if not was_panning:
            prev_ids = [n.id for n in self._prev_selection_nodes if not n.selected]
            nodes, _ = self.selected_items()
            node_ids = [n.id for n in nodes if n not in self._prev_selection_nodes]
            self.node_selection_changed.emit(node_ids, prev_ids)
        # 更新 _prev_selection_nodes（无论是否平移）
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
        self._viewer.scene().blockSignals(True)
        self._viewer.setUpdatesEnabled(False)

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
            # 判断是否为 backdrop 节点（通常 backdrop 节点类型包含 'backdrop' 或类似的标识）
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
            node = self._node_factory.create_node_instance(identifier)
            if node:
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
                        pass
                    if isinstance(node, BaseNode):
                        if prop in node.view.widgets:
                            node.view.widgets[prop].set_value(val)

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
                # set custom properties.
                for prop, val in n_data.get('custom', {}).items():
                    node.model.set_property(prop, val)
                    if isinstance(node, BaseNode):
                        if prop in node.view.widgets:
                            node.view.widgets[prop].set_value(val)

                nodes[n_id] = node
        node_objs = nodes.values()
        if relative_pos:
            self._viewer.move_nodes([n.view for n in node_objs])
            [setattr(n.model, 'pos', n.view.xy_pos) for n in node_objs]
        elif pos:
            self._viewer.move_nodes([n.view for n in node_objs], pos=pos)
            [setattr(n.model, 'pos', n.view.xy_pos) for n in node_objs]
        QtCore.QTimer.singleShot(100, lambda: self.build_connections(data, nodes))

        return node_objs

    def build_connections(self, data, nodes):
        """
        Internal method to build connections after nodes are added.
        This should be called with signals blocked and updates disabled.
        """
        # build the connections.
        for connection in data.get('connections', []):
            in_nid, in_pname = connection.get('in', ('', ''))
            out_nid, out_pname = connection.get('out', ('', ''))

            # 直接从 nodes 字典获取，避免额外查找
            in_node = nodes.get(in_nid)
            out_node = nodes.get(out_nid)

            if not in_node or not out_node:
                # 如果数据不一致，记录警告或跳过
                # logger.warning(f"Connection references non-existent nodes: in={in_nid}, out={out_nid}")
                continue

            in_port = in_node.inputs().get(in_pname)
            out_port = out_node.outputs().get(out_pname)

            if in_port and out_port:
                allow_connection = any([not in_port.model.connected_ports,
                                        in_port.model.multi_connection])
                if allow_connection:

                    in_port.connect_to(out_port) # 直接连接，不经过 undo 命令

                # 在连接建立后调用回调
                in_node.on_input_connected(in_port, out_port)

        self._viewer.setUpdatesEnabled(True)
        self._viewer.scene().blockSignals(False)
        self._viewer.scene().update()