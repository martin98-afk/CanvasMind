from NodeGraphQt.qgraphics.node_base import NodeItem
from Qt import QtCore


class CustomNodeItem(NodeItem):
    _align = None

    def set_align(self, align):
        self._align = align

    def mousePressEvent(self, event):
        # 如果是右键，先选中自己（关键！）
        if event.button() == QtCore.Qt.RightButton:
            # 清除其他选择，只选中当前节点
            scene = self.scene()
            if scene:
                scene.clearSelection()
                self.setSelected(True)
        # 其他逻辑交给父类（包括左键、菜单弹出等）
        super().mousePressEvent(event)


    def _calc_size_horizontal(self):
        # width, height from node name text.
        text_w = self._text_item.boundingRect().width()
        text_h = self._text_item.boundingRect().height()

        # width, height from node ports.
        port_width = 0.0
        p_input_text_width = 0.0
        p_output_text_width = 0.0
        p_input_height = 0.0
        p_output_height = 0.0
        for port, text in self._input_items.items():
            if not port.isVisible():
                continue
            if not port_width:
                port_width = port.boundingRect().width()
            t_width = text.boundingRect().width()
            if text.isVisible() and t_width > p_input_text_width:
                p_input_text_width = text.boundingRect().width()
            p_input_height += port.boundingRect().height()
        for port, text in self._output_items.items():
            if not port.isVisible():
                continue
            if not port_width:
                port_width = port.boundingRect().width()
            t_width = text.boundingRect().width()
            if text.isVisible() and t_width > p_output_text_width:
                p_output_text_width = text.boundingRect().width()
            p_output_height += port.boundingRect().height()

        port_text_width = p_input_text_width + p_output_text_width

        # width, height from node embedded widgets.
        widget_width = 0.0
        widget_height = 0.0
        for widget in self._widgets.values():
            if not widget.isVisible():
                continue
            # ✅ 关键：直接调用 widget.widget().sizeHint()
            real_widget = widget.widget()
            if real_widget is not None:
                w_size = real_widget.sizeHint()
                w_width = w_size.width()
                w_height = w_size.height()
                if w_width > widget_width:
                    widget_width = w_width
                widget_height += w_height + 10
            else:
                w_width = widget.boundingRect().width()
                w_height = widget.boundingRect().height()
                if w_width > widget_width:
                    widget_width = w_width
                widget_height += w_height + 10

        side_padding = 0.0
        if all([widget_width, p_input_text_width, p_output_text_width]):
            port_text_width = max([p_input_text_width, p_output_text_width])
            port_text_width *= 2
        elif widget_width:
            side_padding = 10

        width = port_width + max([text_w, port_text_width]) + side_padding
        height = max([text_h, p_input_height, p_output_height, widget_height])
        if widget_width:
            # add additional width for node widget.
            width += widget_width
        height *= 1.05

        return width, height

    def _align_widgets_horizontal(self, v_offset):
        if not self._widgets:
            return
        rect = self.boundingRect()
        y = rect.y() + v_offset
        inputs = [p for p in self.inputs if p.isVisible()]
        outputs = [p for p in self.outputs if p.isVisible()]
        for widget in self._widgets.values():
            if not widget.isVisible():
                continue
            # ✅ 关键：使用 widget.widget().sizeHint() 获取真实尺寸
            real_widget = widget.widget()
            if real_widget is not None:
                w_size = real_widget.sizeHint()
                widget_width = w_size.width()
                widget_height = w_size.height()
            else:
                # fallback（理论上不会走到这里）
                br = widget.boundingRect()
                widget_width = br.width()
                widget_height = br.height()

            if self._align == 'left':
                x = rect.left() + 10
                widget.widget().setTitleAlign('left')
            elif self._align == 'right':
                x = rect.right() - widget_width - 10
                widget.widget().setTitleAlign('right')
            elif self._align == 'center':
                x = rect.center().x() - (widget_width / 2)
                widget.widget().setTitleAlign('center')
            else:
                if not inputs:
                    x = rect.left() + 10
                    widget.widget().setTitleAlign('left')
                elif not outputs:
                    x = rect.right() - widget_width - 10
                    widget.widget().setTitleAlign('right')
                else:
                    x = rect.center().x() - (widget_width / 2)
                    widget.widget().setTitleAlign('center')

            widget.setPos(x, y)
            y += widget_height + 8  # 使用真实高度