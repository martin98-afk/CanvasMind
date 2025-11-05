import json

from NodeGraphQt import NodeGraph, BaseNode
from NodeGraphQt.base.commands import PortConnectedCmd
from NodeGraphQt.constants import LayoutDirectionEnum, PipeLayoutEnum, ViewerEnum, Z_VAL_PIPE
from NodeGraphQt.qgraphics.pipe import LivePipeItem
from NodeGraphQt.qgraphics.slicer import SlicerPipeItem
from NodeGraphQt.widgets.actions import BaseMenu
from NodeGraphQt.widgets.scene import NodeScene
from NodeGraphQt.widgets.tab_search import TabSearchMenuWidget
from NodeGraphQt.widgets.viewer import NodeViewer
from qtpy import QtGui, QtCore, QtWidgets


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

        self._LIVE_PIPE = LivePipeItem()
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


class CustomNodeGraph(NodeGraph):

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

        # update node graph properties.
        try:
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
                        node.model.set_property(prop, val)
                        if isinstance(node, BaseNode):
                            if prop in node.view.widgets:
                                node.view.widgets[prop].set_value(val)

                    nodes[n_id] = node

                    if not getattr(node, 'component_class', None) and n_data.get('port_deletion_allowed', None):
                        node.set_ports({
                            'input_ports': n_data['input_ports'],
                            'output_ports': n_data['output_ports']
                        })

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

                    if n_data.get('port_deletion_allowed', None):
                        node.set_ports({
                            'input_ports': n_data['input_ports'],
                            'output_ports': n_data['output_ports']
                        })

            QtCore.QTimer.singleShot(50, lambda: self.build_connections(data, nodes))
            node_objs = nodes.values()
            if relative_pos:
                self._viewer.move_nodes([n.view for n in node_objs])
                [setattr(n.model, 'pos', n.view.xy_pos) for n in node_objs]
            elif pos:
                self._viewer.move_nodes([n.view for n in node_objs], pos=pos)
                [setattr(n.model, 'pos', n.view.xy_pos) for n in node_objs]
        finally:
            # === 9. 恢复 UI 更新 ===
            self._viewer.setUpdatesEnabled(True)
            self._viewer.scene().blockSignals(False)
            self._viewer.scene().update()

        return node_objs

    def build_connections(self, data, nodes):

        # build the connections.
        for connection in data.get('connections', []):
            nid, pname = connection.get('in', ('', ''))
            in_node = nodes.get(nid) or self.get_node_by_id(nid)
            if not in_node:
                continue
            in_port = in_node.inputs().get(pname) if in_node else None

            nid, pname = connection.get('out', ('', ''))
            out_node = nodes.get(nid) or self.get_node_by_id(nid)
            if not out_node:
                continue
            out_port = out_node.outputs().get(pname) if out_node else None

            if in_port and out_port:
                # only connect if input port is not connected yet or input port
                allow_connection = any([not in_port.model.connected_ports,
                                        in_port.model.multi_connection])
                if allow_connection:
                    self._undo_stack.push(
                        PortConnectedCmd(in_port, out_port, emit_signal=False)
                    )

                # Run on_input_connected to ensure connections are fully set up
                # after deserialization.
                in_node.on_input_connected(in_port, out_port)