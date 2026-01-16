# -*- coding: utf-8 -*-
from NodeGraphQt import BackdropNode
from NodeGraphQt.constants import NodeEnum, NodePropWidgetEnum

from app.widgets.custom_nodegraphqt.sticky_note_item import StickyNoteItem


class StickyNoteNode(BackdropNode):
    __identifier__ = 'general'
    NODE_NAME = '超级注释'

    def __init__(self):
        super(StickyNoteNode, self).__init__(qgraphics_views=StickyNoteItem)
        self.view.node = self

        # 注册用于存储数据的隐藏属性
        self.create_property('notes_json', '', widget_type=NodePropWidgetEnum.HIDDEN.value)

        # 初始尺寸
        self.set_property('width', 500)
        self.set_property('height', 400)
        self.set_property('color', (45, 45, 45, 255))

    def set_property(self, name, value, push_undo=True):
        super(StickyNoteNode, self).set_property(name, value, push_undo)
        if name == 'notes_json' and self.view:
            # 只有在没有文本块时加载（防止编辑时覆盖）
            if value and not self.view._text_blocks:
                self.view.load_data(value)

    def nodes(self):
        return []  # 保持独立