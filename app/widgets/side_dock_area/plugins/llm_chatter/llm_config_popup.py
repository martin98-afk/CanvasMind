# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLineEdit,
    QApplication
)
from qfluentwidgets import (
    BodyLabel, LineEdit, Slider, SpinBox, PrimaryPushButton,
    PushButton
)

class LLMConfigPopup(QWidget):
    configApplied = pyqtSignal(dict)  # 发送确认后的配置

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.config = {}
        self.parent_widget = parent

        self._setup_ui()

    def _setup_ui(self):

        # 外层容器（带样式）
        self.main_frame = QFrame(self)
        self.main_frame.setObjectName("popupFrame")
        self.main_frame.setStyleSheet("""
            QFrame#popupFrame {
                background-color: #2d2d2d;
                border: 1px solid #444;
                border-radius: 8px;
                padding: 12px;
            }
        """)

        layout = QVBoxLayout(self.main_frame)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        # 标题
        title = BodyLabel("大模型设置", self)
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: white;")
        layout.addWidget(title)

        # 模型名称
        self.model_edit = LineEdit(self)
        self.model_edit.setMinimumWidth(280)
        self.model_edit.setPlaceholderText("例如：qwen/qwen3-30b")
        layout.addWidget(BodyLabel("模型名称：", self))
        layout.addWidget(self.model_edit)

        # API Key
        self.api_key_edit = LineEdit(self)
        self.api_key_edit.setPlaceholderText("sk-xxxx")
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        layout.addWidget(BodyLabel("API Key：", self))
        layout.addWidget(self.api_key_edit)

        # API Base
        self.api_base_edit = LineEdit(self)
        self.api_base_edit.setPlaceholderText("http://127.0.0.1:1234/v1")
        layout.addWidget(BodyLabel("API Base：", self))
        layout.addWidget(self.api_base_edit)

        # Max Tokens
        layout.addWidget(BodyLabel("Max Tokens：", self))
        self.max_tokens_spin = SpinBox(self)
        self.max_tokens_spin.setRange(1024, 409600)
        layout.addWidget(self.max_tokens_spin)

        # Temperature
        temp_layout = QHBoxLayout()
        self.temp_slider = Slider(Qt.Horizontal, self)
        self.temp_slider.setRange(0, 100)
        self.temp_label = BodyLabel("0.70", self)
        self.temp_label.setFixedWidth(40)
        self.temp_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.temp_slider.valueChanged.connect(
            lambda v: self.temp_label.setText(f"{v / 100:.2f}")
        )
        temp_layout.addWidget(self.temp_slider)
        temp_layout.addWidget(self.temp_label)
        layout.addWidget(BodyLabel("Temperature：", self))
        layout.addLayout(temp_layout)

        # 按钮区
        btn_layout = QHBoxLayout()
        self.apply_btn = PrimaryPushButton("应用", self)
        self.cancel_btn = PushButton("取消", self)
        self.apply_btn.clicked.connect(self._on_apply)
        self.cancel_btn.clicked.connect(self.close)

        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.apply_btn)
        layout.addLayout(btn_layout)

        # 整体布局
        window_layout = QVBoxLayout(self)
        window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.addWidget(self.main_frame)

    def set_config(self, config: dict):
        """从外部传入配置初始化 UI"""
        self.config = config.copy()
        self.model_edit.setText(config.get("模型名称", ""))
        self.api_key_edit.setText(config.get("API_KEY", ""))
        self.api_base_edit.setText(config.get("API_URL", ""))
        self.max_tokens_spin.setValue(config.get("MaxTokens", 2048))
        temp = config.get("Temperature", 0.7)
        self.temp_slider.setValue(int(temp * 100))
        self.temp_label.setText(f"{temp:.2f}")

    def get_config(self) -> dict:
        return {
            "模型名称": self.model_edit.text().strip(),
            "API_KEY": self.api_key_edit.text().strip(),
            "API_URL": self.api_base_edit.text().strip(),
            "MaxTokens": self.max_tokens_spin.value(),
            "Temperature": self.temp_slider.value() / 100,
        }

    def _on_apply(self):
        self.configApplied.emit(self.get_config())
        self.close()

    def show_at(self, reference_widget: QWidget):
        """
        将 popup 显示在 reference_widget（如设置按钮）的下方，并右对齐。
        """
        self.adjustSize()
        self.main_frame.adjustSize()
        self.resize(self.main_frame.sizeHint())

        # 获取按钮在全局坐标系中的几何位置
        btn_rect = reference_widget.rect()
        btn_global_pos = reference_widget.mapToGlobal(btn_rect.topLeft())
        btn_width = btn_rect.width()
        btn_height = btn_rect.height()

        popup_width = self.width()
        popup_height = self.height()

        # 计算 popup 的 X：使右边缘对齐
        x = btn_global_pos.x() + btn_width - popup_width
        # Y：从按钮底部开始
        y = btn_global_pos.y() + btn_height

        # 获取屏幕可用区域，防止超出
        screen = QApplication.primaryScreen()
        if screen:
            screen_geom = screen.availableGeometry()
            # 限制 X 不小于屏幕左边界
            x = max(x, screen_geom.left())
            # 如果 popup 会超出屏幕底部，则尝试向上弹出
            if y + popup_height > screen_geom.bottom():
                y = btn_global_pos.y() - popup_height  # 弹到按钮上方

        self.move(x, y)
        self.show()
        self.setFocus()