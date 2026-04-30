# -*- coding: utf-8 -*-
"""
模型配置卡片 - 优化布局，有变化自动保存
"""
import ast
import webbrowser
from loguru import logger
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from qfluentwidgets import (
    BodyLabel,
    LineEdit,
    Slider,
    SpinBox,
    PushButton,
    SwitchButton,
    PasswordLineEdit,
    ComboBox,
)

from app.widgets.basic_widget.searchable_editable_combobox import (
    SearchableEditableComboBox,
)
from app.llm_chatter.constants import (
    PARAM_UI_MAP,
    PARAM_RANGE_MAP,
    PROVIDER_MODELS,
    FREE_PROVIDERS,
)
from app.utils.utils import get_unified_font
from app.utils.config import Settings


class ModelConfigCard(QWidget):
    """模型配置卡片内容 - 有变化自动保存"""

    configApplied = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = {}
        self.current_provider = ""
        self._widgets = {}
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self._do_save)
        self._setup_ui()

    def _setup_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 4, 0, 4)
        self.layout.setSpacing(6)

    def _clear_layout(self, layout):
        """递归清理 layout"""
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self._clear_layout(child.layout())

    def set_config(self, title: str, config: dict):
        self.config = config.copy()
        self.current_provider = title

        self._clear_layout(self.layout)
        self._widgets.clear()

        # 检查是否是预置供应商
        provider_key = title
        if provider_key in PROVIDER_MODELS:
            model_label = BodyLabel("选择模型：", self)
            self.layout.addWidget(model_label)

            model_combo = SearchableEditableComboBox(self)
            saved_models = config.get("模型列表", [])
            if isinstance(saved_models, str):
                try:
                    saved_models = ast.literal_eval(saved_models)
                except:
                    logger.exception("无法解析模型列表")
                    saved_models = []
            if isinstance(saved_models, list) and len(saved_models) > 0:
                model_combo.addItems(saved_models)
            elif provider_key in PROVIDER_MODELS:
                model_combo.addItems(PROVIDER_MODELS[provider_key])
            current_model = config.get("模型名称", "")
            if current_model:
                model_combo.setText(current_model)
            model_combo.currentTextChanged.connect(lambda: self._on_field_changed())
            self.layout.addWidget(model_combo)
            self._widgets["选择模型"] = (model_label, model_combo)

        # API URL
        if provider_key in PROVIDER_MODELS:
            url_label = BodyLabel("API_URL：", self)
            self.layout.addWidget(url_label)
            url_widget = self._create_widget("api_url", "line", config.get("API_URL", ""))
            self.layout.addWidget(url_widget)
            self._widgets["API_URL"] = (url_label, url_widget)
        else:
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

        # 获取地址
        if provider_key in FREE_PROVIDERS:
            api_url = FREE_PROVIDERS[provider_key].get("获取地址", "")
            if api_url:
                url_label = BodyLabel("获取API Key：", self)
                self.layout.addWidget(url_label)

                link_btn = PushButton("点击获取API Key →", self)
                link_btn.setCursor(Qt.PointingHandCursor)
                link_btn.clicked.connect(
                    lambda checked, url=api_url: self._on_get_api_key(url)
                )
                self.layout.addWidget(link_btn)
                self._widgets["获取地址"] = (url_label, link_btn)

        # 动态字段
        skip_keys = ["模型名称", "API_URL", "认证方式", "获取地址"]
        # 显示名称映射（存储字段名 -> UI显示名）
        display_name_map = {
            "最大Token": "上下文长度",
        }
        for key, value in config.items():
            if key in skip_keys:
                continue
            ui_type = self._infer_ui_type(key, value)
            widget = self._create_widget(key, ui_type, value)
            display_name = display_name_map.get(key, key)
            label = BodyLabel(f"{display_name}：", self)
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

    def _infer_ui_type(self, key: str, value) -> str:
        key_lower = key.lower()
        if key in PARAM_UI_MAP:
            return PARAM_UI_MAP[key]
        if "key" in key_lower or "token" in key_lower:
            return "password"
        if isinstance(value, (int, float)):
            if 0 <= value <= 1 or 0 <= value <= 2:
                return "slider"
            else:
                return "spinbox"
        return "line"

    def _create_widget(self, key, ui_type: str, value):
        if ui_type == "password":
            widget = PasswordLineEdit(self)
            widget.setText(str(value) if value else "")
            widget.textChanged.connect(lambda: self._on_field_changed())
            return widget
        elif ui_type == "slider":
            range_info = PARAM_RANGE_MAP.get(
                key, {"min": 0.0, "max": 1.0, "step": 0.01, "type": "float"}
            )
            min_val = range_info["min"]
            max_val = range_info["max"]
            step = range_info["step"]
            is_float = range_info["type"] == "float"
            current = float(value) if value not in (None, "") else min_val
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
            slider.valueChanged.connect(lambda: self._on_field_changed())

            display_value = current if is_float else int(current)
            label = BodyLabel(
                f"{display_value:.2f}" if is_float else str(int(display_value)), self
            )
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

            container.slider = slider
            container.label = label
            container.range_info = range_info
            container.scale = scale

            return container
        elif ui_type == "checkbox":
            widget = SwitchButton(self)
            widget._onText = widget.tr("开启")
            widget._offText = widget.tr("关闭")
            checked = False
            if isinstance(value, bool):
                checked = value
            elif isinstance(value, str):
                checked = value.lower() in ("true", "1", "yes", "on")
            elif isinstance(value, (int, float)):
                checked = bool(value)
            widget.setChecked(checked)
            widget.checkedChanged.connect(lambda: self._on_field_changed())
            return widget
        elif ui_type == "spinbox":
            widget = SpinBox()
            val = int(value) if value else 2048
            # 从 PARAM_RANGE_MAP 获取范围配置，默认为无限范围
            range_info = PARAM_RANGE_MAP.get(key, {"min": 1, "max": 99999999})
            widget.setRange(range_info["min"], range_info["max"])
            widget.setValue(val)
            widget.valueChanged.connect(lambda: self._on_field_changed())
            return widget
        else:
            widget = LineEdit(self)
            widget.setMinimumWidth(200)
            widget.setText(str(value) if value else "")
            widget.textChanged.connect(lambda: self._on_field_changed())
            return widget

    def _on_field_changed(self):
        """字段变化时触发保存"""
        self._save_timer.start()

    def _do_save(self):
        """执行保存"""
        config = self.get_config()
        self.configApplied.emit(config)

    def get_config(self) -> dict:
        result = self.config.copy()
        for key, (label, widget) in self._widgets.items():
            actual_key = "模型名称" if key == "选择模型" else key

            if isinstance(widget, LineEdit):
                result[actual_key] = widget.text().strip()
            elif isinstance(widget, ComboBox):
                result[actual_key] = widget.currentText()
            elif isinstance(widget, SearchableEditableComboBox):
                text = (
                    widget.text().strip()
                    if callable(getattr(widget, "text", None))
                    else ""
                )
                if text:
                    result[actual_key] = text
                else:
                    result[actual_key] = (
                        widget.currentText() if hasattr(widget, "currentText") else ""
                    )
            elif hasattr(widget, "slider"):
                logical_value = widget.slider.value() / widget.scale
                range_info = getattr(widget, "range_info", {})
                if range_info.get("type") == "int":
                    result[actual_key] = int(round(logical_value))
                else:
                    result[actual_key] = float(logical_value)
            elif isinstance(widget, SpinBox):
                result[actual_key] = widget.value()
            elif hasattr(widget, "isChecked"):
                result[actual_key] = widget.isChecked()
            else:
                result[actual_key] = ""
        return result

    def _on_get_api_key(self, url: str):
        webbrowser.open(url)
