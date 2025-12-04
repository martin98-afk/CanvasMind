# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLineEdit, QSpacerItem, QSizePolicy, QApplication
)
from qfluentwidgets import (
    BodyLabel, LineEdit, Slider, SpinBox, PrimaryPushButton,
    PushButton, CaptionLabel, SwitchButton
)

from app.widgets.side_dock_area.plugins.llm_chatter.constants import PARAM_UI_MAP, PARAM_RANGE_MAP


class LLMConfigPopup(QWidget):
    configApplied = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
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
        self.layout.setSpacing(8)

        # 整体窗口布局
        window_layout = QVBoxLayout(self)
        window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.addWidget(self.main_frame)

    def _clear_layout(self, layout):
        """递归清理 layout 中的所有 widget 和子 layout"""
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self._clear_layout(child.layout())  # 递归清理子 layout

    def set_config(self, title: str, config: dict):
        self.config = config.copy()

        # 清空整个 layout（包括标题和按钮，全部重建）
        self._clear_layout(self.layout)
        self._widgets.clear()

        # 重建标题
        title_label = BodyLabel(title, self)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: white;")
        self.layout.addWidget(title_label, 0, Qt.AlignHCenter)

        # 强制字段
        required_fields = {
            "模型名称": ("model_name", "line"),
            "API_URL": ("api_url", "line"),
        }
        for label_text, (key, ui_type) in required_fields.items():
            value = config.get(label_text, "")
            widget = self._create_widget(key, ui_type, value)
            label = BodyLabel(f"{label_text}：", self)
            self.layout.addWidget(label)
            self.layout.addWidget(widget)
            self._widgets[label_text] = (label, widget)

        # 动态字段
        for key, value in config.items():
            if key in ["模型名称", "API_URL"]:
                continue
            ui_type = self._infer_ui_type(key, value)
            widget = self._create_widget(key, ui_type, value)
            label = BodyLabel(f"{key}：", self)
            if ui_type == "checkbox":
                hlayout = QHBoxLayout()
                hlayout.setContentsMargins(0, 0, 0, 0)
                hlayout.addWidget(label)
                hlayout.addStretch()
                hlayout.addWidget(widget)
                self.layout.addLayout(hlayout)
            else:
                self.layout.addWidget(label)
                self.layout.addWidget(widget)
            self._widgets[key] = (label, widget)

        # 重建按钮区（每次都新建，避免引用问题）
        self.btn_layout = QHBoxLayout()
        self.apply_btn = PrimaryPushButton("应用", self)
        self.cancel_btn = PushButton("取消", self)
        self.apply_btn.clicked.connect(self._on_apply)
        self.cancel_btn.clicked.connect(self.close)
        self.btn_layout.addWidget(self.cancel_btn)
        self.btn_layout.addWidget(self.apply_btn)
        self.layout.addLayout(self.btn_layout)

        self.main_frame.adjustSize()
        self.adjustSize()

    def _infer_ui_type(self, key: str, value) -> str:
        """根据 key 或 value 类型推断 UI 类型"""
        key_lower = key.lower()
        if key in PARAM_UI_MAP:
            return PARAM_UI_MAP[key]
        if "key" in key_lower or "token" in key_lower:
            return "password"
        if isinstance(value, (int, float)):
            if 0 <= value <= 1 or 0 <= value <= 2:  # 如 temperature=0.7
                return "slider"
            else:
                return "spinbox"
        return "line"

    def _create_widget(self, key, ui_type: str, value):
        """根据类型创建控件"""
        if ui_type == "password":
            widget = LineEdit(self)
            widget.setEchoMode(QLineEdit.Password)
            widget.setText(str(value) if value else "")
            return widget
        elif ui_type == "slider":
            # 获取范围配置
            range_info = PARAM_RANGE_MAP.get(key, {"min": 0.0, "max": 1.0, "step": 0.01, "type": "float"})
            min_val = range_info["min"]
            max_val = range_info["max"]
            step = range_info["step"]
            is_float = range_info["type"] == "float"

            # 当前值
            current = float(value) if value not in (None, "") else min_val

            # 为 Slider 使用整数刻度（避免浮点精度问题）
            # 将逻辑值映射到整数滑块范围
            scale = 1 / step
            slider_min = int(min_val * scale)
            slider_max = int(max_val * scale)
            slider_value = int(round(current * scale))

            container = QWidget(self)
            hlayout = QHBoxLayout(container)
            hlayout.setContentsMargins(0, 0, 0, 0)

            slider = Slider(Qt.Horizontal, self)
            slider.setRange(slider_min, slider_max)
            slider.setValue(slider_value)

            # 显示当前逻辑值
            display_value = current if is_float else int(current)
            label = BodyLabel(f"{display_value:.2f}" if is_float else str(int(display_value)), self)
            label.setFixedWidth(50)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            def _update_label(v):
                logical_val = v / scale
                if not is_float:
                    logical_val = int(logical_val)
                fmt_val = f"{logical_val:.2f}" if is_float else str(logical_val)
                label.setText(fmt_val)

            slider.valueChanged.connect(_update_label)

            hlayout.addWidget(slider)
            hlayout.addWidget(label)

            # 保存元信息到 container，供 get_config 使用
            container.slider = slider
            container.label = label
            container.range_info = range_info
            container.scale = scale

            return container
        elif ui_type == "checkbox":
            widget = SwitchButton(self)
            widget._onText = widget.tr('开启')
            widget._offText = widget.tr('关闭')
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
            widget.setMinimumWidth(320)
            widget.setText(str(value) if value else "")
            return widget

    def get_config(self) -> dict:
        result = {}
        for key, (label, widget) in self._widgets.items():
            if isinstance(widget, LineEdit):
                result[key] = widget.text().strip()
            elif hasattr(widget, 'slider'):  # slider + label 容器
                logical_value = widget.slider.value() / widget.scale
                range_info = getattr(widget, 'range_info', {})
                if range_info.get("type") == "int":
                    result[key] = int(round(logical_value))
                else:
                    result[key] = float(logical_value)
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
