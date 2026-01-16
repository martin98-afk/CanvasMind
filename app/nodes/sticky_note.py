# -*- coding: utf-8 -*-
import json
from NodeGraphQt import BackdropNode
from NodeGraphQt.constants import NodePropWidgetEnum

from app.widgets.custom_nodegraphqt.sticky_note_item import StickyNoteItem


class StickyNoteNode(BackdropNode):
    __identifier__ = 'general'
    NODE_NAME = '注释节点'

    def __init__(self):
        super(StickyNoteNode, self).__init__(qgraphics_views=StickyNoteItem)
        self.view.node = self

        # 核心数据属性
        self.create_property('notes_json', '', widget_type=NodePropWidgetEnum.HIDDEN.value)

        # 样式属性
        self.set_property('color', (45, 45, 155, 255))
        self.set_property('width', 500)
        self.set_property('height', 400)

    def set_property(self, name, value, push_undo=True):
        super(StickyNoteNode, self).set_property(name, value, push_undo)
        if name == 'notes_json' and self.view:
            if value and not self.view._text_blocks:
                self.view.load_data(value)

    def on_selected_nodes(self, nodes):
        pass

    def nodes(self):
        return []