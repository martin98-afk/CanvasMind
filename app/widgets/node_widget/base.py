from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from NodeGraphQt.errors import NodeWidgetError
from PyQt5 import QtGui
from loguru import logger
from qtpy import QtWidgets, QtCore

from app.components.base import GlobalVariableContext
from app.utils.config import Settings


class _NodeGroupBox(QtWidgets.QWidget):
    """
    自定义控件容器 - 支持标题栏小圆点切换
    """
    toggle_clicked = QtCore.Signal()

    def __init__(self, label, parent=None):
        super(_NodeGroupBox, self).__init__(parent)
        self._highlight = False
        self._label_text = label

        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 8)
        self.layout.setSpacing(1)

        self.header_layout = QtWidgets.QHBoxLayout()
        self.header_layout.setContentsMargins(0, 0, 2, 0)

        self._label_item = QtWidgets.QLabel(label)
        self._label_item.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        self.dot_btn = QtWidgets.QToolButton()
        self.dot_btn.setFixedSize(10, 10)
        self.dot_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.dot_btn.setToolTip("切换 本地输入 / 全局变量")
        self.dot_btn.clicked.connect(self.toggle_clicked.emit)

        self.header_layout.addWidget(self._label_item)
        self.header_layout.addStretch()
        self.header_layout.addWidget(self.dot_btn)

        self.layout.addLayout(self.header_layout)

        self._set_dot_style(False)
        self._update_font()
        self._apply_style()

    def _set_dot_style(self, is_global):
        color = "#00E5FF" if is_global else "#555555"
        self.dot_btn.setStyleSheet(f"""
            QToolButton {{
                background-color: {color};
                border-radius: 5px;
                border: 1px solid rgba(255,255,255,30);
            }}
            QToolButton:hover {{ background-color: white; }}
        """)

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
            QWidget {{ font-family: "{self._get_font_family()}"; background-color: transparent; }}
            QLabel {{ color: {label_color}; border: none; padding-left: 2px; background-color: transparent; }}
        """
        self.setStyleSheet(style)

    def setTitle(self, text):
        self._label_text = text
        self._label_item.setText(text)
        if not text:
            self.setLabelVisible(False)

    def setLabelVisible(self, visible):
        self._label_item.setVisible(visible)
        self.layout.setContentsMargins(0, 0, 0, 0)

    def _apply_unified_font(self, widget):
        font_name = self._get_font_family()
        font = widget.font()
        font.setFamily(font_name)
        widget.setFont(font)
        for child in widget.findChildren(QtWidgets.QWidget):
            child_font = child.font()
            child_font.setFamily(font_name)
            child.setFont(child_font)

    def add_node_widget(self, widget):
        self._apply_unified_font(widget)
        sp = widget.sizePolicy()
        h_policy = sp.horizontalPolicy()
        if hasattr(widget, "fixed_height") and widget.fixed_height:
            widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            stretch = 0
        else:
            widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            stretch = 1

        is_explicit_fixed = (widget.minimumWidth() == widget.maximumWidth() and 0 < widget.minimumWidth() < 16777215)
        if h_policy in [QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Maximum] or is_explicit_fixed:
            self.layout.addWidget(widget, 0, QtCore.Qt.AlignCenter)
        else:
            self.layout.addWidget(widget, stretch)

    def get_node_widget(self):
        if self.layout.count() > 1:
            item = self.layout.itemAt(1)
            return item.widget() if item else None
        return None

    def toggle_highlight(self):
        if self._highlight:
            self.reset()
        else:
            self.highlight()
        self._highlight = not self._highlight

    def paintEvent(self, event):
        opt = QtWidgets.QStyleOption()
        opt.initFrom(self)
        p = QtGui.QPainter(self)
        self.style().drawPrimitive(QtWidgets.QStyle.PE_Widget, opt, p, self)
        super().paintEvent(event)

    def highlight(self):
        # 使用 ID 选择器或类名选择器包裹属性
        # 注意：这里我们给 self 设置一个 objectName 确保选择器精准
        self.setObjectName("highlighted_group")
        style = self.styleSheet() + """
            #highlighted_group { 
                border: 2px dashed #00E5FF; 
                border-radius: 5px; 
            }
        """
        self.setStyleSheet(style)

    def reset(self):
        # 还原样式，移除 objectName 或重新调用 _apply_style
        self.setObjectName("")
        self._apply_style()


class CustomNodeBaseWidget(QtWidgets.QGraphicsProxyWidget):
    """
    支持状态显示与全局变量切换的基类控件
    """
    value_changed = QtCore.Signal(str, object)
    VAR_WIDGET_CLASS = None

    def __init__(self, parent=None, name=None, label=''):
        super(CustomNodeBaseWidget, self).__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET)
        self._name = name
        self._label = label
        self._node = None
        self.label_visible = True
        self._local_widget = None
        self._global_widget = None
        self._is_using_global = False

    @property
    def node(self):
        return self._node

    @node.setter
    def node(self, node):
        self._node = node

    def toggle_global_mode(self):
        group = self.widget()
        if not group: return
        # 检查是否是参数类控件，展示类控件不需要替换
        if not hasattr(self.get_custom_widget(), "main_window"): return
        # 检查槽位是否已经注入了类
        if self.VAR_WIDGET_CLASS is None:
            logger.error("VarComboBoxWidget class not registered in CustomNodeBaseWidget")
            return

        self._is_using_global = not self._is_using_global

        if self._is_using_global:
            if not self._global_widget:
                # 使用注入的类创建实例
                self._global_widget = self.VAR_WIDGET_CLASS(
                    main_window=self.get_custom_widget().main_window, type="全局变量"
                )
                # self._global_widget.setZValue(Z_VAL_NODE_WIDGET + 10)
                self._global_widget.valueChanged.connect(self.on_value_changed)

            self._local_widget.hide()
            group.layout.replaceWidget(self._local_widget, self._global_widget)
            self._global_widget.show()
            group._set_dot_style(True)
            if not self.label_visible:
                self.widget().setLabelVisible(True)
        else:
            if self._global_widget:
                self._global_widget.hide()
                group.layout.replaceWidget(self._global_widget, self._local_widget)
            self._local_widget.show()
            group._set_dot_style(False)
            if not self.label_visible:
                self.widget().setLabelVisible(False)

        self.on_value_changed()

    def get_value(self):
        if self._is_using_global and self._global_widget:
            return self._global_widget.get_value()

        return self._get_local_value()

    def set_value(self, value):
        if isinstance(value, str) and GlobalVariableContext.is_variable_name(value):
            if not self._is_using_global:
                self.toggle_global_mode()
            self._global_widget.set_value(value)
        else:
            if self._is_using_global:
                self.toggle_global_mode()
            self._set_local_value(value)

    def _get_local_value(self):
        raise NotImplementedError

    def _set_local_value(self, value):
        raise NotImplementedError

    def set_custom_widget(self, widget):
        if self.widget():
            raise NodeWidgetError('Custom node widget already set.')
        self._local_widget = widget
        group = _NodeGroupBox(self._label)
        group.toggle_clicked.connect(self.toggle_global_mode)
        group.add_node_widget(widget)
        self.setWidget(group)

    def on_value_changed(self, *args, **kwargs):
        self.value_changed.emit(self.get_name(), self.get_value())

    def get_name(self):
        return self._name

    def set_name(self, name):
        if not name: return
        if self.node:
            raise NodeWidgetError('Can\'t set property name widget already added to a Node')
        self._name = name

    def get_custom_widget(self):
        widget = self.widget()
        if hasattr(widget, 'get_node_widget'):
            return widget.get_node_widget()
        return widget

    def set_label(self, label=''):
        if self.widget() and hasattr(self.widget(), 'setTitle'):
            self.widget().setTitle(label)
        self._label = label

    def set_label_visible(self, visible=True):
        if self.widget() and hasattr(self.widget(), 'setLabelVisible'):
            self.label_visible = visible
            self.widget().setLabelVisible(visible)