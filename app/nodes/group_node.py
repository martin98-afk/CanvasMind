# -*- coding: utf-8 -*-
from NodeGraphQt import GroupNode
from NodeGraphQt.qgraphics.node_group import GroupNodeItem


def create_group_node_class(graph, parent_window):

    class CustomGroupNode(GroupNode):
        __identifier__ = 'general'
        NODE_NAME = 'GroupNode'

        def __init__(self):
            super(CustomGroupNode, self).__init__(qgraphics_item=GroupNodeItem)
            self.set_color(50, 50, 50)  # 设置一个深色背景

    return CustomGroupNode
