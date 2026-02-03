from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt, pyqtProperty, QPropertyAnimation, QEasingCurve, QRectF, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QBrush


class ModernSwitch(QtWidgets.QAbstractButton):
    """
    高级感动态开关
    1. 模拟 QCheckBox 的 stateChanged 信号
    2. 增加背景色平滑过渡动画
    3. 修复全区域点击响应
    """
    # 模拟原生 QCheckBox 的信号
    stateChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(46, 24)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)

        # 内部状态变量
        self._handle_position = 3
        # 背景颜色过渡属性：0 为关闭色，1 为开启色
        self._color_anim_progress = 0.0

        # 颜色定义
        self._color_off_bg = QColor("#3E3E42")  # 深色背景
        self._color_on_bg = QColor("#0078D4")  # 科技蓝
        self._color_handle = QColor("#FFFFFF")  # 白色滑块

        # 1. 滑块位置动画
        self.pos_anim = QPropertyAnimation(self, b"handle_position", self)
        self.pos_anim.setDuration(250)
        self.pos_anim.setEasingCurve(QEasingCurve.OutCubic)

        # 2. 颜色渐变动画
        self.color_anim = QPropertyAnimation(self, b"color_progress", self)
        self.color_anim.setDuration(250)

    # --- 动画属性定义 ---
    @pyqtProperty(float)
    def handle_position(self):
        return self._handle_position

    @handle_position.setter
    def handle_position(self, pos):
        self._handle_position = pos
        self.update()

    @pyqtProperty(float)
    def color_progress(self):
        return self._color_anim_progress

    @color_progress.setter
    def color_progress(self, val):
        self._color_anim_progress = val
        self.update()

    # --- 逻辑重写 ---
    def nextCheckState(self):
        super().nextCheckState()
        self._update_ui(True)
        # 发送模拟信号：2 代表 Checked, 0 代表 Unchecked
        self.stateChanged.emit(2 if self.isChecked() else 0)

    def setChecked(self, checked):
        super().setChecked(checked)
        self._update_ui(False)  # 外部设置通常不需要再次触发动画，或者设为 True 保持一致

    def _update_ui(self, animate=True):
        """更新动画状态"""
        end_pos = self.width() - self.height() + 3 if self.isChecked() else 3
        end_color = 1.0 if self.isChecked() else 0.0

        if animate:
            self.pos_anim.stop()
            self.pos_anim.setEndValue(end_pos)
            self.pos_anim.start()

            self.color_anim.stop()
            self.color_anim.setEndValue(end_color)
            self.color_anim.start()
        else:
            self.handle_position = end_pos
            self.color_progress = end_color

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        # 1. 计算插值颜色 (实现淡入淡出效果)
        r = self._color_off_bg.red() + (self._color_on_bg.red() - self._color_off_bg.red()) * self._color_anim_progress
        g = self._color_off_bg.green() + (
                    self._color_on_bg.green() - self._color_off_bg.green()) * self._color_anim_progress
        b = self._color_off_bg.blue() + (
                    self._color_on_bg.blue() - self._color_off_bg.blue()) * self._color_anim_progress
        current_bg = QColor(int(r), int(g), int(b))

        # 2. 绘制轨道
        painter.setBrush(current_bg)
        painter.drawRoundedRect(self.rect(), self.height() / 2, self.height() / 2)

        # 3. 绘制滑块
        margin = 3
        handle_size = self.height() - margin * 2
        # 增加微弱阴影增强立体感
        painter.setBrush(QColor(0, 0, 0, 30))
        painter.drawEllipse(QRectF(self._handle_position + 0.5, margin + 0.5, handle_size, handle_size))

        painter.setBrush(self._color_handle)
        painter.drawEllipse(QRectF(self._handle_position, margin, handle_size, handle_size))


class CheckBoxWidget(QtWidgets.QWidget):
    """节点内显示：复选框"""
    valueChanged = QtCore.pyqtSignal(bool)
    fixed_height = True

    def __init__(self, text="", state=False, parent=None):
        super().__init__(parent)
        self._value = state if isinstance(state, bool) else str(state).lower() in ("true", "1")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)

        self.label = QtWidgets.QLabel(text)
        self.label.setStyleSheet("color: #AAAAAA; font-family: 'Segoe UI'; font-size: 13px;")

        self.checkbox = ModernSwitch()
        self.checkbox.setChecked(self._value)

        # 现在 checkbox 拥有 stateChanged 信号了，不会再报错
        self.checkbox.stateChanged.connect(self._on_state_changed)

        layout.addWidget(self.label)
        layout.addStretch(1)
        layout.addWidget(self.checkbox)

    def _on_state_changed(self, state):
        # state 是 0 或 2
        val = state == 2
        if val != self._value:
            self._value = val
            self.valueChanged.emit(self._value)

    def get_value(self):
        return self._value

    def set_value(self, value):
        if isinstance(value, str):
            value = value.lower() in ("true", "1")
        if value != self._value:
            self._value = value
            self.checkbox.setChecked(value)