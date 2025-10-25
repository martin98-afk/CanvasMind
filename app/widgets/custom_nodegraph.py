import json

from NodeGraphQt import NodeGraph, BaseNode
from NodeGraphQt.base.commands import PortConnectedCmd


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

                    if n_data.get('port_deletion_allowed', None):
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
                    # can have multiple connections.
                    # important when duplicating nodes.
                    allow_connection = any([not in_port.model.connected_ports,
                                            in_port.model.multi_connection])
                    if allow_connection:
                        self._undo_stack.push(
                            PortConnectedCmd(in_port, out_port, emit_signal=False)
                        )

                    # Run on_input_connected to ensure connections are fully set up
                    # after deserialization.
                    in_node.on_input_connected(in_port, out_port)

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