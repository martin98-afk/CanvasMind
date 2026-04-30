# -*- coding: utf-8 -*-
import requests
from PyQt5.QtCore import pyqtSignal, QSize, Qt, QRect, QTimer
from PyQt5.QtGui import QIcon, QPainter, QColor, QFont
from PyQt5.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QPushButton,
    QDialog,
    QLineEdit,
    QDoubleSpinBox,
    QFrame,
)
from qfluentwidgets import (
    ToolButton,
    FluentIcon,
    PushButton,
    qconfig,
    ExpandSettingCard,
    ConfigItem,
    LineEdit,
    Dialog,
    PrimaryPushButton,
    StrongBodyLabel,
    IconWidget,
    InfoBar,
    BodyLabel,
)
from app.utils.utils import get_icon
from app.widgets.basic_widget.searchable_editable_combobox import (
    SearchableEditableComboBox,
)
from app.llm_chatter.constants import (
    PROVIDER_ICONS,
    PROVIDER_MODELS,
    FREE_PROVIDERS,
)


def fetch_provider_models(
    api_url: str, api_key: str, provider_name: str, auth_type: str = "bearer"
) -> list:
    """Fetch model list from provider API. Returns (success, models_or_error_msg)."""
    headers = {"Authorization": f"Bearer {api_key}"} if auth_type == "bearer" else {}

    urls_to_try = []
    if provider_name == "MiniMax (月之暗面)":
        urls_to_try = [
            f"{api_url.rstrip('/')}/v1/models",
            f"{api_url.rstrip('/')}/api/models",
        ]
    elif provider_name == "DeepSeek":
        urls_to_try = [f"{api_url.rstrip('/')}/models"]
    else:
        urls_to_try = [
            f"{api_url.rstrip('/')}/models",
            f"{api_url.rstrip('/')}/v1/models",
        ]

    last_error = ""
    for url in urls_to_try:
        try:
            print(f"[ProviderEditDialog] Trying {url}")
            response = requests.get(url, headers=headers, timeout=10)
            print(f"[ProviderEditDialog] Response status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()

                if isinstance(data, dict):
                    if "data" in data:
                        return [
                            m.get("id") or m.get("name", "") or m.get("model", "")
                            for m in data["data"]
                            if isinstance(m, dict)
                        ]
                    elif "models" in data:
                        return [
                            m.get("id") or m.get("name", "")
                            for m in data["models"]
                            if isinstance(m, dict)
                        ]
                    elif "object" in data and isinstance(data["object"], list):
                        return [
                            m.get("id", "")
                            for m in data["object"]
                            if isinstance(m, dict)
                        ]
                    for key in ["items", "result"]:
                        if key in data and isinstance(data[key], list):
                            return [
                                m.get("id")
                                or m.get("name", "")
                                or (m if isinstance(m, str) else "")
                                for m in data[key]
                            ]
                elif isinstance(data, list):
                    return [
                        m.get("id", "") if isinstance(m, dict) else str(m) for m in data
                    ]
            else:
                last_error = f"HTTP {response.status_code}"

        except requests.exceptions.Timeout:
            last_error = "请求超时"
        except requests.exceptions.ConnectionError:
            last_error = "连接失败"
        except Exception as e:
            last_error = str(e)

    if last_error:
        print(f"[ProviderEditDialog] All attempts failed. Last error: {last_error}")
    return []


class ProviderIconWidget(IconWidget):
    def __init__(self, provider_name: str, size: int = 32, parent=None):
        super().__init__(parent)
        self.provider_name = provider_name
        self.setFixedSize(size, size)
        self._init_icon()

    def _init_icon(self):
        icon_name = PROVIDER_ICONS.get(self.provider_name, "")
        if icon_name:
            icon = get_icon(icon_name)
            if icon:
                self.setIcon(icon)
                return
        letters = ""
        for part in self.provider_name.split():
            if part and part not in ["(", ")", "（", "）"]:
                letters += part[0]
        if len(letters) > 2:
            letters = letters[:2]
        self._text = letters

    def paintEvent(self, event):
        if not hasattr(self, "_text") or not self._text:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = self._get_color()
        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 6, 6)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont(get_unified_font().family(), self.width() // 3, QFont.Bold))
        painter.drawText(
            QRect(0, 0, self.width(), self.height()), Qt.AlignCenter, self._text
        )

    def _get_color(self):
        colors = [
            "#0078d4",
            "#e74c3c",
            "#2ecc71",
            "#9b59b6",
            "#f39c12",
            "#1abc9c",
            "#34495e",
        ]
        hash_val = sum(ord(c) for c in self.provider_name)
        return colors[hash_val % len(colors)]


class ProviderItem(QWidget):
    removed = pyqtSignal(QWidget)
    selected = pyqtSignal(QWidget)
    editRequested = pyqtSignal(str, dict)

    def __init__(
        self, provider_name: str, provider_info: dict, is_default: bool, parent=None
    ):
        super().__init__(parent=parent)
        self.provider_name = provider_name
        self.provider_info = provider_info
        self.is_default = is_default
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        self.setFixedHeight(56)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setStyleSheet("""
            ProviderItem {
                background-color: transparent;
                border-radius: 8px;
            }
            ProviderItem:hover {
                background-color: #3d3d3d;
            }
        """)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(12)

        self.radioButton = QPushButton()
        self.radioButton.setFixedSize(20, 20)
        self.radioButton.setCheckable(True)
        self.radioButton.setChecked(self.is_default)
        self.radioButton.setCursor(Qt.PointingHandCursor)
        self.radioButton.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 2px solid #555555;
                border-radius: 10px;
            }
            QPushButton:checked {
                border: 2px solid #0078d4;
                background-color: #0078d4;
            }
            QPushButton:hover {
                border-color: #0078d4;
            }
        """)

        self.iconWidget = ProviderIconWidget(self.provider_name, 32)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        self.nameLabel = QLabel(self.provider_name)
        self.nameLabel.setStyleSheet(
            "color: #ffffff; font-size: 14px; font-weight: 500;"
        )
        self.modelLabel = QLabel(self.provider_info.get("模型名称", ""))
        self.modelLabel.setStyleSheet("color: #888888; font-size: 12px;")

        info_layout.addWidget(self.nameLabel)
        info_layout.addWidget(self.modelLabel)

        main_layout.addWidget(self.radioButton, 0, Qt.AlignLeft | Qt.AlignVCenter)
        main_layout.addWidget(self.iconWidget, 0, Qt.AlignLeft | Qt.AlignVCenter)
        main_layout.addLayout(info_layout)
        main_layout.addStretch(1)

        btn_widget = QWidget()
        btn_widget.setStyleSheet("background-color: transparent;")
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(4)
        self.editButton = ToolButton(FluentIcon.EDIT)
        self.removeButton = ToolButton(FluentIcon.CLOSE)
        self.editButton.setFixedSize(28, 28)
        self.removeButton.setFixedSize(28, 28)
        self.editButton.setIconSize(QSize(14, 14))
        self.removeButton.setIconSize(QSize(14, 14))
        self.editButton.setStyleSheet(
            "background-color: transparent; border-radius: 4px;"
        )
        self.removeButton.setStyleSheet(
            "background-color: transparent; border-radius: 4px;"
        )
        btn_layout.addWidget(self.editButton)
        btn_layout.addWidget(self.removeButton)
        main_layout.addWidget(btn_widget, 0, Qt.AlignRight | Qt.AlignVCenter)

    def _connect_signals(self):
        self.removeButton.clicked.connect(lambda: self.removed.emit(self))
        self.radioButton.clicked.connect(lambda: self.selected.emit(self))
        self.editButton.clicked.connect(self._on_edit)

    def _on_edit(self):
        self.editRequested.emit(self.provider_name, self.provider_info)

    def update_info(self, name: str, info: dict):
        self.provider_name = name
        self.provider_info = info
        self.nameLabel.setText(name)
        self.modelLabel.setText(info.get("模型名称", ""))
        self.iconWidget.provider_name = name
        self.iconWidget._init_icon()
        self.iconWidget.update()


class ProviderEditDialog(QDialog):
    def __init__(
        self, provider_name: str, provider_info: dict, is_new: bool, parent=None
    ):
        super().__init__(parent)
        self.provider_name = provider_name
        self.provider_info = provider_info.copy() if provider_info else {}
        self.is_new = is_new
        self.setWindowTitle("添加服务商" if is_new else "编辑服务商")
        self.setMinimumSize(480, 480)
        self.setMaximumSize(520, 800)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowTitleHint)
        self.setModal(True)
        self._original_info = provider_info.copy() if provider_info else {}
        self._fetch_thread = None
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
            }
            QLabel {
                color: #cccccc;
                background: transparent;
            }
            QDoubleSpinBox {
                background-color: #3d3d3d;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QDoubleSpinBox:hover {
                border-color: #0078d4;
            }
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                background-color: #3d3d3d;
                border: none;
            }
            QFrame#section_frame {
                background-color: #333333;
                border-radius: 8px;
                border: none;
            }
            QPushButton#fetch_btn {
                background-color: #1a8cd4;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
            }
            QPushButton#fetch_btn:hover {
                background-color: #0078d4;
            }
            QPushButton#fetch_btn:disabled {
                background-color: #555555;
                color: #888888;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        header_label = StrongBodyLabel("添加服务商" if self.is_new else "编辑服务商")
        header_label.setStyleSheet(
            "color: #ffffff; font-size: 16px; font-weight: bold;"
        )
        main_layout.addWidget(header_label)

        connection_frame = QFrame()
        connection_frame.setObjectName("section_frame")
        connection_layout = QVBoxLayout(connection_frame)
        connection_layout.setContentsMargins(16, 12, 16, 12)
        connection_layout.setSpacing(12)

        conn_title = BodyLabel("连接配置")
        conn_title.setStyleSheet("color: #4fc3f7; font-size: 13px; font-weight: bold;")
        connection_layout.addWidget(conn_title)

        self.getKeyBtn = None
        if self.is_new:
            name_row = QHBoxLayout()
            name_row.addWidget(QLabel("服务商:"))
            self.nameCombo = SearchableEditableComboBox()
            for provider_name in FREE_PROVIDERS.keys():
                icon_name = PROVIDER_ICONS.get(provider_name, "大模型")
                icon = get_icon(icon_name)
                self.nameCombo.addItem(provider_name, icon=icon)
            self.nameCombo.setDisabled(False)
            self.nameCombo.setCurrentIndex(0)
            self.nameCombo.currentTextChanged.connect(self._on_provider_changed)
            name_row.addWidget(self.nameCombo, 1)

            self.getKeyBtn = QPushButton("获取API Key")
            self.getKeyBtn.setFixedSize(90, 28)
            self.getKeyBtn.setCursor(Qt.PointingHandCursor)
            self.getKeyBtn.setStyleSheet("""
                QPushButton {
                    background-color: #0078d4;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #1a8cd4;
                }
            """)
            self.getKeyBtn.clicked.connect(
                lambda: self._open_help_url(self.nameCombo.currentText())
            )
            name_row.addWidget(self.getKeyBtn)

            connection_layout.addLayout(name_row)
            first_provider = self.nameCombo.currentText()
            template = FREE_PROVIDERS.get(first_provider, {})
        elif self.provider_name in FREE_PROVIDERS:
            template = FREE_PROVIDERS[self.provider_name]
            name_row = QHBoxLayout()
            name_row.addWidget(QLabel("服务商:"))
            name_row.addWidget(QLabel(self.provider_name))
            connection_layout.addLayout(name_row)
        else:
            template = self.provider_info
            name_row = QHBoxLayout()
            name_row.addWidget(QLabel("服务商:"))
            name_row.addWidget(QLabel(self.provider_name))
            connection_layout.addLayout(name_row)

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("API URL:"))
        self.apiUrlEdit = LineEdit()
        self.apiUrlEdit.setText(
            self.provider_info.get("API_URL", template.get("API_URL", ""))
        )
        url_row.addWidget(self.apiUrlEdit, 1)
        connection_layout.addLayout(url_row)

        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("API Key:"))
        self.apiKeyEdit = LineEdit()
        self.apiKeyEdit.setEchoMode(QLineEdit.Password)
        self.apiKeyEdit.setText(self.provider_info.get("API_KEY", ""))
        key_row.addWidget(self.apiKeyEdit, 1)
        connection_layout.addLayout(key_row)

        main_layout.addWidget(connection_frame)

        model_frame = QFrame()
        model_frame.setObjectName("section_frame")
        model_layout = QVBoxLayout(model_frame)
        model_layout.setContentsMargins(16, 12, 16, 12)
        model_layout.setSpacing(12)

        model_title_layout = QHBoxLayout()
        model_title = BodyLabel("模型配置")
        model_title.setStyleSheet("color: #4fc3f7; font-size: 13px; font-weight: bold;")
        model_title_layout.addWidget(model_title)
        model_title_layout.addStretch()

        self.fetchBtn = QPushButton("从API获取模型列表")
        self.fetchBtn.setObjectName("fetch_btn")
        self.fetchBtn.setCursor(Qt.PointingHandCursor)
        self.fetchBtn.clicked.connect(self._on_fetch_models)
        model_title_layout.addWidget(self.fetchBtn)
        model_layout.addLayout(model_title_layout)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("默认模型:"))
        self.modelCombo = SearchableEditableComboBox()
        self.modelCombo.setDisabled(False)
        current_model = self.provider_info.get("模型名称", template.get("模型名称", ""))
        saved_models = self.provider_info.get("模型列表", [])
        if isinstance(saved_models, list):
            saved_models_to_use = saved_models
        else:
            saved_models_to_use = []
        if self.is_new:
            selected_provider = self.nameCombo.currentText()
            if saved_models_to_use:
                self.modelCombo.addItems(saved_models_to_use)
            elif selected_provider in PROVIDER_MODELS:
                self.modelCombo.addItems(PROVIDER_MODELS[selected_provider])
            elif "DeepSeek" in PROVIDER_MODELS:
                self.modelCombo.addItems(PROVIDER_MODELS["DeepSeek"])
        else:
            if saved_models_to_use:
                self.modelCombo.addItems(saved_models_to_use)
            elif self.provider_name in PROVIDER_MODELS:
                self.modelCombo.addItems(PROVIDER_MODELS[self.provider_name])
            elif (
                self.provider_name in FREE_PROVIDERS
                and "模型名称" in FREE_PROVIDERS[self.provider_name]
            ):
                self.modelCombo.addItem(
                    FREE_PROVIDERS[self.provider_name].get("模型名称", "")
                )
        if current_model:
            self.modelCombo.addItem(current_model)
            idx = self.modelCombo.findText(current_model)
            if idx >= 0:
                self.modelCombo.setCurrentIndex(idx)
        model_row.addWidget(self.modelCombo, 1)
        model_layout.addLayout(model_row)

        self.fetchStatusLabel = BodyLabel("")
        self.fetchStatusLabel.setStyleSheet("color: #888888; font-size: 11px;")
        model_layout.addWidget(self.fetchStatusLabel)
        self._fetched_models = []

        main_layout.addWidget(model_frame)

        param_frame = QFrame()
        param_frame.setObjectName("section_frame")
        param_layout = QVBoxLayout(param_frame)
        param_layout.setContentsMargins(16, 12, 16, 12)
        param_layout.setSpacing(12)

        param_title = BodyLabel("生成参数")
        param_title.setStyleSheet("color: #4fc3f7; font-size: 13px; font-weight: bold;")
        param_layout.addWidget(param_title)

        temp_row = QHBoxLayout()
        temp_row.addWidget(QLabel("温度:"))
        self.tempSpin = QDoubleSpinBox()
        self.tempSpin.setRange(0, 2)
        self.tempSpin.setSingleStep(0.1)
        self.tempSpin.setValue(
            self._original_info.get("温度", template.get("温度", 0.7))
        )
        self.tempSpin.setDecimals(2)
        temp_row.addWidget(self.tempSpin, 1)
        param_layout.addLayout(temp_row)

        context_row = QHBoxLayout()
        context_row.addWidget(QLabel("上下文长度:"))
        self.contextLengthSpin = QDoubleSpinBox()
        self.contextLengthSpin.setRange(1, 99999999)
        self.contextLengthSpin.setSingleStep(1000)
        self.contextLengthSpin.setValue(
            self._original_info.get("最大Token", template.get("最大Token", 4096))
        )
        self.contextLengthSpin.setDecimals(0)
        context_row.addWidget(self.contextLengthSpin, 1)
        param_layout.addLayout(context_row)

        main_layout.addWidget(param_frame)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.cancelBtn = QPushButton("取消")
        self.saveBtn = PrimaryPushButton("保存")
        self.cancelBtn.setFixedSize(100, 36)
        self.saveBtn.setFixedSize(100, 36)
        btn_layout.addWidget(self.cancelBtn)
        btn_layout.addWidget(self.saveBtn)
        main_layout.addLayout(btn_layout)

        self.cancelBtn.clicked.connect(self.reject)
        self.saveBtn.clicked.connect(self._on_save)

        if self.is_new:
            self._on_provider_changed(self.nameCombo.currentText())

    def _on_provider_changed(self, name: str):
        if name in FREE_PROVIDERS:
            template = FREE_PROVIDERS[name]
            self.apiUrlEdit.setText(template.get("API_URL", ""))
            self.modelCombo.clear()
            if name in PROVIDER_MODELS:
                self.modelCombo.addItems(PROVIDER_MODELS[name])
            self.modelCombo.addItem(template.get("模型名称", ""))
            self.modelCombo.setCurrentIndex(0)
            self.contextLengthSpin.setValue(template.get("最大Token", 4096))
        self.fetchStatusLabel.setText("")

    def _on_fetch_models(self):
        api_url = self.apiUrlEdit.text().strip()
        api_key = self.apiKeyEdit.text().strip()
        provider_name = (
            self.nameCombo.currentText() if self.is_new else self.provider_name
        )

        if not api_url or not api_key:
            self.fetchStatusLabel.setText("请先填写 API URL 和 API Key")
            self.fetchStatusLabel.setStyleSheet("color: #e74c3c; font-size: 11px;")
            return

        self.fetchBtn.setEnabled(False)
        self.fetchStatusLabel.setText("正在获取模型列表...")
        self.fetchStatusLabel.setStyleSheet("color: #888888; font-size: 11px;")

        try:
            models = fetch_provider_models(api_url, api_key, provider_name)
            self._on_models_fetched(models)
        except Exception as e:
            self._on_models_fetched([])

    def _on_models_fetched(self, models: list):
        self.fetchBtn.setEnabled(True)
        if not isinstance(models, list):
            models = []
        self._fetched_models = models
        if models:
            self.modelCombo.blockSignals(True)
            current = self.modelCombo.currentText()
            self.modelCombo.clear()
            self.modelCombo.addItems(models)
            if current and self.modelCombo.findText(current) >= 0:
                self.modelCombo.setCurrentIndex(self.modelCombo.findText(current))
            self.modelCombo.blockSignals(False)
            self.fetchStatusLabel.setText(f"成功获取 {len(models)} 个模型")
            self.fetchStatusLabel.setStyleSheet("color: #2ecc71; font-size: 11px;")
        else:
            self.fetchStatusLabel.setText("获取模型列表失败，请检查 API 配置")
            self.fetchStatusLabel.setStyleSheet("color: #e74c3c; font-size: 11px;")

    def _open_help_url(self, name: str):
        if name in FREE_PROVIDERS:
            import webbrowser

            url = FREE_PROVIDERS[name].get("获取地址", "")
            if url:
                webbrowser.open(url)

    def _on_save(self):
        provider_name = (
            self.nameCombo.currentText() if self.is_new else self.provider_name
        )
        self.provider_info = {
            "API_URL": self.apiUrlEdit.text().strip(),
            "API_KEY": self.apiKeyEdit.text().strip(),
            "模型名称": self.modelCombo.currentText().strip(),
            "温度": self.tempSpin.value(),
            "最大Token": int(self.contextLengthSpin.value()),
            "认证方式": "bearer",
        }
        if self._fetched_models:
            self.provider_info["模型列表"] = self._fetched_models
        self.accept()

    def get_result(self):
        if self.is_new:
            return self.nameCombo.currentText(), self.provider_info
        return self.provider_name, self.provider_info


class ProviderListSettingCard(ExpandSettingCard):
    providerChanged = pyqtSignal(dict)
    defaultProviderChanged = pyqtSignal(str)

    def __init__(
        self,
        icon: QIcon,
        configItem: ConfigItem,
        defaultProviderItem: ConfigItem,
        title: str,
        content: str = None,
        parent=None,
        home=None,
    ):
        self.home = home
        super().__init__(icon, title, content, parent)
        self.title = title
        self.configItem = configItem
        self.defaultProviderItem = defaultProviderItem
        self.addProviderButton = PushButton("添加服务商", self, FluentIcon.ADD)
        self.providers = (
            qconfig.get(configItem).copy()
            if isinstance(qconfig.get(configItem), dict)
            else {}
        )
        self.default_provider = qconfig.get(defaultProviderItem) or ""
        self.__initWidget()

    def __initWidget(self):
        self.addWidget(self.addProviderButton)
        self.viewLayout.setSpacing(0)
        self.viewLayout.setAlignment(Qt.AlignTop)
        self.viewLayout.setContentsMargins(8, 0, 8, 0)
        self.view.setStyleSheet("background-color: transparent;")
        self._refresh_items()
        self.addProviderButton.clicked.connect(self._show_add_dialog)

    def _refresh_items(self):
        self.providers = (
            qconfig.get(self.configItem).copy()
            if isinstance(qconfig.get(self.configItem), dict)
            else {}
        )
        self.default_provider = qconfig.get(self.defaultProviderItem) or ""
        while self.viewLayout.count() > 0:
            item = self.viewLayout.takeAt(0)
            if item.widget() and item.widget() != self.addProviderButton:
                item.widget().deleteLater()
        for name, info in self.providers.items():
            is_default = name == self.default_provider
            self._add_provider_item(name, info, is_default)

    def _add_provider_item(self, name: str, info: dict, is_default: bool):
        item = ProviderItem(name, info, is_default, self.view)
        item.removed.connect(self._show_confirm_dialog)
        item.selected.connect(lambda i: self._select_provider(i))
        item.editRequested.connect(lambda n, i: self._show_edit_dialog(n, i, item))
        self.viewLayout.addWidget(item)
        item.show()
        self._adjustViewSize()

    def _show_add_dialog(self):
        dialog = ProviderEditDialog("", {}, True, self.home)
        if dialog.exec():
            name, info = dialog.get_result()
            if name and name not in self.providers:
                self.providers[name] = info
                qconfig.set(self.configItem, self.providers)
                self._add_provider_item(name, info, False)
                self.providerChanged.emit(self.providers)

    def _show_edit_dialog(self, name: str, info: dict, item: ProviderItem):
        self.providers = (
            qconfig.get(self.configItem).copy()
            if isinstance(qconfig.get(self.configItem), dict)
            else {}
        )
        current_info = self.providers.get(name, {})
        if not current_info:
            current_info = info
        dialog = ProviderEditDialog(name, current_info, False, self.home)
        if dialog.exec():
            new_name, new_info = dialog.get_result()
            if new_name in self.providers:
                self.providers[new_name] = new_info
                qconfig.set(self.configItem, self.providers)
                item.update_info(new_name, new_info)
                self.providerChanged.emit(self.providers)

    def _show_confirm_dialog(self, item: ProviderItem):
        title = self.tr("确定要删除这个服务商吗?")
        content = (
            self.tr('删除 "') + item.provider_name + self.tr('" 后将不再出现在列表中。')
        )
        w = Dialog(title, content, self.window())
        w.yesSignal.connect(lambda: self._remove_provider(item))
        w.exec_()

    def _remove_provider(self, item: ProviderItem):
        if item.provider_name not in self.providers:
            return
        del self.providers[item.provider_name]
        qconfig.set(self.configItem, self.providers)
        self.viewLayout.removeWidget(item)
        item.deleteLater()
        self._adjustViewSize()
        self.providerChanged.emit(self.providers)
        if self.default_provider == item.provider_name:
            keys = list(self.providers.keys())
            self.default_provider = keys[0] if keys else ""
            qconfig.set(self.defaultProviderItem, self.default_provider)
            self.defaultProviderChanged.emit(self.default_provider)

    def _select_provider(self, item: ProviderItem):
        for i in range(self.viewLayout.count()):
            w = self.viewLayout.itemAt(i).widget()
            if isinstance(w, ProviderItem) and w != item:
                w.radioButton.setChecked(False)
        item.radioButton.setChecked(True)
        self.default_provider = item.provider_name
        qconfig.set(self.defaultProviderItem, self.default_provider)
        self.defaultProviderChanged.emit(self.default_provider)
