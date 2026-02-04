from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from NodeGraphQt.errors import NodeWidgetError
from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtCore import pyqtSignal
from loguru import logger

from app.components.base import GlobalVariableContext
from app.utils.config import Settings


class ModeSwitcherButton(QtWidgets.QAbstractButton):
    """
    现代风格状态切换按钮
    特点：
    1. 圆形悬浮背景 (Ripple Effect 视觉替代)。
    2. 悬浮时图标有动态变化（变亮/变粗/填充）。
    3. 视觉层级清晰：空心=本地，实心发光=全局。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(22, 22)  # 稍微加大一点尺寸，容纳光晕
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setToolTip("切换输入模式：\n• 空心：本地输入\n• 实心：全局变量")

        # 颜色配置
        self._color_local = QtGui.QColor("#888888")  # 平态：灰色
        self._color_local_hover = QtGui.QColor("#FFFFFF")  # 悬浮：亮白

        self._color_global = QtGui.QColor("#00E5FF")  # 平态：青色
        self._color_global_hover = QtGui.QColor("#80F3FF")  # 悬浮：亮青色

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

        # --- 1. 绘制背景 (圆形光晕) ---
        if self._is_hovered:
            # 根据当前模式决定背景色调，增强关联感
            if self._is_global:
                bg_color = QtGui.QColor(0, 229, 255, 30)  # 青色淡光晕
            else:
                bg_color = QtGui.QColor(255, 255, 255, 30)  # 白色淡光晕

            painter.setBrush(bg_color)
            painter.setPen(QtCore.Qt.NoPen)
            # 绘制一个完美的圆作为背景，而不是圆角矩形
            bg_radius = 10.0
            painter.drawEllipse(center, bg_radius, bg_radius)

        # --- 2. 绘制前景 (图标) ---
        icon_radius = 4.0

        if self._is_global:
            # === 全局模式：实心发光点 ===

            # A. 外部辉光 (Glow)
            glow_opacity = 100 if not self._is_hovered else 150
            glow_size = 1.5 if not self._is_hovered else 2.5  # 悬浮时辉光变大

            glow_color = QtGui.QColor(self._color_global)
            glow_color.setAlpha(glow_opacity)

            painter.setBrush(QtCore.Qt.NoBrush)
            glow_pen = QtGui.QPen(glow_color)
            glow_pen.setWidthF(glow_size)
            painter.setPen(glow_pen)
            painter.drawEllipse(center, icon_radius + 0.5, icon_radius + 0.5)

            # B. 内部实心点
            core_color = self._color_global_hover if self._is_hovered else self._color_global
            painter.setBrush(core_color)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawEllipse(center, icon_radius, icon_radius)

        else:
            # === 本地模式：空心圆环 ===

            pen_color = self._color_local_hover if self._is_hovered else self._color_local
            pen_width = 1.8 if self._is_hovered else 1.2  # 悬浮时线条变粗

            painter.setPen(QtGui.QPen(pen_color, pen_width))

            if self._is_hovered:
                # 悬浮时，内部稍微填充一点点颜色，增加实体感
                fill_color = QtGui.QColor(255, 255, 255, 20)
                painter.setBrush(fill_color)
            else:
                painter.setBrush(QtCore.Qt.NoBrush)

            painter.drawEllipse(center, icon_radius, icon_radius)

            # 绘制中心微点 (让空心不那么单调，更有靶心的感觉)
            # 悬浮时这个点也变亮
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(pen_color)
            dot_size = 0.8 if self._is_hovered else 0.5
            painter.drawEllipse(center, dot_size, dot_size)


class _NodeGroupBox(QtWidgets.QWidget):
    """
    自定义控件容器 - 支持标题栏小圆点切换
    """
    toggle_clicked = pyqtSignal()

    def __init__(self, label, parent=None):
        super(_NodeGroupBox, self).__init__(parent)
        self._highlight = False
        self._label_text = label

        # 主布局
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 8)
        self.layout.setSpacing(1)

        # 标题栏布局
        self.header_layout = QtWidgets.QHBoxLayout()
        self.header_layout.setContentsMargins(0, 0, 2, 0)

        # 标题文本
        self._label_item = QtWidgets.QLabel(label)
        self._label_item.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        # 【优化点】使用自定义的高性能绘制按钮
        self.dot_btn = ModeSwitcherButton()
        self.dot_btn.clicked.connect(self.toggle_clicked.emit)

        self.header_layout.addWidget(self._label_item)
        self.header_layout.addStretch()
        self.header_layout.addWidget(self.dot_btn)

        self.layout.addLayout(self.header_layout)

        self._update_font()
        self._apply_style()

    def _set_dot_style(self, is_global):
        # 【优化点】直接调用方法更新绘制状态，不再注入 CSS
        self.dot_btn.set_mode(is_global)

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
        # 调整边距以适应隐藏标题的情况
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
        self.setObjectName("highlighted_group")
        style = self.styleSheet() + """
            #highlighted_group { 
                border: 2px dashed #00E5FF; 
                border-radius: 5px; 
            }
        """
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

    def setToolTip(self, tooltip):
        tooltip = tooltip.replace('\n', '<br/>')
        tooltip = '<b>{}</b><br/>{}'.format(self.get_name(), tooltip)
        super(CustomNodeBaseWidget, self).setToolTip(tooltip)

    def toggle_global_mode(self, mode=None):
        group = self.widget()
        if not group: return
        # 检查是否是参数类控件，展示类控件不需要替换
        if not hasattr(self.get_custom_widget(), "main_window"): return
        # 检查槽位是否已经注入了类
        if self.VAR_WIDGET_CLASS is None:
            logger.error("VarComboBoxWidget class not registered in CustomNodeBaseWidget")
            return

        self._is_using_global = mode or not self._is_using_global

        if self._is_using_global:
            if not self._global_widget:
                # 使用注入的类创建实例
                self._global_widget = self.VAR_WIDGET_CLASS(
                    main_window=self.get_custom_widget().main_window, type="全局变量"
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
        if GlobalVariableContext.is_variable_name(value):
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
        if self.node and self._name in self.node.model.properties.keys():
            self._name = f"_{self._name}"
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

    def get_port_func(self):
        vars = [f"input.{port.name()}" for port in self.node.input_ports()]
        for port in self.node.input_ports():
            connected_ports = port.connected_ports()
            for connected_port in connected_ports:
                safe_name = connected_port.node().name().replace(" ", "_")
                vars.append(f"input.{safe_name}__{connected_port.name()}")

        return vars