# -*- coding: utf-8 -*-
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont
from Qt import QtWidgets, QtCore


class ModernSpinButton(QtWidgets.QPushButton):
    """自定义高颜值功能按钮"""

    def __init__(self, text, position="mid", parent=None):
        super().__init__(text, parent)
        self.setFixedSize(28, 28)
        self.position = position  # left, right
        self._setup_style()

    def _setup_style(self):
        # 按钮圆角逻辑：左按钮左圆角，右按钮右圆角
        radius = "4px"
        border_radius = f"border-top-left-radius: {radius}; border-bottom-left-radius: {radius};" if self.position == "left" else \
            f"border-top-right-radius: {radius}; border-bottom-right-radius: {radius};"

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: #383838;
                color: #B0B0B0;
                border: 1px solid #1A1A1A;
                font-size: 16px;
                font-weight: light;
                {border_radius}
            }}
            QPushButton:hover {{
                background-color: #454545;
                color: #00A3FF;
                border: 1px solid #333333;
            }}
            QPushButton:pressed {{
                background-color: #222222;
                color: #007ACC;
            }}
        """)


class ProfessionalSpinBox(QtWidgets.QWidget):
    """
    工业级美化数值控件
    [ — ]  120.00  [ + ]
    """
    valueChanged = pyqtSignal(object)

    def __init__(self, value=0, step=1, decimals=2, is_int=False, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self._value = value
        self._step = step
        self._decimals = decimals
        self._is_int = is_int

        # 步进加速逻辑
        self._timer = QTimer()
        self._timer.timeout.connect(self._on_timer_tick)
        self._current_direction = 0
        self._accel_factor = 1.0

        self._setup_ui()

    def _setup_ui(self):
        self.main_layout = QtWidgets.QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 1. 减少按钮 (使用 Unicode 细线符号)
        self.btn_minus = ModernSpinButton("−", position="left")
        self.btn_minus.pressed.connect(lambda: self._start_auto_change(-1))
        self.btn_minus.released.connect(self._stop_auto_change)

        # 2. 数值输入框
        self.edit = QtWidgets.QLineEdit(str(self._format_value(self._value)))
        self.edit.setAlignment(Qt.AlignCenter)
        self.edit.setFixedHeight(28)
        # 使用等宽字体，防止数值跳动时字符闪烁
        font = QFont("Consolas", 10) if sys.platform == "win32" else QFont("Monaco", 10)
        self.edit.setFont(font)
        self.edit.setStyleSheet("""
            QLineEdit {
                background-color: #252525;
                color: #E0E0E0;
                border-top: 1px solid #1A1A1A;
                border-bottom: 1px solid #1A1A1A;
                border-left: none;
                border-right: none;
                padding: 0 5px;
                selection-background-color: #007ACC;
            }
            QLineEdit:focus {
                color: #FFFFFF;
                background-color: #1E1E1E;
            }
        """)
        self.edit.editingFinished.connect(self._on_text_edited)

        # 3. 增加按钮
        self.btn_plus = ModernSpinButton("+", position="right")
        self.btn_plus.pressed.connect(lambda: self._start_auto_change(1))
        self.btn_plus.released.connect(self._stop_auto_change)

        self.main_layout.addWidget(self.btn_minus)
        self.main_layout.addWidget(self.edit)
        self.main_layout.addWidget(self.btn_plus)

        # 整体容器外边框效果
        self.setAttribute(Qt.WA_StyledBackground)
        self.container_active = False

    def _format_value(self, val):
        if self._is_int:
            return int(val)
        return round(float(val), self._decimals)

    def set_value(self, val):
        val = self._format_value(val)
        if self._value != val:
            self._value = val
            self.edit.setText(str(val))
            self.valueChanged.emit(val)

    # --- 智能步进逻辑 ---

    def _start_auto_change(self, direction):
        self._current_direction = direction
        self._accel_factor = 1.0
        self._do_step()
        self._timer.start(300)  # 初始延迟

    def _stop_auto_change(self):
        self._timer.stop()

    def _on_timer_tick(self):
        # 加速算法：长按时间越长，步进速度越快
        self._timer.start(max(10, int(50 / self._accel_factor)))
        self._accel_factor += 0.2
        self._do_step()

    def _do_step(self):
        # 根据加速因子动态调整步长
        actual_step = self._step * (int(self._accel_factor) if self._accel_factor > 2 else 1)
        self.set_value(self._value + (self._current_direction * actual_step))

    def _on_text_edited(self):
        try:
            # 支持科学计数法输入
            raw_text = self.edit.text().replace(',', '')
            new_val = float(raw_text)
            self.set_value(new_val)
        except ValueError:
            self.edit.setText(str(self._value))

    def wheelEvent(self, event):
        if self.edit.hasFocus() or self.underMouse():
            delta = event.angleDelta().y()
            direction = 1 if delta > 0 else -1
            # 滚轮支持 Shift 加速
            mod = QtWidgets.QApplication.keyboardModifiers()
            mult = 10 if mod == Qt.ControlModifier else (0.1 if mod == Qt.ShiftModifier else 1)
            self.set_value(self._value + (direction * self._step * mult))
            event.accept()


# --- NodeGraphQt 适配 ---

import sys
from app.widgets.node_widget.base import CustomNodeBaseWidget


class SpinBoxWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(object)
    fixed_height = True

    def __init__(self, parent=None, default=0, type="float"):
        super().__init__(parent)
        self.main_window = parent
        is_int = (type == "int")
        # 初始步长设置
        step = 1 if is_int else 0.1

        self.spinbox = ProfessionalSpinBox(
            value=default,
            step=step,
            is_int=is_int,
            decimals=3,
            parent=self
        )
        self.spinbox.valueChanged.connect(self.valueChanged.emit)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.spinbox)

    def get_value(self):
        return self.spinbox._value

    def set_value(self, value):
        self.spinbox.set_value(value)


class NumberWidgetWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", label="", default=0, type="float", window=None, z_value=Z_VAL_NODE_WIDGET):
        super().__init__(parent)
        self.setZValue(z_value)
        self.set_name(name)
        self.set_label(f"{label}({name})")
        self.type = type

        # --- 修复方案：不要赋值给 self.widget，使用局部变量 ---
        inner_widget = SpinBoxWidget(default=default, parent=window, type=type)
        self.set_custom_widget(inner_widget, add_on_label=True)

        # 连接信号
        inner_widget.valueChanged.connect(self.on_value_changed)

    def _get_local_value(self):
        # 使用基类提供的 get_custom_widget() 方法安全获取对象
        widget = self.get_custom_widget()
        if widget:
            return widget.get_value()
        return 0

    def _set_local_value(self, value):
        widget = self.get_custom_widget()
        if widget:
            try:
                v = float(value) if self.type == "float" else int(float(value))
                widget.set_value(v)
            except (ValueError, TypeError):
                pass