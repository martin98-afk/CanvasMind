# -*- coding: utf-8 -*-
from Qt import QtWidgets, QtCore
from NodeGraphQt import NodeBaseWidget
from qfluentwidgets import Slider, LineEdit


class RangeWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(object)

    def __init__(self, min_val=0, max_val=100, step=1, default=0, parent=None):
        super().__init__(parent)
        self.min_val = min_val
        self.max_val = max_val
        self.step = step

        # 判断是整数还是浮点
        self.is_float = isinstance(step, float) or isinstance(min_val, float)

        # 滑块（QSlider 只支持整数，所以用缩放）
        self.slider = Slider(QtCore.Qt.Horizontal)
        self.slider.setFixedWidth(200)
        self.slider.setMinimum(0)
        self.slider.setMaximum(int((max_val - min_val) / step))
        self.slider.setSingleStep(1)

        # 数值显示
        self.value_edit = LineEdit()
        self.value_edit.setFixedWidth(60)
        self.value_edit.setAlignment(QtCore.Qt.AlignCenter)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.slider)
        layout.addWidget(self.value_edit)

        # 初始化值
        self.set_value(default)

        # 连接信号
        self.slider.valueChanged.connect(self._on_slider_changed)
        self.value_edit.editingFinished.connect(self._on_text_changed)

    def _on_slider_changed(self, slider_val):
        real_val = self.min_val + slider_val * self.step
        if not self.is_float:
            real_val = int(real_val)
        self.value_edit.setText(f"{real_val:.1f}")
        self.valueChanged.emit(real_val)

    def _on_text_changed(self):
        try:
            text = self.value_edit.text()
            val = float(text) if self.is_float else int(text)
            if val < self.min_val:
                val = self.min_val
            elif val > self.max_val:
                val = self.max_val
            # 对齐步长
            steps = round((val - self.min_val) / self.step)
            val = self.min_val + steps * self.step
            if not self.is_float:
                val = int(val)
            self.value_edit.setText(f"{val:.1f}")
            self.slider.setValue(int((val - self.min_val) / self.step))
            self.valueChanged.emit(val)
        except ValueError:
            self.value_edit.setText(f"{self.min_val:.1f}")

    def set_value(self, value):
        if isinstance(value, str) and len(value) == 0:
            value = self.min_val
        value = float(value) if self.is_float else int(value)
        if value < self.min_val:
            value = self.min_val
        elif value > self.max_val:
            value = self.max_val
        steps = round((value - self.min_val) / self.step)
        real_val = self.min_val + steps * self.step
        if not self.is_float:
            real_val = int(real_val)
        self.value_edit.setText(f"{real_val:.1f}")
        self.slider.setValue(int(steps))

    def get_value(self):
        return float(self.value_edit.text()) if self.is_float else int(self.value_edit.text())


class RangeWidgetWrapper(NodeBaseWidget):
    def __init__(self, parent=None, name="", label="", min_val=0, max_val=100, step=1, default=0):
        super().__init__(parent)
        self.set_name(name)
        self.set_label(label)
        widget = RangeWidget(min_val, max_val, step, default)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)