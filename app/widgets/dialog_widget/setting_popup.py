# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QPoint, pyqtSignal, QTimer, QEvent, QSize
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QWidget,
    QApplication,
    QScrollArea,
    QHBoxLayout,
    QSizePolicy,
    QFrame,
    QDialog,
    QStackedWidget,
    QPushButton,
    QComboBox,
    QSpinBox,
)
from qfluentwidgets import (
    StrongBodyLabel,
    TransparentPushButton,
    BodyLabel,
    FluentIcon,
)

from app.utils.config import Settings
from app.utils.utils import get_icon, get_unified_font
from dist.CanvasMind._internal.app.widgets.side_dock_area.registry import SideDockRegistry


class SettingDialog(QDialog):
    configChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent_widget = None
        self._event_filter_installed = False
        self._plugin_cards = {}
        self.cfg = Settings.get_instance()

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._perform_save_to_disk)

        self._load_plugin_states_from_config()
        self.setup_ui()

    def _load_plugin_states_from_config(self):

        saved_states = self.cfg.side_dock_plugins.value
        if saved_states:
            SideDockRegistry.load_states_from_config(saved_states)

    def setup_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(
            """
            SettingDialog {
                background-color: transparent;
            }
        """
        )
        self.setObjectName("settingPopup")
        self.setContentsMargins(10, 10, 10, 10)

        container = QFrame(self)
        container.setObjectName("container")
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        container.setStyleSheet(
            """
            QFrame#container {
                background-color: #2b2b2b;
                border-radius: 12px;
                border: 1px solid #3d3d3d;
            }
        """
        )
        container.setAutoFillBackground(False)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.addWidget(container)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(40)
        header.setStyleSheet(
            "background-color: #2b2b2b; border-bottom: 1px solid #3d3d3d; border-top-left-radius: 12px; border-top-right-radius: 12px;"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 12, 0)
        header_layout.setSpacing(8)

        title_label = StrongBodyLabel(self.tr("系统设置"))
        title_label.setFont(get_unified_font(14, True))
        title_label.setStyleSheet("color: #ffffff;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        self.close_btn = TransparentPushButton("✕")
        self.close_btn.setFixedSize(32, 32)
        self.close_btn.setStyleSheet("""
            TransparentPushButton {
                background-color: transparent;
                color: #888888;
                border: none;
                border-radius: 6px;
                font-size: 14px;
            }
            TransparentPushButton:hover {
                background-color: #ff5f56;
                color: #ffffff;
            }
        """)
        self.close_btn.clicked.connect(self.hidePopup)
        header_layout.addWidget(self.close_btn)

        container_layout.addWidget(header)

        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #2b2b2b;")
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.nav_widget = QWidget()
        self.nav_widget.setFixedWidth(180)
        self.nav_widget.setStyleSheet("background-color: #252525;")
        nav_layout = QVBoxLayout(self.nav_widget)
        nav_layout.setContentsMargins(8, 16, 8, 8)
        nav_layout.setSpacing(4)

        self.nav_items = {}
        self.nav_buttons = {}
        categories = [
            ("llm", self.tr("大模型"), "大模型")
        ]
        for key, label, icon_name in categories:
            btn = self._create_nav_button(key, label, icon_name)
            self.nav_buttons[key] = btn
            nav_layout.addWidget(btn)
        nav_layout.addStretch()

        nav_footer = QWidget()
        nav_footer.setStyleSheet("background-color: transparent;")
        footer_layout = QVBoxLayout(nav_footer)
        footer_layout.setContentsMargins(12, 0, 0, 0)
        footer_layout.setSpacing(2)

        app_name = StrongBodyLabel("LLMChatter")
        app_name.setFont(get_unified_font(12, True))
        app_name.setStyleSheet("color: #888888; background: transparent;")
        footer_layout.addWidget(app_name)

        version_text = self.tr("{}").format(self.cfg.current_version)
        version_label = BodyLabel(version_text)
        version_label.setFont(get_unified_font(11))
        version_label.setStyleSheet("color: #666666; background: transparent;")
        footer_layout.addWidget(version_label)

        nav_layout.addWidget(nav_footer)

        for btn in self.nav_buttons.values():
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #aaaaaa;
                    border: none;
                    border-radius: 6px;
                    text-align: left;
                    padding-left: 12px;
                }
                QPushButton:hover {
                    background-color: #3d3d3d;
                    color: #ffffff;
                }
            """)

        self.content_stack = QStackedWidget()
        self.content_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.content_stack.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #2b2b2b;
            }
            QScrollBar:vertical {
                border: none;
                background: #2b2b2b;
                width: 10px;
                margin: 4px 2px 4px 2px;
            }
            QScrollBar::handle:vertical {
                background: #555555;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #666666;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self.content_widgets = {}
        self._create_content_pages()

        self._select_nav("llm")

        content_layout.addWidget(self.nav_widget)
        content_layout.addWidget(self.content_stack, 1)

        container_layout.addWidget(content_widget, 1)

        self.resize(900, 600)

    def _create_nav_button(self, key, text, icon_name=None):
        btn = QPushButton()
        btn.setFixedHeight(36)
        btn.setCursor(Qt.PointingHandCursor)

        if icon_name:
            icon = get_icon(icon_name)
            btn.setIcon(icon)
            btn.setIconSize(QSize(18, 18))

        btn.setText("  " + text)
        btn.setFont(get_unified_font(13, True))
        btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #aaaaaa;
                border: none;
                border-radius: 6px;
                text-align: left;
                padding-left: 12px;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #2d2d2d;
                color: #ffffff;
            }
        """)
        btn._nav_key = key
        btn.clicked.connect(lambda: self._select_nav(btn._nav_key))
        return btn

    def _select_nav(self, key):
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #0078d4;
                        color: #ffffff;
                        border: none;
                        border-radius: 6px;
                        text-align: left;
                        padding-left: 12px;
                    }
                    QPushButton:hover {
                        background-color: #1a8cd4;
                        color: #ffffff;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        color: #aaaaaa;
                        border: none;
                        border-radius: 6px;
                        text-align: left;
                        padding-left: 12px;
                    }
                    QPushButton:hover {
                        background-color: #3d3d3d;
                        color: #ffffff;
                    }
                """)
        if key in self.content_widgets:
            self.content_stack.setCurrentWidget(self.content_widgets[key])

    def _create_content_pages(self):
        keys = ["llm"]
        for key in keys:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            content = QWidget()
            content.setStyleSheet("background-color: #2b2b2b; border: none;")
            content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            layout = QVBoxLayout(content)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(16)

            if key == "llm":
                self._setup_llm_settings(layout)

            layout.addStretch(1)
            scroll.setWidget(content)
            self.content_widgets[key] = scroll
            self.content_stack.addWidget(scroll)

    def _setup_llm_settings(self, layout):
        from qfluentwidgets import (
            SwitchSettingCard,
            OptionsSettingCard,
        )
        from app.widgets.card_widget.provider_setting_card import (
            ProviderListSettingCard,
        )
        from app.widgets.card_widget.list_setting_card import (
            SkillListSettingCard,
        )

        self.llmGroup = QWidget()
        self.llmGroup.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        llmGroupLayout = QVBoxLayout(self.llmGroup)
        llmGroupLayout.setSpacing(10)

        group_label = StrongBodyLabel(self.tr("大模型配置"))
        group_label.setStyleSheet("color: #e0e0e0; font-size: 14px; font-weight: bold;")
        llmGroupLayout.addWidget(group_label)

        self.llmProviderCard = ProviderListSettingCard(
            icon=get_icon("大模型"),
            configItem=self.cfg.llm_saved_providers,
            defaultProviderItem=self.cfg.llm_selected_model,
            title=self.tr("已保存的服务商"),
            content=self.tr("管理已配置的大模型服务商，可选择默认使用哪个"),
            parent=self.llmGroup,
            home=self,
        )
        self.llmProviderCard.providerChanged.connect(self._on_llm_providers_changed)
        self.cfg.llm_saved_providers.valueChanged.connect(self.onConfigChanged)
        self.cfg.llm_selected_model.valueChanged.connect(self.onConfigChanged)

        self.llmSkillsCard = SkillListSettingCard(
            icon=get_icon("智能体"),
            configItem=self.cfg.llm_enabled_skills,
            title=self.tr("启用技能"),
            content=self.tr(
                "选择要在系统提示词中注入的技能，提高大模型使用这些技能的频率"
            ),
            parent=self.llmGroup,
            home=self,
        )
        self.llmSkillsCard.skillsChanged.connect(self.onConfigChanged)

        self.llmNotifyCard = SwitchSettingCard(
            get_icon("提示"),
            self.tr("智能体完成通知"),
            self.tr("大模型回复或需要回答问题时，如果窗口不在前台则发送通知"),
            configItem=self.cfg.llm_notify_enabled,
            parent=self.llmGroup,
        )
        self.cfg.llm_notify_enabled.valueChanged.connect(self.onConfigChanged)

        self.llmSoundCard = OptionsSettingCard(
            self.cfg.llm_notify_sound,
            get_icon("提示"),
            self.tr("通知提示音"),
            self.tr("选择收到通知时的提示音"),
            texts=[self.tr("默认提示音"), self.tr("短提示音"), self.tr("无提示音")],
            parent=self.llmGroup,
        )
        self.llmSoundCard.optionChanged.connect(self.onConfigChanged)

        # API 服务开关
        self.llmApiEnabledCard = SwitchSettingCard(
            get_icon("API"),
            self.tr("启用 API 服务"),
            self.tr("开启后可通过 HTTP 接口远程调用 LLM 对话功能，文档地址：http://localhost:{}/docs".format(self.cfg.llm_api_port.value)),
            configItem=self.cfg.llm_api_enabled,
            parent=self.llmGroup,
        )
        self.cfg.llm_api_enabled.valueChanged.connect(self._on_llm_api_enabled_changed)
        self.cfg.llm_api_port.valueChanged.connect(self._on_llm_api_port_changed)

        # 端口号设置
        self.llmApiPortCard = self._create_port_setting_card(
            self.tr("API 服务端口"),
            self.tr("设置 API 服务的监听端口（1024-65535）"),
            self.llmGroup,
        )

        llmGroupLayout.addWidget(self.llmProviderCard)
        llmGroupLayout.addWidget(self.llmSkillsCard)
        llmGroupLayout.addWidget(self.llmNotifyCard)
        llmGroupLayout.addWidget(self.llmSoundCard)
        llmGroupLayout.addWidget(self.llmApiEnabledCard)
        llmGroupLayout.addWidget(self.llmApiPortCard)
        layout.addWidget(self.llmGroup)

    def _create_port_setting_card(self, title, content, parent=None):
        """创建端口设置卡片"""
        from qfluentwidgets import SettingCard

        class PortSettingCard(SettingCard):
            def __init__(self, title, content, cfg, parent=None):
                super().__init__(FluentIcon.INFO, title, content, parent)
                self.cfg = cfg

                self.spinBox = QSpinBox()
                self.spinBox.setFixedWidth(100)
                self.spinBox.setRange(1024, 65535)
                self.spinBox.setValue(cfg.llm_api_port.value)
                self.spinBox.valueChanged.connect(self._on_value_changed)

                self.hBoxLayout.addWidget(self.spinBox)
                self.hBoxLayout.addSpacing(16)

            def _on_value_changed(self, value):
                self.cfg.set(self.cfg.llm_api_port, value, save=True)
                # 更新 API 服务开关卡片的描述
                if hasattr(self.parent(), 'llmApiEnabledCard'):
                    self.parent().llmApiEnabledCard.setContent(
                        self.tr("开启后可通过 HTTP 接口远程调用 LLM 对话功能，文档地址：http://localhost:{}/docs".format(value))
                    )

        card = PortSettingCard(title, content, self.cfg, parent)
        return card

    def _on_llm_api_enabled_changed(self, enabled):
        """API 服务开关变化时启动/停止服务"""
        from app.llm_chatter.api import (
            start_llm_api_service,
            stop_llm_api_service,
            is_service_running,
            get_llm_api_service,
        )

        if enabled:
            if not is_service_running():
                service = get_llm_api_service()
                service.port = self.cfg.llm_api_port.value
                service.start(background=True)
        else:
            if is_service_running():
                stop_llm_api_service()
        self.onConfigChanged()

    def _on_llm_api_port_changed(self, port):
        """端口变化时，如果服务正在运行则重启服务"""
        from app.llm_chatter.api import (
            start_llm_api_service,
            stop_llm_api_service,
            is_service_running,
            get_llm_api_service,
        )

        if self.cfg.llm_api_enabled.value and is_service_running():
            # 停止旧服务
            stop_llm_api_service()
            # 用新端口启动服务
            service = get_llm_api_service()
            service.port = port
            service.start(background=True)
        # 更新 API 服务开关卡片的描述
        if hasattr(self, 'llmApiEnabledCard'):
            self.llmApiEnabledCard.setContent(
                self.tr("开启后可通过 HTTP 接口远程调用 LLM 对话功能，文档地址：http://localhost:{}/docs".format(port))
            )

    def _on_llm_providers_changed(self, providers: dict):
        self.configChanged.emit()
        self._save_timer.start()

    def onConfigChanged(self):
        self.configChanged.emit()
        self._save_timer.start()

    def _perform_save_to_disk(self):
        try:
            self.cfg.save_config()
        except Exception as e:
            print(f"保存配置失败: {e}")

    def enterEvent(self, event):
        super().enterEvent(event)
        self._remove_event_filter()

    def leaveEvent(self, event):
        self._install_event_filter()
        super().leaveEvent(event)

    def _install_event_filter(self):
        if not self._event_filter_installed:
            QApplication.instance().installEventFilter(self)
            self._event_filter_installed = True

    def _remove_event_filter(self):
        if self._event_filter_installed:
            QApplication.instance().removeEventFilter(self)
            self._event_filter_installed = False

    def _is_widget_in_dialog_tree(self, widget) -> bool:
        """检查 widget 是否在 SettingDialog 的窗口树中（包括子对话框和弹出列表）"""
        if widget is None:
            return False
        
        if widget == self:
            return True
        
        current = widget
        while current:
            if current == self:
                return True
            if isinstance(current, QDialog) and current.isVisible():
                parent = current.parent()
                while parent:
                    if parent == self:
                        return True
                    parent = parent.parent()
            current = current.parent()
        
        return False

    def _is_combobox_popup(self, widget) -> bool:
        """检查 widget 是否是 QComboBox 相关的弹出列表"""
        if widget is None:
            return False
        
        if isinstance(widget, QComboBox):
            return True
        
        current = widget.parent() if hasattr(widget, 'parent') else None
        while current:
            if isinstance(current, QComboBox):
                return True
            current = current.parent() if hasattr(current, 'parent') else None
        
        class_name = widget.metaObject().className() if hasattr(widget, 'metaObject') else ''
        if 'Completer' in class_name or 'Popup' in class_name:
            if hasattr(widget, 'parent') and widget.parent():
                return self._is_combobox_popup(widget.parent())
        
        return False

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            if not self.geometry().contains(event.globalPos()):
                target = QApplication.widgetAt(event.globalPos())
                
                if self._is_widget_in_dialog_tree(target):
                    return super().eventFilter(obj, event)
                
                if self._is_combobox_popup(target):
                    return super().eventFilter(obj, event)
                
                self.hidePopup()
                return False
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        super().showEvent(event)
        self._install_event_filter()

    def hideEvent(self, event):
        self._remove_event_filter()
        super().hideEvent(event)

    def show_at_left(self, parent_widget, button_top_right):
        self._parent_widget = parent_widget
        self._follow_window = False

        self.resize(950, 700)
        self.move(
            (QApplication.desktop().screenGeometry().width() - self.width()) // 2,
            (QApplication.desktop().screenGeometry().height() - self.height()) // 2,
        )
        self.show()
        self.activateWindow()

    def _update_position(self, parent_widget):
        if not self._follow_window or not self.isVisible():
            return

        nav_interface = parent_widget.navigationInterface
        nav_right = nav_interface.rect().right()
        nav_right_global = nav_interface.mapToGlobal(QPoint(nav_right, 0))
        x = nav_right_global.x() + 5

        parent_global_y = parent_widget.mapToGlobal(QPoint(0, 0)).y()
        y = parent_global_y

        popup_height = parent_widget.height()
        screen = QApplication.desktop().screenGeometry(parent_widget)
        if y + popup_height > screen.bottom():
            popup_height = screen.bottom() - y - 10

        self.move(x, y)
        self.resize(self.width(), popup_height)

    def hidePopup(self):
        self._follow_window = False
        self._remove_event_filter()
        self.hide()

    def deleteLater(self):
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._perform_save_to_disk()
        self._remove_event_filter()
        super().deleteLater()
