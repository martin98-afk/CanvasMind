from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from PyQt5.QtCore import pyqtSignal
from Qt import QtWidgets

from app.widgets.basic_widget.switch import ModernSwitch
from app.widgets.node_widget.base import CustomNodeBaseWidget


class CheckBoxWidget(QtWidgets.QWidget):
    """节点内显示：复选框包装容器"""
    valueChanged = pyqtSignal(bool)
    fixed_height = True

    def __init__(self, text="", state=False, parent=None):
        super().__init__(parent)
        self._value = state if isinstance(state, bool) else str(state).lower() in ("true", "1")

        # 现代化文字标签
        self.label = QtWidgets.QLabel(text)
        # 字体可以根据你的 Settings 类调整，这里使用默认系统字体演示
        self.label.setStyleSheet("""
            QLabel {
                color: #BBBBBB; 
                font-family: 'Segoe UI', 'Microsoft YaHei';
                font-size: 13px;
            }
        """)

        # 替换为自定义的原生 ModernSwitch
        self.checkbox = ModernSwitch()
        self.checkbox.setChecked(self._value)
        # 初始化滑块位置，防止初次显示没动画时位置不对
        self.checkbox._handle_position = (self.checkbox.width() - self.checkbox.height() + 2) if self._value else 2

        self.checkbox.stateChanged.connect(self._on_state_changed)

        # 布局调整
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)  # 适当增加边距更有“呼吸感”
        layout.setSpacing(10)
        layout.addWidget(self.label)
        layout.addStretch(1)
        layout.addWidget(self.checkbox)

    def _on_state_changed(self, state):
        # state: 0 (Unchecked), 2 (Checked)
        new_val = state == 2
        if new_val != self._value:
            self._value = new_val
            self.valueChanged.emit(self._value)

    def get_value(self):
        return self._value

    def set_value(self, value):
        if isinstance(value, str):
            value = value.lower() in ("true", "1")

        if value != self._value:
            self._value = value
            self.checkbox.setChecked(value)
            # 手动更新滑块位置（用于非点击触发的状态变更）
            end_pos = self.checkbox.width() - self.checkbox.height() + 2 if value else 2
            self.checkbox.handle_position = end_pos


class CheckBoxWidgetWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", label="", text="", state=False, window=None, z_value=1):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET + z_value)
        self.set_name(name)
        self.set_label(f"{text}({name})")
        widget = CheckBoxWidget(text=f"{text}({name})", state=state, parent=window)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)
        self.set_label_visible(False)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)


