from NodeGraphQt.constants import ViewerEnum, Z_VAL_NODE_WIDGET
from NodeGraphQt.errors import NodeWidgetError
from qtpy import QtWidgets, QtCore

from app.utils.config import Settings


class _NodeGroupBox(QtWidgets.QGroupBox):

    def __init__(self, label, parent=None):
        super(_NodeGroupBox, self).__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(1)
        self._label = label

        # 应用初始字体
        self._update_font()

        self.setTitle(label)

    def _get_font_family(self):
        """从设置中获取字体名称"""
        try:
            return Settings().get_instance().canvas_font_type.value
        except Exception:
            return "Arial"  # 回退默认字体

    def _update_font(self):
        """统一设置控件的字体对象"""
        font_name = self._get_font_family()
        font = self.font()
        font.setFamily(font_name)
        self.setFont(font)

    def setTitle(self, text):
        self._label = text
        margin = (0, 2, 0, 0) if text else (0, 0, 0, 0)
        self.layout().setContentsMargins(*margin)
        super(_NodeGroupBox, self).setTitle(text)
        # 重新应用样式以适应新的标题和字体
        self.setTitleAlign(self._current_align if hasattr(self, '_current_align') else 'center')

    def setTitleAlign(self, align='center'):
        self._current_align = align
        font_family = self._get_font_family()

        text_color = tuple(map(lambda i, j: i - j, (255, 255, 255),
                               ViewerEnum.BACKGROUND_COLOR.value))

        style_dict = {
            'QGroupBox': {
                'background-color': 'rgba(0, 0, 0, 0)',
                'border': '0px solid rgba(0, 0, 0, 0)',
                'margin-top': '1px',
                'padding-bottom': '2px',
                'padding-left': '1px',
                'padding-right': '1px',
                'font-size': '12pt',
                'font-weight': 'bold',
                'font-family': font_family  # 注入字体
            },
            'QGroupBox::title': {
                'color': 'rgba({0}, {1}, {2}, 200)'.format(*text_color),
                'padding': '0px',
                'font-size': '12pt',
                'font-weight': 'bold',
                'font-family': font_family  # 注入字体
            }
        }

        if self.title():
            style_dict['QGroupBox']['padding-top'] = '18px'
        else:
            style_dict['QGroupBox']['padding-top'] = '2px'

        if align == 'center':
            style_dict['QGroupBox::title']['subcontrol-origin'] = 'margin'
            style_dict['QGroupBox::title']['subcontrol-position'] = 'top center'
        elif align == 'left':
            style_dict['QGroupBox::title']['subcontrol-origin'] = 'margin'
            style_dict['QGroupBox::title']['subcontrol-position'] = 'top left'
            style_dict['QGroupBox::title']['padding-left'] = '4px'
        elif align == 'right':
            style_dict['QGroupBox::title']['subcontrol-origin'] = 'margin'
            style_dict['QGroupBox::title']['subcontrol-position'] = 'top right'
            style_dict['QGroupBox::title']['padding-right'] = '4px'

        stylesheet = ''
        for css_class, css in style_dict.items():
            style = '{} {{\n'.format(css_class)
            for elm_name, elm_val in css.items():
                style += '  {}:{};\n'.format(elm_name, elm_val)
            style += '}\n'
            stylesheet += style
        self.setStyleSheet(stylesheet)

    def add_node_widget(self, widget):
        # 尝试给子控件也应用相同字体
        font_name = self._get_font_family()
        font = widget.font()
        font.setFamily(font_name)
        widget.setFont(font)

        self.layout().addWidget(widget)

    def get_node_widget(self):
        return self.layout().itemAt(0).widget()

    def minimumSizeHint(self):
        # 这里的 self.fontMetrics() 会根据 self.setFont 设置的字体自动更新
        size = super(_NodeGroupBox, self).minimumSizeHint()
        if self.title():
            font_metrics = self.fontMetrics()
            title_width = font_metrics.horizontalAdvance(self.title())
            min_width = max(size.width(), title_width + 20)
            size.setWidth(min_width)
        return size

    def sizeHint(self):
        size = super(_NodeGroupBox, self).sizeHint()
        if self.title():
            font_metrics = self.fontMetrics()
            title_width = font_metrics.horizontalAdvance(self.title())
            preferred_width = max(size.width(), title_width + 20)
            size.setWidth(preferred_width)
        return size


class CustomNodeBaseWidget(QtWidgets.QGraphicsProxyWidget):
    """
    This is the main wrapper class that allows a ``QtWidgets.QWidget`` to be
    added in a :class:`NodeGraphQt.BaseNode` object.

    .. inheritance-diagram:: NodeGraphQt.NodeBaseWidget
        :parts: 1

    Args:
        parent (NodeGraphQt.BaseNode.view): parent node view.
        name (str): property name for the parent node.
        label (str): label text above the embedded widget.
    """

    value_changed = QtCore.Signal(str, object)
    """
    Signal triggered when the ``value`` attribute has changed.

    (This is connected to the :meth: `BaseNode.set_property` function when the 
    widget is added into the node.)

    :parameters: str, object
    :emits: property name, propety value
    """

    def __init__(self, parent=None, name=None, label=''):
        super(CustomNodeBaseWidget, self).__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET)
        self._name = name
        self._label = label
        self._node = None

    def setToolTip(self, tooltip):
        tooltip = tooltip.replace('\n', '<br/>')
        tooltip = '<b>{}</b><br/>{}'.format(self.get_name(), tooltip)
        super(CustomNodeBaseWidget, self).setToolTip(tooltip)

    def on_value_changed(self, *args, **kwargs):
        """
        This is the slot function that
        Emits the widgets current :meth:`NodeBaseWidget.value` with the
        :attr:`NodeBaseWidget.value_changed` signal.

        Args:
            args: not used.
            kwargs: not used.

        Emits:
            str, object: <node_property_name>, <node_property_value>
        """
        self.value_changed.emit(self.get_name(), self.get_value())

    @property
    def type_(self):
        """
        Returns the node widget type.

        Returns:
            str: widget type.
        """
        return str(self.__class__.__name__)

    @property
    def node(self):
        """
        Returns the node object this widget is embedded in.
        (This will return ``None`` if the widget has not been added to
        the node yet.)

        Returns:
            NodeGraphQt.BaseNode: parent node.
        """
        return self._node

    def get_icon(self, name):
        """
        Returns the default icon from the Qt framework.

        Returns:
            str: icon name.
        """
        return self.style().standardIcon(QtWidgets.QStyle.StandardPixmap(name))

    def get_name(self):
        """
        Returns the parent node property name.

        Returns:
            str: property name.
        """
        return self._name

    def set_name(self, name):
        """
        Set the property name for the parent node.

        Important:
            The property name must be set before the widget is added to
            the node.

        Args:
            name (str): property name.
        """
        if not name:
            return
        if self.node:
            raise NodeWidgetError(
                'Can\'t set property name widget already added to a Node'
            )
        self._name = name

    def get_value(self):
        """
        Returns the widgets current value.

        You must re-implement this property to if you're using a custom widget.

        Returns:
            str: current property value.
        """
        raise NotImplementedError

    def set_value(self, text):
        """
        Sets the widgets current value.

        You must re-implement this property to if you're using a custom widget.

        Args:
            text (str): new text value.
        """
        raise NotImplementedError

    def get_custom_widget(self):
        """
        Returns the embedded QWidget used in the node.

        Returns:
            QtWidgets.QWidget: nested QWidget
        """
        widget = self.widget()
        return widget.get_node_widget()

    def set_custom_widget(self, widget):
        """
        Set the custom QWidget used in the node.

        Args:
            widget (QtWidgets.QWidget): custom.
        """
        if self.widget():
            raise NodeWidgetError('Custom node widget already set.')
        group = _NodeGroupBox(self._label)
        group.add_node_widget(widget)
        self.setWidget(group)

    def get_label(self):
        """
        Returns the label text displayed above the embedded node widget.

        Returns:
            str: label text.
        """
        return self._label

    def set_label(self, label=''):
        """
        Sets the label text above the embedded widget.

        Args:
            label (str): new label ext.
        """
        if self.widget():
            self.widget().setTitle(label)
        self._label = label