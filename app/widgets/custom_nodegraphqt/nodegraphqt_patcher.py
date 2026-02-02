from NodeGraphQt.base.model import NodeModel
from NodeGraphQt.constants import NodePropWidgetEnum
from NodeGraphQt.errors import NodePropertyError
from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem
from NodeGraphQt.qgraphics.node_backdrop import BackdropNodeItem
from NodeGraphQt.qgraphics.node_base import NodeItem
from NodeGraphQt.widgets.viewer_nav import NodeNavigationWidget
from PyQt5 import QtCore, QtGui


def add_property(self, name, value, items=None, range=None,
                 widget_type=None, widget_tooltip=None, tab=None):
    """
    add custom property or raises an error if the property name is already
    taken.

    Args:
        name (str): name of the property.
        value (object): data.
        items (list[str]): items used by widget type NODE_PROP_QCOMBO.
        range (tuple): min, max values used by NODE_PROP_SLIDER.
        widget_type (int): widget type flag.
        widget_tooltip (str): custom tooltip for the property widget.
        tab (str): widget tab name.
    """
    widget_type = widget_type or NodePropWidgetEnum.HIDDEN.value
    tab = tab or 'Properties'

    if name in self._custom_prop.keys():
        raise NodePropertyError(
            '"{}" property already exists.'.format(name))

    self._custom_prop[name] = value

    if self._graph_model is None:
        self._TEMP_property_widget_types[name] = widget_type
        self._TEMP_property_attrs[name] = {'tab': tab}
        if items:
            self._TEMP_property_attrs[name]['items'] = items
        if range:
            self._TEMP_property_attrs[name]['range'] = range
        if widget_tooltip:
            self._TEMP_property_attrs[name]['tooltip'] = widget_tooltip

    else:
        attrs = {
            self.type_: {
                name: {
                    'widget_type': widget_type,
                    'tab': tab
                }
            }
        }
        if items:
            attrs[self.type_][name]['items'] = items
        if range:
            attrs[self.type_][name]['range'] = range
        if widget_tooltip:
            attrs[self.type_][name]['tooltip'] = widget_tooltip
        self._graph_model.set_node_common_properties(attrs)


def add_label_item(self, label, node_id):
    item = QtGui.QStandardItem(label)
    item.setToolTip(node_id)
    metrics = QtGui.QFontMetrics(item.font())
    if hasattr(metrics, 'horizontalAdvance'):
        width = metrics.horizontalAdvance(item.text())
    else:
        width = metrics.width(item.text())
    width *= 1.5
    item.setSizeHint(QtCore.QSize(int(width), 20))
    self.model().appendRow(item)
    self.selectionModel().setCurrentIndex(
        self.model().indexFromItem(item),
        QtCore.QItemSelectionModel.ClearAndSelect)


def get_wwidth(self):
    return self._width

def set_wwidth(self, width=0.0):
    self._width = width

def get_hheight(self):
    return self._height

def set_hheight(self, height=0.0):
    self._height = height

# --- 3. 替换 properties 方法 (因为它是一个 @property) ---

def patched_properties(self):
    """
    对应你源码中的 properties 逻辑
    """
    # 注意：你源码中写的是 self.width，这里建议指向 patch 后的 self.wwidth
    props = {
        'wwidth': self.width,
        'hheight': self.height,
        'pos': self.xy_pos
    }
    props.update(self._properties)
    return props

# --- 4. 替换 from_dict 方法 (这是一个普通方法) ---

def patched_from_dict(self, node_dict):
    """
    对应你源码中的 from_dict 逻辑
    """
    node_attrs = list(self._properties.keys()) + ['wwidth', 'hheight', 'pos']
    for name, value in node_dict.items():
        if name in node_attrs:
            if name == 'pos':
                name = 'xy_pos'
            elif name == "wwidth":
                name = "width"
            elif name == "hheight":
                name = "height"
            setattr(self, name, value)


def patched_width_setter(self, width=0.0):
    # 调用 wwidth 的 setter (fset) 来更新基础值
    # 这样可以确保如果 wwidth 也有补丁逻辑，会被一同触发
    AbstractNodeItem.wwidth.fset(self, width)

    # 触发你需要的联动逻辑
    if hasattr(self, '_sizer'):
        self._sizer.set_pos(self._width, self._height)


def patched_height_setter(self, height=0.0):
    # 调用 hheight 的 setter (fset)
    AbstractNodeItem.hheight.fset(self, height)

    # 触发你需要的联动逻辑
    if hasattr(self, '_sizer'):
        self._sizer.set_pos(self._width, self._height)


def set_property(self, name, value):
    """
    Args:
        name (str): property name.
        value (object): property value.
    """
    if name in self.properties.keys():
        setattr(self, name, value)
    elif name in self._custom_prop.keys():
        self._custom_prop[name] = value
    else:
        self.add_property(name, value)


def patch_nodegraphqt():
    """解决nodegraphqt内部函数问题"""
    # 动态替换掉库里的原始函数
    NodeNavigationWidget.add_label_item = add_label_item
    NodeModel.add_property = add_property
    NodeModel.set_property = set_property
    # --- 2. 为类注入新的 Property ---
    # 注意：必须在类级别（AbstractNodeItem）赋值，而不是实例级别
    # AbstractNodeItem.wwidth = property(get_wwidth, set_wwidth)
    # AbstractNodeItem.hheight = property(get_hheight, set_hheight)
    # AbstractNodeItem.properties = property(patched_properties)
    # AbstractNodeItem.from_dict = patched_from_dict
    # width_getter = AbstractNodeItem.width.fget
    # height_getter = AbstractNodeItem.height.fget

    # 重新定义 width 和 height 属性
    # BackdropNodeItem.width = property(fget=width_getter, fset=patched_width_setter)
    # BackdropNodeItem.height = property(fget=height_getter, fset=patched_height_setter)
    # NodeItem.width = property(fget=width_getter, fset=patched_width_setter)
    # NodeItem.height = property(fget=height_getter, fset=patched_height_setter)