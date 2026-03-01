from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from NodeGraphQt.errors import NodeWidgetError
from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtCore import pyqtSignal
from loguru import logger

from app.components.base import GlobalVariableContext
from app.utils.config import Settings


class ModeSwitcherButton(QtWidgets.QAbstractButton):
    """
    现代风格状态切换按钮 (保持原样)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(22, 22)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setToolTip("切换输入模式：\n• 空心：本地输入\n• 实心：全局变量")

        self._color_local = QtGui.QColor("#888888")
        self._color_local_hover = QtGui.QColor("#FFFFFF")
        self._color_global = QtGui.QColor("#00E5FF")
        self._color_global_hover = QtGui.QColor("#80F3FF")

        self._is_global = False
        self._is_hovered = False

    def set_mode(self, is_global):
        if self._is_global != is_global:
            self._is_global = is_global
            self.setChecked(is_global)
            self.update()

    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        rect = self.rect()
        center = QtCore.QPointF(rect.center())

        if self._is_hovered:
            if self._is_global:
                bg_color = QtGui.QColor(0, 229, 255, 30)
            else:
                bg_color = QtGui.QColor(255, 255, 255, 30)
            painter.setBrush(bg_color)
            painter.setPen(QtCore.Qt.NoPen)
            bg_radius = 10.0
            painter.drawEllipse(center, bg_radius, bg_radius)

        icon_radius = 4.0

        if self._is_global:
            glow_opacity = 100 if not self._is_hovered else 150
            glow_size = 1.5 if not self._is_hovered else 2.5
            glow_color = QtGui.QColor(self._color_global)
            glow_color.setAlpha(glow_opacity)
            painter.setBrush(QtCore.Qt.NoBrush)
            glow_pen = QtGui.QPen(glow_color)
            glow_pen.setWidthF(glow_size)
            painter.setPen(glow_pen)
            painter.drawEllipse(center, icon_radius + 0.5, icon_radius + 0.5)

            core_color = (
                self._color_global_hover if self._is_hovered else self._color_global
            )
            painter.setBrush(core_color)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawEllipse(center, icon_radius, icon_radius)
        else:
            pen_color = (
                self._color_local_hover if self._is_hovered else self._color_local
            )
            pen_width = 1.8 if self._is_hovered else 1.2
            painter.setPen(QtGui.QPen(pen_color, pen_width))
            if self._is_hovered:
                fill_color = QtGui.QColor(255, 255, 255, 20)
                painter.setBrush(fill_color)
            else:
                painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawEllipse(center, icon_radius, icon_radius)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(pen_color)
            dot_size = 0.8 if self._is_hovered else 0.5
            painter.drawEllipse(center, dot_size, dot_size)


class _NodeGroupBox(QtWidgets.QWidget):
    """
    自定义控件容器 - 布局优化版
    """

    toggle_clicked = pyqtSignal()

    def __init__(self, label, parent=None):
        super(_NodeGroupBox, self).__init__(parent)
        self._highlight = False
        self._label_text = label
        self._font_family = None

        # === 1. 主垂直布局 (用于放置原来的大控件 或 全局变量控件) ===
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 8)
        self.layout.setSpacing(1)

        # === 2. 标题栏水平布局 ===
        self.header_layout = QtWidgets.QHBoxLayout()
        self.header_layout.setContentsMargins(0, 0, 2, 0)
        self.header_layout.setSpacing(4)

        # 标题文本
        self._label_item = QtWidgets.QLabel(label)
        self._label_item.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        # 模式切换按钮
        self.dot_btn = ModeSwitcherButton()
        self.dot_btn.clicked.connect(self.toggle_clicked.emit)

        # 组装 Header: [Label] -> [Stretch] -> [DotBtn]
        # 注意：如果有 add_on_label 的控件，会插入到 Stretch 和 DotBtn 之间
        self.header_layout.addWidget(self._label_item)
        self.header_layout.addStretch()  # Index 1
        self.header_layout.addWidget(self.dot_btn)  # Index 2

        self.layout.addLayout(self.header_layout)

        self._update_font()
        self._apply_style()

    def _set_dot_style(self, is_global):
        self.dot_btn.set_mode(is_global)

    def _get_font_family(self):
        try:
            return Settings.get_instance().canvas_font_type.value
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
            # 这里如果不希望完全隐藏标题行（因为可能还有按钮），可以只隐藏Label
            self._label_item.setVisible(False)
        else:
            self._label_item.setVisible(True)

    def setLabelVisible(self, visible):
        # 仅控制文字显示，不应该隐藏整个 GroupBox 导致布局塌陷
        self._label_item.setVisible(visible)
        # 如果是隐藏 Label，调整一下边距使其紧凑
        if visible:
            self.layout.setContentsMargins(0, 0, 0, 8)
        else:
            self.layout.setContentsMargins(0, 0, 0, 0)

    def _apply_unified_font(self, widget):
        font_name = self._get_font_family()
        font = widget.font()
        font.setFamily(font_name)
        widget.setFont(font)
        for child in widget.findChildren(QtWidgets.QWidget):
            child_font = child.font()
            child_font.setFamily(font_name)
            child_font.setPointSize(10)
            child_font.setBold(True)
            child.setFont(child_font)

    def add_node_widget(self, widget, add_on_label=False):
        """
        :param widget: 待添加的控件
        :param add_on_label: 是否添加到标题栏右侧
        """
        self._apply_unified_font(widget)

        if add_on_label:
            # === 添加到标题栏 (Label右侧对齐) ===
            # header 结构: 0:Label, 1:Stretch, 2:Button
            # 插入到 Stretch(1) 之后，Button 之前。所以 Insert Index = 2
            self.header_layout.insertWidget(2, widget)
        else:
            # === 添加到常规位置 (第二行) ===
            sp = widget.sizePolicy()
            h_policy = sp.horizontalPolicy()
            if hasattr(widget, "fixed_height") and widget.fixed_height:
                widget.setSizePolicy(
                    QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
                )
                stretch = 0
            else:
                widget.setSizePolicy(
                    QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
                )
                stretch = 1

            is_explicit_fixed = (
                widget.minimumWidth() == widget.maximumWidth()
                and 0 < widget.minimumWidth() < 16777215
            )
            if (
                h_policy in [QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Maximum]
                or is_explicit_fixed
            ):
                self.layout.addWidget(widget, 0, QtCore.Qt.AlignCenter)
            else:
                self.layout.addWidget(widget, stretch)

    def add_global_widget(self, widget):
        """专门添加全局变量控件，强制添加到垂直布局底部"""
        self._apply_unified_font(widget)

        widget.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self.layout.addWidget(widget, 0)
        # self.layout.addWidget(widget, 0, QtCore.Qt.AlignCenter)

    def get_node_widget(self):
        # 1. 优先查找 Header 中的自定义控件
        # Index: 0=Label, 1=Stretch, 2=Widget(可能), 3=Button
        if self.header_layout.count() > 3:
            item = self.header_layout.itemAt(2)
            w = item.widget()
            if w and w != self.dot_btn:
                return w

        # 2. 查找 Body 中的控件
        # Body Index 0 是 HeaderLayout，Index 1 是 Widget
        if self.layout.count() > 1:
            item = self.layout.itemAt(1)
            # 确保拿到的不是 HeaderLayout
            if item.widget():
                return item.widget()
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
        self.setObjectName("highlighted_group")
        style = (
            self.styleSheet()
            + """
            #highlighted_group { 
                border: 2px dashed #00E5FF; 
                border-radius: 5px; 
            }
        """
        )
        self.setStyleSheet(style)

    def reset(self):
        self.setObjectName("")
        self._apply_style()


class CustomNodeBaseWidget(QtWidgets.QGraphicsProxyWidget):
    """
    支持状态显示与全局变量切换的基类控件
    """

    value_changed = pyqtSignal(str, object)
    VAR_WIDGET_CLASS = None

    def __init__(self, parent=None, name=None, label=""):
        super(CustomNodeBaseWidget, self).__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET)
        self._name = name
        self._label = label
        self._node = None
        self._widget_on_label = False
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

    def setToolTip(self, tooltip):
        tooltip = tooltip.replace("\n", "<br/>")
        tooltip = "<b>{}</b><br/>{}".format(self.get_name(), tooltip)
        super(CustomNodeBaseWidget, self).setToolTip(tooltip)

    def toggle_global_mode(self, mode=None):
        """
        切换本地/全局模式
        优化逻辑：使用 Hide/Show 而不是 ReplaceWidget，确保在不同布局位置下都能正常工作，并保持对象引用。
        """
        group = self.widget()  # type: _NodeGroupBox
        if not group:
            return

        # 检查是否是参数类控件
        if not hasattr(self.get_custom_widget(), "main_window"):
            return
        # 检查槽位是否已经注入了类
        if self.VAR_WIDGET_CLASS is None:
            logger.error(
                "VarComboBoxWidget class not registered in CustomNodeBaseWidget"
            )
            return

        # 确定目标模式
        target_mode = mode if mode is not None else not self._is_using_global
        self._is_using_global = target_mode

        if self._widget_on_label:
            if self._is_using_global:
                # === 开启全局模式 ===

                # 1. 隐藏本地控件 (无论它在标题栏还是第二行)
                if self._local_widget:
                    self._local_widget.setVisible(False)

                # 2. 确保全局控件存在并添加到第二行
                if not self._global_widget:
                    self._global_widget = self.VAR_WIDGET_CLASS(
                        main_window=self.get_custom_widget().main_window,
                        type="全局变量",
                    )
                    self._global_widget.valueChanged.connect(self.on_value_changed)
                    # 使用专门的方法添加到第二行
                    group.add_global_widget(self._global_widget)

                # 3. 显示全局控件
                self._global_widget.setVisible(True)
                group._set_dot_style(True)
                # 全局模式下通常需要显示 Label 以便对齐
                if not self.label_visible:
                    self.widget().setLabelVisible(True)

            else:
                # === 开启本地模式 ===
                # 1. 隐藏全局控件
                if self._global_widget:
                    self._global_widget.setVisible(False)
                # 2. 显示本地控件
                if self._local_widget:
                    self._local_widget.setVisible(True)
                group._set_dot_style(False)
                # 恢复 Label 状态
                if not self.label_visible:
                    self.widget().setLabelVisible(False)

            # 触发值变更信号
            self.node.view._draw_node_horizontal()
        else:
            if self._is_using_global:
                if not self._global_widget:
                    # 使用注入的类创建实例
                    self._global_widget = self.VAR_WIDGET_CLASS(
                        main_window=self.get_custom_widget().main_window,
                        type="全局变量",
                    )
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
        # 外部设置值时的自动切换逻辑
        if GlobalVariableContext.is_variable_name(value):
            if not self._is_using_global:
                self.toggle_global_mode(True)  # 强制切到全局
            self._global_widget.set_value(value)
        else:
            if self._is_using_global:
                self.toggle_global_mode(False)  # 强制切回本地
            self._set_local_value(value)

    def _get_local_value(self):
        raise NotImplementedError

    def _set_local_value(self, value):
        raise NotImplementedError

    def set_custom_widget(self, widget, add_on_label=False):
        """
        设置自定义控件
        :param widget: 你的控件 (比如 CheckBox)
        :param add_on_label: True 表示放在标题栏右侧，False 表示放在第二行
        """
        if self.widget():
            raise NodeWidgetError("Custom node widget already set.")

        self._local_widget = widget

        group = _NodeGroupBox(self._label)
        group.toggle_clicked.connect(self.toggle_global_mode)

        # 传递位置参数给 GroupBox
        group.add_node_widget(widget, add_on_label=add_on_label)
        self._widget_on_label = add_on_label
        self.setWidget(group)

    def on_value_changed(self, *args, **kwargs):
        self.value_changed.emit(self.get_name(), self.get_value())

    def get_name(self):
        if self.node and self._name in self.node.model.properties.keys():
            self._name = f"_{self._name}"
        return self._name

    def set_name(self, name):
        if not name:
            return
        if self.node:
            raise NodeWidgetError(
                "Can't set property name widget already added to a Node"
            )
        self._name = name

    def get_custom_widget(self):
        widget = self.widget()
        if hasattr(widget, "get_node_widget"):
            return widget.get_node_widget()
        return widget

    def set_label(self, label=""):
        if self.widget() and hasattr(self.widget(), "setTitle"):
            self.widget().setTitle(label)
        self._label = label

    def set_label_visible(self, visible=True):
        if self.widget() and hasattr(self.widget(), "setLabelVisible"):
            self.label_visible = visible
            self.widget().setLabelVisible(visible)

    def get_port_func(self):
        vars = [f"input.{port.name()}" for port in self.node.input_ports()]
        for port in self.node.input_ports():
            connected_ports = port.connected_ports()
            for connected_port in connected_ports:
                safe_name = connected_port.node().name().replace(" ", "_")
                vars.append(f"input.{safe_name}__{connected_port.name()}")

        return vars
