# -*- coding: utf-8 -*-
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem
from qtpy import QtCore, QtGui, QtWidgets
from NodeGraphQt import BackdropNode

from app.widgets.custom_nodegraphqt.sticky_note_item import StickyNoteItem


# ------------------------------------------------------------------------------
# 2. 逻辑层 (Node)
# ------------------------------------------------------------------------------

class StickyNoteNode(BackdropNode):
    __identifier__ = 'general'
    NODE_NAME = '注释节点'
    description = '注释节点，可以进行文本编辑'

    def __init__(self):
        super(StickyNoteNode, self).__init__(qgraphics_views=StickyNoteItem)
        self.set_icon(":/icons/文本注释.svg")
        self.view.node = self
        # 添加 note_text 属性到 model 中，这是保存到 JSON 的关键
        self.model.add_property('note_text', '')

        self.set_property('color', (40, 40, 40, 255))
        self.set_property('width', 250)
        self.set_property('height', 180)

    def set_property(self, name, value, push_undo=True):
        super(StickyNoteNode, self).set_property(name, value, push_undo)
        if name == 'note_text' and self.view:
            self.view.set_text(value)

        # 【核心修正 3】：当宽高改变时，强制刷新视图
        if name in ['width', 'height'] and self.view:
            self.view.update()

    def on_selected_nodes(self, nodes):
        # 覆盖 Backdrop 逻辑：禁止它自动“吸附”移动其他节点
        pass

    def nodes(self):
        # 让它表现得像普通节点，不包含任何子节点
        return []

    def set_text(self, text):
        self.set_property('note_text', text)

    def get_text(self):
        return self.get_property('note_text')

    def on_backdrop_item_resize(self, old_size, new_size):
        """当通过右下角拖拽缩放时触发"""
        super(StickyNoteNode, self).on_backdrop_item_resize(old_size, new_size)
        # 拖拽时强制视图重新布局文本
        if self.view:
            self.view.update()

    def set_icon(self, icon=None):
        """
        Set the node icon.

        Args:
            icon (str): path to the icon image.
        """
        self.set_property('icon', icon)