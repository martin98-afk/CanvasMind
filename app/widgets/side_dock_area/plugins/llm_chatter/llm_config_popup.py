# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLineEdit, QSpacerItem, QSizePolicy, QApplication
)
from qfluentwidgets import (
    BodyLabel, LineEdit, Slider, SpinBox, PrimaryPushButton,
    PushButton, CaptionLabel
)

class LLMConfigPopup(QWidget):
    configApplied = pyqtSignal(dict)

    # 定义常见参数的 UI 类型映射（可扩展）
    PARAM_UI_MAP = {
        "API_KEY": "password",
        "温度": "slider",
        "是否思考": "checkbox",
        "temp": "slider",
        "最大Token": "spinbox",
        "max_new_tokens": "spinbox",
        "top_p": "slider",
        "frequency_penalty": "slider",
        "presence_penalty": "slider",
    }

    def __init__(self, title="大模型配置", parent=None):
        super().__init__(parent)
        self.title = title
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.config = {}
        self.parent_widget = parent

        # 动态控件存储
        self._widgets = {}  # key -> (label, widget)

        self._setup_ui()

    def _setup_ui(self):
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

        self.layout = QVBoxLayout(self.main_frame)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(3)

        title_label = BodyLabel(self.title, self)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: white;")
        self.layout.addWidget(title_label, 0, Qt.AlignHCenter)

        # 按钮区（先预留，最后添加）
        self.btn_layout = QHBoxLayout()
        self.apply_btn = PrimaryPushButton("应用", self)
        self.cancel_btn = PushButton("取消", self)
        self.apply_btn.clicked.connect(self._on_apply)
        self.cancel_btn.clicked.connect(self.close)
        self.btn_layout.addStretch()
        self.btn_layout.addWidget(self.cancel_btn)
        self.btn_layout.addWidget(self.apply_btn)

        # 整体窗口布局
        window_layout = QVBoxLayout(self)
        window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.addWidget(self.main_frame)

    def set_config(self, config: dict):
        """动态根据 config 生成 UI 控件"""
        self.config = config.copy()

        # 清空旧控件（除了标题和按钮区）
        while self.layout.count() > 1:  # 保留标题（索引0）
            item = self.layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        self._widgets.clear()

        # 强制字段（即使 config 里没有也显示）
        required_fields = {
            "模型名称": ("model_name", "line"),
            "API_URL": ("api_url", "line"),
        }
        for label_text, (key, ui_type) in required_fields.items():
            value = config.get(label_text, "")
            widget = self._create_widget(ui_type, value)
            label = CaptionLabel(f"{label_text}：", self)
            self.layout.addWidget(label)
            self.layout.addWidget(widget)
            self._widgets[label_text] = (label, widget)

        # 动态字段：遍历 config 中除强制字段外的所有键
        for key, value in config.items():
            if key in ["模型名称", "API_URL"]:
                continue  # 已处理
            # 尝试匹配 UI 类型
            ui_type = self._infer_ui_type(key, value)
            widget = self._create_widget(ui_type, value)
            label = CaptionLabel(f"{key}：", self)
            self.layout.addWidget(label)
            self.layout.addWidget(widget)
            self._widgets[key] = (label, widget)

        # 添加按钮区（确保在最后）
        self.layout.addLayout(self.btn_layout)

        # 调整大小（重要！）
        self.main_frame.adjustSize()
        self.adjustSize()

    def _infer_ui_type(self, key: str, value) -> str:
        """根据 key 或 value 类型推断 UI 类型"""
        key_lower = key.lower()
        if key in self.PARAM_UI_MAP:
            return self.PARAM_UI_MAP[key]
        if "key" in key_lower or "token" in key_lower:
            return "password"
        if isinstance(value, (int, float)):
            if 0 <= value <= 1 or 0 <= value <= 2:  # 如 temperature=0.7
                return "slider"
            else:
                return "spinbox"
        return "line"

    def _create_widget(self, ui_type: str, value):
        """根据类型创建控件"""
        if ui_type == "password":
            widget = LineEdit(self)
            widget.setEchoMode(QLineEdit.Password)
            widget.setText(str(value) if value else "")
            return widget
        elif ui_type == "slider":
            # 创建 HBox: slider + label
            container = QWidget(self)
            hlayout = QHBoxLayout(container)
            hlayout.setContentsMargins(0, 0, 0, 0)
            slider = Slider(Qt.Horizontal, self)
            value_float = float(value) if value else 0.7
            slider.setRange(0, 100)
            slider.setValue(int(value_float * 100))
            label = BodyLabel(f"{value_float:.2f}", self)
            label.setFixedWidth(40)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            slider.valueChanged.connect(lambda v, lbl=label: lbl.setText(f"{v / 100:.2f}"))
            hlayout.addWidget(slider)
            hlayout.addWidget(label)
            # 存储引用用于 get_config
            container.slider = slider
            container.label = label
            return container
        elif ui_type == "checkbox":
            from qfluentwidgets import CheckBox
            widget = CheckBox(self)
            # 支持传入 bool 或字符串 "true"/"True"/"1"
            checked = False
            if isinstance(value, bool):
                checked = value
            elif isinstance(value, str):
                checked = value.lower() in ("true", "1", "yes", "on")
            elif isinstance(value, (int, float)):
                checked = bool(value)
            widget.setChecked(checked)
            return widget
        elif ui_type == "spinbox":
            widget = SpinBox(self)
            val = int(value) if value else 2048
            # 根据值范围动态设范围（可优化）
            if val <= 1000:
                widget.setRange(0, 2000)
            elif val <= 32768:
                widget.setRange(1024, 32768)
            else:
                widget.setRange(1024, 409600)
            widget.setValue(val)
            return widget
        else:
            widget = LineEdit(self)
            widget.setText(str(value) if value else "")
            return widget

    def get_config(self) -> dict:
        result = {}
        for key, (label, widget) in self._widgets.items():
            if isinstance(widget, LineEdit):
                result[key] = widget.text().strip()
            elif hasattr(widget, 'slider'):  # slider + label 容器
                result[key] = widget.slider.value() / 100
            elif isinstance(widget, SpinBox):
                result[key] = widget.value()
            elif hasattr(widget, 'isChecked'):  # CheckBox or QCheckBox
                result[key] = widget.isChecked()
            else:
                result[key] = ""
        return result

    def _on_apply(self):
        self.configApplied.emit(self.get_config())
        self.close()

    def show_at(self, reference_widget: QWidget):
        self.adjustSize()
        btn_rect = reference_widget.rect()
        btn_global_pos = reference_widget.mapToGlobal(btn_rect.topLeft())
        btn_width = btn_rect.width()
        btn_height = btn_rect.height()

        popup_width = self.width()
        popup_height = self.height()

        x = btn_global_pos.x() + btn_width - popup_width
        y = btn_global_pos.y() + btn_height

        screen = QApplication.primaryScreen()
        if screen:
            screen_geom = screen.availableGeometry()
            x = max(x, screen_geom.left())
            if y + popup_height > screen_geom.bottom():
                y = btn_global_pos.y() - popup_height

        self.move(x, y)
        self.show()
        self.setFocus()