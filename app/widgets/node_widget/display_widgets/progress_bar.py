from PyQt5 import QtCore
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import ProgressBar, CaptionLabel

from app.widgets.node_widget.base import CustomNodeBaseWidget


class ProgressWidget(QWidget):
    valueChanged = QtCore.pyqtSignal(int)
    fixed_height = True
    def __init__(self, parent=None, name="", default=0, min=0, max=100):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        # 紧凑布局，适应节点尺寸
        self.layout.setContentsMargins(8, 4, 8, 4)
        self.layout.setSpacing(4)

        # 1. 标题或状态标签 (展示 "Step 1/10" 或 "45%")
        self.status_label = CaptionLabel(str(name), self)

        # 2. 进度条主体
        self.pbar = ProgressBar(self)
        self.pbar.setRange(min, max)
        self.pbar.setMinimumHeight(12)

        # 3. 详细描述标签 (可选，用于展示具体的处理内容)
        self.desc_label = CaptionLabel("", self)

        self.layout.addWidget(self.status_label)
        self.layout.addWidget(self.pbar)
        self.layout.addWidget(self.desc_label)

        # 初始化值
        self.set_value(default)

    def set_value(self, data):
        """
        支持两种数据格式：
        1. 直接传数字: 45
        2. 传字典: {"value": 45, "text": "正在上传...", "desc": "file_1.zip"}
        """
        val = int(float(data))
        self.pbar.setValue(val)
        self.status_label.setText(f"{val}%")
        self.desc_label.setVisible(False)
        self.valueChanged.emit(val)

    def get_value(self):
        return self.pbar.value()


class ProgressBarWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", default=None, min=0, max=100, window=None):
        super().__init__(parent)
        self.set_name(name)
        self.set_label_visible(False)
        widget = ProgressWidget(parent=window, name=name, default=default, min=min, max=max)
        widget.valueChanged.connect(self.on_value_changed)
        self.set_custom_widget(widget)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)