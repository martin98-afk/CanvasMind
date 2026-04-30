# -*- coding: utf-8 -*-
"""
大模型设置卡片 - 垂直列表布局，高度不够滚动
"""
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QFontDatabase
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QFontComboBox,
    QComboBox,
)
from qfluentwidgets import (
    CardWidget,
    StrongBodyLabel,
    BodyLabel,
    SwitchSettingCard,
    OptionsSettingCard,
    SettingCard,
    FluentIcon,
)
from app.utils.utils import get_icon, get_unified_font
from app.utils.config import Settings


class LLMSettingsCard(CardWidget):
    """大模型设置卡片 - 垂直列表布局"""

    closed = pyqtSignal()
    configChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = Settings.get_instance()
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._perform_save)

        self._setup_ui()

    def _setup_ui(self):
        self.setSizePolicy(1, 0)  # 水平方向可扩展
        self.setFixedHeight(350)  # 固定高度，超出滚动
        self.setStyleSheet("""
            CardWidget {
                background-color: rgba(33, 33, 38, 250);
                border: 1px solid #3d3d3d;
                border-radius: 8px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(4)

        # 头部
        header = QHBoxLayout()
        header.setSpacing(8)

        icon_label = QLabel("⚙️", self)
        icon_label.setFont(get_unified_font(12))

        title_label = StrongBodyLabel("系统设置", self)
        title_label.setFont(get_unified_font(11, True))
        title_label.setStyleSheet("color: #f59e0b;")

        header.addWidget(icon_label)
        header.addWidget(title_label)
        header.addStretch()

        # 关闭按钮
        self.close_btn = QLabel("✕", self)
        self.close_btn.setFont(get_unified_font(11))
        self.close_btn.setStyleSheet("color: #888888; cursor: pointer; padding: 4px;")
        self.close_btn.mousePressEvent = lambda e: self._on_close()
        header.addWidget(self.close_btn)

        main_layout.addLayout(header)

        # 内容区域 - 使用 ScrollArea
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 6px;
                margin: 2px 2px 2px 2px;
            }
            QScrollBar::handle:vertical {
                background: #555555;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #666666;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 4, 0, 4)
        content_layout.setSpacing(6)

        # 已保存的服务商
        from app.widgets.card_widget.provider_setting_card import ProviderListSettingCard
        self.llmProviderCard = ProviderListSettingCard(
            icon=get_icon("大模型"),
            configItem=self.cfg.llm_saved_providers,
            defaultProviderItem=self.cfg.llm_selected_model,
            title="已保存的服务商",
            content="管理已配置的大模型服务商",
            parent=self,
            home=self,
        )
        content_layout.addWidget(self.llmProviderCard)

        # 启用技能
        from app.widgets.card_widget.list_setting_card import SkillListSettingCard
        self.llmSkillsCard = SkillListSettingCard(
            icon=get_icon("智能体"),
            configItem=self.cfg.llm_enabled_skills,
            title="启用技能",
            content="选择要注入的技能",
            parent=self,
            home=self,
        )
        content_layout.addWidget(self.llmSkillsCard)

        # 全局字体设置
        self._setup_font_card()
        content_layout.addWidget(self.llmFontCard)

        # 智能体完成通知
        self.llmNotifyCard = SwitchSettingCard(
            get_icon("提示"),
            "智能体完成通知",
            "窗口不在前台时发送通知",
            configItem=self.cfg.llm_notify_enabled,
            parent=self,
        )
        content_layout.addWidget(self.llmNotifyCard)

        # 通知提示音
        self.llmSoundCard = OptionsSettingCard(
            self.cfg.llm_notify_sound,
            get_icon("提示"),
            "通知提示音",
            "选择提示音",
            texts=["默认", "短提示音", "无"],
            parent=self,
        )
        content_layout.addWidget(self.llmSoundCard)

        # # API 服务开关
        # self.llmApiEnabledCard = SwitchSettingCard(
        #     get_icon("API"),
        #     "启用 API 服务",
        #     f"http://localhost:{self.cfg.llm_api_port.value}/docs",
        #     configItem=self.cfg.llm_api_enabled,
        #     parent=self,
        # )
        # content_layout.addWidget(self.llmApiEnabledCard)
        #
        # # 端口号设置
        # self._setup_port_card()
        # content_layout.addWidget(self.llmApiPortCard)

        content_layout.addStretch(1)
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll, 1)

        # 连接信号
        self.llmProviderCard.providerChanged.connect(self._on_config_changed)
        self.llmSkillsCard.skillsChanged.connect(self._on_config_changed)
        self.cfg.llm_notify_enabled.valueChanged.connect(self._on_config_changed)
        self.llmSoundCard.optionChanged.connect(self._on_config_changed)
        self.cfg.llm_font_family.valueChanged.connect(self._on_config_changed)
        self.cfg.llm_api_enabled.valueChanged.connect(self._on_llm_api_enabled_changed)
        self.cfg.llm_api_port.valueChanged.connect(self._on_llm_api_port_changed)

    def _setup_font_card(self):
        """创建字体设置卡片"""
        from qfluentwidgets import SettingCard

        class FontSettingCard(SettingCard):
            def __init__(self, title, content, cfg, parent=None):
                super().__init__(FluentIcon.FONT, title, content, parent)
                self.cfg = cfg
                self._parent = parent

                self.fontCombo = QFontComboBox()
                self.fontCombo.setMinimumWidth(200)
                self.fontCombo.setStyleSheet("""
                    QFontComboBox {
                        color: #e0e0e0;
                        background-color: #3d3d3d;
                        border: 1px solid #555555;
                        border-radius: 4px;
                        padding: 4px 10px;
                        min-height: 26px;
                        selection-background-color: #0078d4;
                    }
                    QFontComboBox:hover {
                        border: 1px solid #0078d4;
                    }
                    QFontComboBox::drop-down {
                        border: none;
                        width: 24px;
                    }
                    QFontComboBox QAbstractItemView {
                        color: #e0e0e0;
                        background-color: #2d2d2d;
                        border: 1px solid #555555;
                        selection-background-color: #0078d4;
                        selection-color: #ffffff;
                        outline: none;
                    }
                """)
                # 设置当前字体
                current_font = cfg.llm_font_family.value
                self.fontCombo.setCurrentFont(QFont(current_font))
                self.fontCombo.currentFontChanged.connect(self._on_font_changed)

                self.hBoxLayout.addWidget(self.fontCombo)
                self.hBoxLayout.addSpacing(16)

            def _on_font_changed(self, font):
                self.cfg.set(self.cfg.llm_font_family, font.family(), save=True)
                self.cfg.save()
                # 通知父级配置变化
                if self._parent and hasattr(self._parent, '_on_config_changed'):
                    self._parent._on_config_changed()

        self.llmFontCard = FontSettingCard(
            "全局字体",
            "设置界面显示字体",
            self.cfg,
            self,
        )

    def _setup_port_card(self):
        """创建端口设置卡片"""
        from qfluentwidgets import SettingCard, SpinBox
        from qfluentwidgets import FluentIcon

        class PortSettingCard(SettingCard):
            def __init__(self, title, content, cfg, parent=None):
                super().__init__(FluentIcon.INFO, title, content, parent)
                self.cfg = cfg

                self.spinBox = SpinBox()
                self.spinBox.setFixedWidth(100)
                self.spinBox.setRange(1024, 65535)
                self.spinBox.setValue(cfg.llm_api_port.value)
                self.spinBox.valueChanged.connect(self._on_value_changed)

                self.hBoxLayout.addWidget(self.spinBox)
                self.hBoxLayout.addSpacing(16)

            def _on_value_changed(self, value):
                self.cfg.set(self.cfg.llm_api_port, value, save=True)
                # 更新 API 服务开关卡片的描述
                parent = self.parent()
                while parent and not hasattr(parent, 'llmApiEnabledCard'):
                    parent = parent.parent()
                if parent and hasattr(parent, 'llmApiEnabledCard'):
                    parent.llmApiEnabledCard.setContent(
                        f"http://localhost:{value}/docs"
                    )

        self.llmApiPortCard = PortSettingCard(
            "API 端口",
            "设置 API 服务端口（1024-65535）",
            self.cfg,
            self,
        )

    def _on_close(self):
        self.setVisible(False)
        self.closed.emit()

    def _on_config_changed(self):
        self.configChanged.emit()
        self._save_timer.start()

    def _perform_save(self):
        try:
            self.cfg.save_config()
        except Exception as e:
            print(f"保存配置失败: {e}")

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
        self._on_config_changed()

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
                f"http://localhost:{port}/docs"
            )

    def show(self):
        self.setVisible(True)
        self.raise_()

    def hide(self):
        self.setVisible(False)