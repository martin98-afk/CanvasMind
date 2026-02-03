# -*- coding: utf-8 -*-
import math
from Qt import QtWidgets, QtCore, QtGui
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET

from app.widgets.basic_widget.style_sheet import StyleSheet
from app.widgets.node_widget.base import CustomNodeBaseWidget


class RangeWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(object)
    fixed_height = True

    def __init__(self, min_val=0, max_val=100, step=1, default=0, parent=None):
        super().__init__(parent)
        # 应用样式
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        StyleSheet.RANGE_WIDGET.apply(self)

        self.min_val = min_val
        self.max_val = max_val
        self.step = step

        # 逻辑处理
        self.is_float = isinstance(step, float) or isinstance(min_val, float) or isinstance(default, float)
        self.decimal_places = 0
        if self.is_float:
            # 自动计算小数位数，防止浮点精度问题显示过长
            str_step = str(step)
            if '.' in str_step:
                self.decimal_places = len(str_step.split('.')[1])
            else:
                self.decimal_places = 2

        # 防抖相关
        self._debounce_timer = QtCore.QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._emit_value_changed)
        self._debounce_delay = 150  # 稍微增加一点延迟，减少高频触发

        # 1. 替换为原生 QSlider
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setMinimum(0)
        # 计算 slider 的总步数
        steps_count = int(round((max_val - min_val) / step))
        self.slider.setMaximum(steps_count)
        self.slider.setSingleStep(1)
        # 滚轮步长优化：按住 Ctrl 滚轮可以微调，否则快调 (可选)
        self.slider.setPageStep(max(1, int(steps_count / 10)))

        # 2. 替换为原生 QLineEdit
        self.value_edit = QtWidgets.QLineEdit()
        self.value_edit.setAlignment(QtCore.Qt.AlignCenter)
        self.value_edit.setMinimumWidth(40)  # 稍微宽一点

        # 布局
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)  # 控件间距，适中即可
        layout.addWidget(self.slider)
        layout.addWidget(self.value_edit)

        # 初始化数据
        self._current_value = default
        self.set_value(default)

        # 信号连接
        self.slider.valueChanged.connect(self._on_slider_changed)
        self.value_edit.editingFinished.connect(self._on_text_changed)

        # 初始宽度适配
        self._update_line_edit_width(default)

    def _update_line_edit_width(self, value):
        """ 根据内容动态调整宽度，增加一点视觉余量 """
        if isinstance(value, (int, float)):
            text = f"{value:.{self.decimal_places}f}"
        else:
            text = str(value)

        font_metrics = self.value_edit.fontMetrics()
        # Advance width + padding (左右各5px + 光标余量)
        width = font_metrics.horizontalAdvance(text) + 20
        self.value_edit.setFixedWidth(max(45, width))

    def _on_slider_changed(self, slider_val):
        """ Slider 拖动处理 """
        # 1. 计算真实值
        real_val = self.min_val + (slider_val * self.step)

        # 2. 格式化
        if not self.is_float:
            real_val = int(round(real_val))
            text_val = str(real_val)
        else:
            text_val = f"{real_val:.{self.decimal_places}f}"

        # 3. 更新 UI (静默更新，不触发 editingFinished)
        self.value_edit.blockSignals(True)
        self.value_edit.setText(text_val)
        self.value_edit.blockSignals(False)

        self._update_line_edit_width(real_val)

        # 4. 记录并防抖触发
        self._current_value = real_val
        self._debounce_timer.start(self._debounce_delay)

    def _on_text_changed(self):
        """ 文本框输入完成处理 """
        text = self.value_edit.text().strip()
        if not text:
            return

        try:
            val = float(text)

            # 范围限制
            if val < self.min_val: val = self.min_val
            if val > self.max_val: val = self.max_val

            # 步长对齐 (Snap to step)
            # 公式: min + round((val - min) / step) * step
            steps = round((val - self.min_val) / self.step)
            val = self.min_val + (steps * self.step)

            # 类型转换
            if not self.is_float:
                val = int(round(val))

            self._current_value = val

            # 反向更新 Slider
            slider_pos = int(steps)
            self.slider.blockSignals(True)  # 防止循环触发
            self.slider.setValue(slider_pos)
            self.slider.blockSignals(False)

            # 格式化回显
            new_text = f"{val:.{self.decimal_places}f}" if self.is_float else str(val)
            self.value_edit.setText(new_text)
            self._update_line_edit_width(val)

            # 立即触发信号 (文本输入通常不需要防抖)
            self.valueChanged.emit(val)

        except ValueError:
            # 输入非法时回滚
            self.set_value(self._current_value)

    def _emit_value_changed(self):
        self.valueChanged.emit(self._current_value)

    def set_value(self, value):
        """ 外部设置值 """
        try:
            value = float(value)
        except (ValueError, TypeError):
            value = self.min_val

        # 范围限制
        if value < self.min_val: value = self.min_val
        if value > self.max_val: value = self.max_val

        # 计算 Slider 位置
        steps = round((value - self.min_val) / self.step)
        real_val = self.min_val + (steps * self.step)

        if not self.is_float:
            real_val = int(round(real_val))

        self._current_value = real_val

        # 更新 UI
        self.slider.blockSignals(True)
        self.slider.setValue(int(steps))
        self.slider.blockSignals(False)

        text_val = f"{real_val:.{self.decimal_places}f}" if self.is_float else str(real_val)
        self.value_edit.setText(text_val)
        self._update_line_edit_width(real_val)

    def get_value(self):
        return self._current_value


class RangeWidgetWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", label="", min_val=0, max_val=100, step=1, default=0, window=None,
                 z_value=1):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET + z_value)

        # 这里的 Label 也可以做一些样式优化，不过 NodeGraphQt 通常有自己的 label 处理
        self.set_name(name)
        self.set_label(f"{label}({name})")

        widget = RangeWidget(min_val, max_val, step, default, window)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)