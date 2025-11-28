from distutils.version import LooseVersion

from NodeGraphQt import NodeGraphMenu, NodeGraphCommand
from NodeGraphQt.errors import NodeMenuError
from NodeGraphQt.widgets.actions import BaseMenu, NodeAction
from Qt import QtCore
from qtpy import QtGui


class CustomNodesMenu(NodeGraphMenu):
    """
    The ``NodesMenu`` is the context menu triggered from a node.

    .. inheritance-diagram:: NodeGraphQt.NodesMenu
        :parts: 1

    example for accessing the nodes context menu.

    .. code-block:: python
        :linenos:

        from NodeGraphQt import NodeGraph

        node_graph = NodeGraph()

        # get the nodes context menu.
        nodes_menu = node_graph.get_context_menu('nodes')
    """

    def add_command(self, name, func=None, node_type=None, node_class=None,
                    shortcut=None, icon=None):
        """
        Re-implemented to add a command to the specified node type menu.

        Args:
            name (str): command name.
            func (function): command function eg. "func(``graph``, ``node``)".
            node_type (str): specified node type for the command.
            node_class (class): specified node class for the command.
            shortcut (str): shortcut key.
            icon (QtGui.QIcon or str, optional):
                - If str: treated as file path to icon.
                - If QtGui.QIcon: used directly.
                - If None: no icon.

        Returns:
            NodeGraphQt.NodeGraphCommand: the appended command.
        """
        if not node_type and not node_class:
            raise NodeMenuError('Node type or Node class not specified!')

        if node_class:
            node_type = node_class.__name__

        node_menu = self.qmenu.get_menu(node_type)
        if not node_menu:
            node_menu = BaseMenu(node_type, self.qmenu)
            if node_class:
                node_menu.node_class = node_class
                node_menu.graph = self._graph
            self.qmenu.addMenu(node_menu)

        if not self.qmenu.isEnabled():
            self.qmenu.setDisabled(False)

        action = NodeAction(name, self._graph.viewer())
        action.graph = self._graph

        # === 新增：设置图标 ===
        if icon is not None:
            if isinstance(icon, str):
                # 假设字符串是文件路径
                icon = QtGui.QIcon(icon)
            if isinstance(icon, QtGui.QIcon):
                action.setIcon(icon)
        # ===================

        if LooseVersion(QtCore.qVersion()) >= LooseVersion('5.10'):
            action.setShortcutVisibleInContextMenu(True)

        if shortcut:
            self._set_shortcut(action, shortcut)
        if func:
            action.executed.connect(func)

        if node_class:
            node_menus = self.qmenu.get_menus(node_class)
            if node_menu in node_menus:
                node_menus.remove(node_menu)
            for menu in node_menus:
                menu.addAction(action)

        node_menu.addAction(action)
        command = NodeGraphCommand(self._graph, action, func)
        self._commands[name] = command
        self._items.append(command)
        return command
    
    def add_separator(self, node_type):
        """
        Adds a separator to the menu.
        """
        node_menu = self.qmenu.get_menu(node_type)
        node_menu.addSeparator()
        self._items.append(None)