from NodeGraphQt.constants import ViewerEnum, Z_VAL_NODE_WIDGET
from NodeGraphQt.errors import NodeWidgetError
from qtpy import QtWidgets, QtCore, QtGui

from app.utils.config import Settings


class _NodeGroupBox(QtWidgets.QWidget):
    """
    自定义控件容器
    1. 垂直布局：上标题，下控件。
    2. 智能对齐：固定大小控件居中，其他控件填满。
    3. 支持隐藏标题。
    4. 视觉隔离间距。
    """

    def __init__(self, label, parent=None):
        super(_NodeGroupBox, self).__init__(parent)
        self._label_text = label

        # 主布局：垂直
        self.layout = QtWidgets.QVBoxLayout(self)
        # 底部保留 8px 间距，实现视觉隔离
        self.layout.setContentsMargins(0, 0, 0, 8)
        self.layout.setSpacing(1)

        # 标题 Label
        self._label_item = QtWidgets.QLabel(label)
        self._label_item.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.layout.addWidget(self._label_item)

        # 应用初始字体和样式
        self._update_font()
        self._apply_style()

    def _get_font_family(self):
        try:
            return Settings().get_instance().canvas_font_type.value
        except Exception:
            return "Arial"

    def _update_font(self):
        font_name = self._get_font_family()
        font = self.font()
        font.setFamily(font_name)
        self.setFont(font)

        if self._label_item:
            l_font = self._label_item.font()
            l_font.setFamily(font_name)
            l_font.setPointSize(10)
            l_font.setBold(True)
            self._label_item.setFont(l_font)

    def _apply_style(self):
        label_color = "rgba(170, 170, 170, 255)"

        style = f"""
            QWidget {{
                background-color: transparent;
            }}
            QLabel {{
                color: {label_color};
                border: none;
                padding-left: 2px;
                background-color: transparent;
            }}
        """
        self.setStyleSheet(style)

    def setTitle(self, text):
        self._label_text = text
        self._label_item.setText(text)
        if not text:
            self.setLabelVisible(False)

    def setLabelVisible(self, visible):
        self._label_item.setVisible(visible)
        # 调整边距：无论是否有标题，都保持底部间距以维持隔离感
        self.layout.setContentsMargins(0, 0, 0, 0)

    def add_node_widget(self, widget):
        """
        核心修改：添加控件时智能判断对齐方式
        """
        # 1. 统一字体
        font_name = self._get_font_family()
        font = widget.font()
        font.setFamily(font_name)
        font.setPointSize(10)
        widget.setFont(font)

        # 2. 注入样式
        self._apply_child_style(widget)

        # 3. 智能布局逻辑
        sp = widget.sizePolicy()
        h_policy = sp.horizontalPolicy()

        # 判断是否为“固定宽度”控件 Fixed: 绝对固定 Maximum: 不能超过某个宽度 (通常意味着不想被拉伸)
        center_policies = [
            QtWidgets.QSizePolicy.Fixed,
            QtWidgets.QSizePolicy.Maximum
        ]

        # 额外检查：有些控件虽然策略是 Preferred，但手动设置了 setFixedWidth
        # 如果 minWidth == maxWidth 且不为 0 或无限大，则认为是固定宽
        is_explicit_fixed = (widget.minimumWidth() == widget.maximumWidth() and
                             0 < widget.minimumWidth() < 16777215)

        if h_policy in center_policies or is_explicit_fixed:
            # 【关键点】如果是固定大小，添加 AlignCenter 标志
            self.layout.addWidget(widget, 0, QtCore.Qt.AlignCenter)
        else:
            # 否则，使用默认行为 (通常是 Fill / Stretch)
            self.layout.addWidget(widget)

    def _apply_child_style(self, widget):
        widget.setAttribute(QtCore.Qt.WA_StyledBackground, True)

    def get_node_widget(self):
        if self.layout.count() > 1:
            return self.layout.itemAt(1).widget()
        return None


class CustomNodeBaseWidget(QtWidgets.QGraphicsProxyWidget):
    """
    包装类保持不变
    """
    value_changed = QtCore.Signal(str, object)

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
        self.value_changed.emit(self.get_name(), self.get_value())

    @property
    def type_(self):
        return str(self.__class__.__name__)

    @property
    def node(self):
        return self._node

    def get_icon(self, name):
        return self.style().standardIcon(QtWidgets.QStyle.StandardPixmap(name))

    def get_name(self):
        return self._name

    def set_name(self, name):
        if not name: return
        if self.node:
            raise NodeWidgetError('Can\'t set property name widget already added to a Node')
        self._name = name

    def get_value(self):
        raise NotImplementedError

    def set_value(self, text):
        raise NotImplementedError

    def get_custom_widget(self):
        widget = self.widget()
        if hasattr(widget, 'get_node_widget'):
            return widget.get_node_widget()
        return widget

    def set_custom_widget(self, widget):
        if self.widget():
            raise NodeWidgetError('Custom node widget already set.')

        group = _NodeGroupBox(self._label)
        group.add_node_widget(widget)
        self.setWidget(group)

    def get_label(self):
        return self._label

    def set_label(self, label=''):
        if self.widget() and hasattr(self.widget(), 'setTitle'):
            self.widget().setTitle(label)
        self._label = label

    def set_label_visible(self, visible=True):
        if self.widget() and hasattr(self.widget(), 'setLabelVisible'):
            self.widget().setLabelVisible(visible)