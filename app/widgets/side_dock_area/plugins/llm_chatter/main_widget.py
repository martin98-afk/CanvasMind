# -*- coding: utf-8 -*-
import json
import re
from datetime import datetime
from typing import Optional, Dict, Any, List

from PyQt5.QtCore import (
    Qt,
    QTimer,
    pyqtSignal,
    QThreadPool,
)
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QApplication,
    QWidget,
    QFileDialog,
)
from loguru import logger
from qfluentwidgets import (
    setFont,
    ComboBox,
    FluentIcon,
    SingleDirectionScrollArea,
    InfoBar,
    InfoBarPosition,
    CardWidget,
    CaptionLabel,
    TransparentToolButton,
    TransparentToggleToolButton,
)

from app.utils.config import Settings
from app.utils.utils import get_icon
from app.widgets.side_dock_area.plugins.llm_chatter.constants import (
    FREE_PROVIDERS,
    PROVIDER_ICONS,
)
from app.widgets.side_dock_area.plugins.llm_chatter.core import (
    ChatEngine,
    ToolExecutor,
    MemoryManagerCore,
)
from app.widgets.side_dock_area.plugins.llm_chatter.core.agent import AgentManager
from app.widgets.side_dock_area.plugins.llm_chatter.utils.chat_session import (
    SessionManager,
    ChatSession,
)
from app.widgets.side_dock_area.plugins.llm_chatter.utils.history_manager import (
    HistoryManager,
)
from app.widgets.side_dock_area.plugins.llm_chatter.utils.worker import (
    TitleGenerationTask,
    TopicSummaryTask,
    ShellExecutionTask,
)
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.bottom_input_area import (
    SendableTextEdit,
)
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.context_selector import (
    ContextSelector,
)
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.conversation_node_preview import (
    ConversationNodePreview,
)
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.llm_config_popup import (
    LLMConfigPopup,
)
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.memory_manager import (
    MemoryManagerDialog,
)
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.message_card import (
    MessageCard,
    create_welcome_card,
)
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.question_floating_widget import (
    QuestionFloatingWidget,
)
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.render_helpers import (
    render_tool_block,
    format_tool_block,
)
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.todo_floating_widget import (
    TodoFloatingWidget,
)
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.sub_agent_floating_widget import (
    SubAgentFloatingWidget,
)
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.tool_floating_widget import (
    ToolFloatingWidget,
)
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class OpenAIChatToolWindow(ToolWindow):
    name = "大模型对话"
    icon = get_icon("大模型")
    singleton = True
    default_position = DockPosition.BOTTOM
    session_manager = SessionManager()
    _valid_configs: Dict[str, Dict[str, Any]] = {}
    history_manager = None
    _agent_manager: Optional[AgentManager] = None
    _current_agent: str = "plan"
    _in_history_mode = False
    _current_history_index: Optional[int] = None
    _settings_popup = None
    _is_welcome = False
    _first_show = False
    _is_searching = False
    _search_results: List[int] = []
    _current_search_index: int = -1
    _loaded_skill_doc: str = ""
    _skill_enabled: bool = True
    _is_shell_mode: bool = False
    _chat_engine: Optional[ChatEngine] = None
    _tool_executor: Optional[ToolExecutor] = None
    _memory_manager: Optional[MemoryManagerCore] = None
    _is_continuing: bool = False
    _processed_tool_ids: set = set()
    _current_assistant_card = None
    _tool_call_depth: int = 0
    _pending_tool_calls: int = 0
    _first_tool_result: bool = True
    _todo_floating_widget = None
    _question_floating_widget = None
    _question_tool_call_id = None
    _history_preview_session_data: Optional[dict] = None
    _history_preview_history_index: Optional[int] = None
    _history_preview_opening: bool = False
    _history_preview_messages: Optional[List[dict]] = None
    _history_preview_title: str = ""
    insertResponse = pyqtSignal(str)
    createResponse = pyqtSignal(str)
    contextActionRequested = pyqtSignal(str, str)
    skillExecutionRequested = pyqtSignal(str, dict)
    userInterventionRequested = pyqtSignal(dict)
    executionResultProduced = pyqtSignal(str)
    toolStartUiSyncRequested = pyqtSignal(str, str, object, str)

    def __init__(self, homepage, button):
        super().__init__(homepage, button)
        self._gen_thread_pool = QThreadPool()
        self._gen_thread_pool.setMaxThreadCount(2)
        self.toolStartUiSyncRequested.connect(
            self._handle_tool_start_ui_sync, type=Qt.BlockingQueuedConnection
        )
        self.homepage = homepage
        self._is_streaming = False
        self.session_manager.create_new_session()
        if hasattr(self.homepage, "global_variables_changed"):
            self.homepage.global_variables_changed.connect(self._load_model_configs)
        self._initialize_managers()

    def _initialize_managers(self):
        """初始化核心管理器"""
        canvas_name = getattr(self.homepage, "workflow_name", "default") or "default"

        self._memory_manager = MemoryManagerCore(canvas_name)
        self._tool_executor = ToolExecutor(self.homepage)
        self._agent_manager = AgentManager()

        from app.widgets.side_dock_area.plugins.llm_chatter.core.sub_agent_executor import (
            SubAgentManager,
        )

        self._sub_agent_manager = SubAgentManager(
            agent_manager=self._agent_manager,
            tool_executor=self._tool_executor,
            get_llm_config=self._get_current_model_config,
        )
        self._tool_executor.set_sub_agent_manager(self._sub_agent_manager)

        self._chat_engine = ChatEngine(
            session_manager=self.session_manager,
            get_model_config=self._get_current_model_config,
            get_context_provider=lambda: self.context_selector,
            tool_executor=self._tool_executor,
            agent_manager=self._agent_manager,
            get_chat_cards=self._get_chat_cards_for_engine,
            get_memory_context=lambda: self._memory_manager.get_context_string()
            if self._memory_manager
            else "",
        )

        self._chat_engine.set_callback("content_received", self._on_content_received)
        self._chat_engine.set_callback("tool_call_started", self._on_tool_call_started)
        self._chat_engine.set_callback(
            "tool_call_sync_requested", self._request_tool_start_ui_sync
        )
        self._chat_engine.set_callback(
            "tool_result_received", self._on_tool_result_received
        )
        self._chat_engine.set_callback("stream_started", self._on_stream_started)
        self._chat_engine.set_callback("stream_finished", self._on_stream_finished)
        self._chat_engine.set_callback("error", self._on_engine_error)
        self._chat_engine.set_callback(
            "user_message_added", self._on_user_message_added
        )
        self._chat_engine.set_callback("skill_requested", self._on_skill_requested)
        self._chat_engine.set_callback(
            "shell_command_requested", self._on_shell_command_requested
        )
        self._chat_engine.set_callback("question_asked", self._on_question_asked)
        self._chat_engine.set_callback("agent_switched", self._on_agent_switched)
        self._chat_engine.set_callback(
            "task_state_changed", self._on_task_state_changed
        )

        self._initialize_history_manager()

    def _request_tool_start_ui_sync(
        self, tool_call_id: str, tool_name: str, arguments: dict, round_id: str = None
    ):
        self.toolStartUiSyncRequested.emit(
            tool_call_id, tool_name, arguments or {}, round_id or ""
        )

    def _handle_tool_start_ui_sync(
        self, tool_call_id: str, tool_name: str, arguments: object, round_id: str
    ):
        self._on_tool_call_started(tool_call_id, tool_name, arguments or {}, round_id)
        QApplication.sendPostedEvents()
        if self._tool_floating_widget:
            self._tool_floating_widget.repaint()
        self.repaint()
        QApplication.processEvents()

    def _get_chat_cards_for_engine(self):
        cards = []
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, MessageCard):
                    cards.append(widget)
        return cards

    def _get_current_model_config(self) -> Dict[str, Any]:
        """获取当前选中的模型配置"""
        selected_name = (
            self.model_combo.currentText()
            if hasattr(self, "model_combo")
            else "系统默认配置"
        )
        return self._valid_configs.get(selected_name, {})

    def showEvent(self, event):
        if not self._first_show:
            self._first_show = True
            QTimer.singleShot(0, lambda: self._create_new_session())
        super().showEvent(event)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.setStyleSheet("""
            OpenAIChatToolWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(10, 14, 22, 255),
                    stop:1 rgba(15, 20, 30, 255));
            }
        """)

        session_bar_layout = QHBoxLayout()
        session_bar_layout.setContentsMargins(0, 0, 0, 0)
        session_bar_layout.setSpacing(4)

        left_layout = QHBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self.title_edit = QLabel("新对话", self)
        self.title_edit.setStyleSheet("""
            QLabel {
                color: #f3f6fc;
                font-size: 15px;
                font-weight: bold;
                padding: 6px 10px;
                border-radius: 10px;
                background-color: rgba(255, 255, 255, 0.03);
            }
            QLabel:hover {
                background-color: rgba(255, 255, 255, 0.06);
            }
        """)
        self.title_edit.setCursor(Qt.PointingHandCursor)
        self.title_edit.mouseDoubleClickEvent = self._on_title_double_click
        left_layout.addWidget(self.title_edit)

        self.menu_btn = TransparentToolButton(FluentIcon.MORE, self)
        self.menu_btn.setFixedSize(26, 26)
        self.menu_btn.setToolTip("更多操作")
        self._create_context_menu()
        left_layout.addWidget(self.menu_btn)

        right_layout = QHBoxLayout()

        model_label = QLabel("模型：", self)
        setFont(model_label, 12, QFont.Bold)
        model_label.setStyleSheet("color: #ffffff;")
        right_layout.addWidget(model_label)

        self.model_combo = ComboBox(self)
        self._load_model_configs()
        setFont(self.model_combo, 12)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        right_layout.addWidget(self.model_combo)
        self.settings_btn = TransparentToolButton(FluentIcon.SETTING, self)
        self.settings_btn.setToolTip("模型设置")
        self.settings_btn.clicked.connect(self._open_settings_popup)
        right_layout.addWidget(self.settings_btn)

        session_bar_layout.addLayout(left_layout)
        session_bar_layout.addStretch()
        session_bar_layout.addLayout(right_layout)
        layout.addLayout(session_bar_layout)

        self._todo_floating_widget = TodoFloatingWidget(self)
        self._todo_floating_widget.setVisible(False)
        layout.addWidget(self._todo_floating_widget)

        self._sub_agent_floating_widget = SubAgentFloatingWidget(self)
        self._sub_agent_floating_widget.setVisible(False)
        layout.addWidget(self._sub_agent_floating_widget)

        self._tool_floating_widget = ToolFloatingWidget(self)
        self._tool_floating_widget.setVisible(False)
        self._tool_floating_widget.cancelled.connect(self._on_tool_cancelled)
        layout.addWidget(self._tool_floating_widget)

        self.chat_scroll_area = SingleDirectionScrollArea(self)
        self.chat_scroll_area.setMinimumWidth(400)
        self.chat_scroll_area.setStyleSheet(
            """
            SingleDirectionScrollArea {
                background-color: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.04);
                border-radius: 18px;
            }
            """
        )
        self.chat_scroll_area.setWidgetResizable(True)
        self.chat_scroll_area.setViewportMargins(2, 2, 10, 2)

        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background: transparent;")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(8, 8, 8, 8)
        self.chat_layout.setSpacing(8)
        self.chat_layout.setAlignment(Qt.AlignBottom)
        self.chat_scroll_area.setWidget(self.chat_container)

        layout.addWidget(self.chat_scroll_area, 1)

        self.node_preview = ConversationNodePreview(self)
        self.node_preview.nodeClicked.connect(self._on_node_preview_clicked)
        layout.addWidget(self.node_preview)

        self.chat_scroll_area.verticalScrollBar().valueChanged.connect(
            self._on_scroll_changed
        )

        self._question_floating_widget = QuestionFloatingWidget(self)
        self._question_floating_widget.setVisible(False)
        self._question_floating_widget.answered.connect(self._on_question_answered)
        self._question_floating_widget.cancelled.connect(self._on_question_cancelled)
        layout.addWidget(self._question_floating_widget)

        hlayout = QHBoxLayout()
        hlayout.setContentsMargins(0, 0, 0, 0)
        hlayout.setSpacing(0)
        self.context_selector = ContextSelector(self)
        hlayout.addWidget(self.context_selector)
        hlayout.addStretch(1)

        self.new_session_btn = TransparentToolButton(FluentIcon.ADD, self)
        self.new_session_btn.setFixedSize(26, 26)
        self.new_session_btn.setToolTip("新建对话")
        self.new_session_btn.clicked.connect(self._create_new_session)

        self.memory_btn = TransparentToolButton(get_icon("长期记忆"), self)
        self.memory_btn.setFixedSize(26, 26)
        self.memory_btn.setToolTip("长期记忆管理")
        self.memory_btn.clicked.connect(self._show_soul_memory)

        self.history_btn = TransparentToggleToolButton(FluentIcon.HISTORY, self)
        self.history_btn.setFixedSize(26, 26)
        self.history_btn.setToolTip("历史对话")
        self.history_btn.toggled.connect(self._toggle_history_mode)

        self.shell_btn = TransparentToggleToolButton(get_icon("shell"), self)
        self.shell_btn.setFixedSize(26, 26)
        self.shell_btn.setToolTip("Shell执行模式")
        self.shell_btn.toggled.connect(self._toggle_shell_mode)

        hlayout.addWidget(self.shell_btn)
        hlayout.addWidget(self.memory_btn)
        hlayout.addWidget(self.history_btn)
        hlayout.addWidget(self.new_session_btn)

        layout.addLayout(hlayout)

        self.input_area = SendableTextEdit(self)
        self.input_area.setMaximumHeight(108)
        setFont(self.input_area, 15)
        self.input_area.sendMessageRequested.connect(self._on_send_clicked)
        self.input_area.stopMessageRequested.connect(self._on_stop_clicked)
        self.input_area.clearRequested.connect(self._on_clear_shortcut)
        self.input_area.newSessionRequested.connect(self._create_new_session)
        self.input_area.agentChanged.connect(self._on_agent_changed)
        layout.addWidget(self.input_area)

        self._load_agent_list()

    def _on_model_changed(self, model_name: str):
        if model_name:
            setting = Settings.get_instance()
            setting.set(setting.llm_selected_model, model_name, save=True)

    def _open_settings_popup(self):
        if self._settings_popup is None:
            self._settings_popup = LLMConfigPopup(parent=self)
            self._settings_popup.configApplied.connect(self._on_config_applied)

        current_name = self.model_combo.currentText()
        if current_name in self._valid_configs:
            config = self._valid_configs[current_name].copy()
        else:
            setting = Settings.get_instance()
            config = {
                "模型名称": setting.llm_model.value,
                "API_KEY": setting.llm_api_key.value,
                "API_URL": setting.llm_api_base.value,
                "最大Token": setting.llm_max_tokens.value,
                "温度": setting.llm_temperature.value,
                "是否思考": setting.llm_enable_thinking.value,
            }

        self._settings_popup.set_config(self.model_combo.currentText(), config)
        self._settings_popup.show_at(self.settings_btn)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), MessageCard):
                item.widget().sync_width()

    def _on_config_applied(self, new_config: dict):
        current_name = self.model_combo.currentText()
        is_free_provider = current_name in FREE_PROVIDERS

        if current_name == "系统默认配置":
            setting = Settings.get_instance()
            setting.set(setting.llm_model, new_config["模型名称"])
            setting.set(setting.llm_api_key, new_config["API_KEY"])
            setting.set(setting.llm_api_base, new_config["API_URL"])
            setting.set(setting.llm_max_tokens, new_config["最大Token"])
            setting.set(setting.llm_temperature, new_config["温度"])
            setting.set(setting.llm_enable_thinking, new_config["是否思考"])
            setting.save_config()
            self._load_model_configs()
            InfoBar.success(
                "系统默认配置已更新", "已保存到系统配置。", parent=self, duration=1500
            )
        elif is_free_provider:
            self._valid_configs[current_name] = new_config
            setting = Settings.get_instance()
            saved_providers = setting.llm_saved_providers.value or {}
            saved_providers[current_name] = new_config
            setting.set(setting.llm_saved_providers, saved_providers, save=True)
            InfoBar.success("已保存", "配置已保存到本地。", parent=self, duration=1500)
        else:
            if (
                hasattr(self.homepage, "global_variables")
                and self.homepage.global_variables
            ):
                custom_vars = self.homepage.global_variables.custom
                if current_name in custom_vars:
                    custom_vars[current_name].value = new_config
                    self.homepage._on_global_variables_changed(
                        "custom", current_name, "update"
                    )
                else:
                    from app.components.base import CustomVariable

                    custom_vars[current_name] = CustomVariable(value=new_config)
                    self.homepage._on_global_variables_changed(
                        "custom", current_name, "add"
                    )
                self._load_model_configs()
                idx = self.model_combo.findText(current_name)
                if idx >= 0:
                    self.model_combo.setCurrentIndex(idx)
                InfoBar.success(
                    "已保存", "配置已保存到自定义配置。", parent=self, duration=1500
                )
            else:
                InfoBar.warning(
                    "无法保存",
                    "当前页面不支持保存自定义配置。",
                    parent=self,
                    duration=1500,
                )

    def _load_model_configs(self):
        setting = Settings.get_instance()
        saved_model = setting.llm_selected_model.value

        current_text = (
            self.model_combo.currentText() if self.model_combo.count() > 0 else ""
        )

        self._valid_configs.clear()
        self.model_combo.clear()

        setting = Settings.get_instance()
        default_config = {
            "模型名称": setting.llm_model.value,
            "API_KEY": setting.llm_api_key.value,
            "API_URL": setting.llm_api_base.value,
            "最大Token": setting.llm_max_tokens.value,
            "温度": setting.llm_temperature.value,
            "是否思考": setting.llm_enable_thinking.value,
        }
        self._valid_configs["系统默认配置"] = default_config

        all_model_names = ["系统默认配置"]

        try:
            custom_vars = getattr(self.homepage, "global_variables", None)
            if custom_vars and hasattr(custom_vars, "custom"):
                for config_name, var_obj in custom_vars.custom.items():
                    if hasattr(var_obj, "value") and isinstance(var_obj.value, dict):
                        val = var_obj.value
                        if {"API_URL", "API_KEY", "模型名称"}.issubset(val.keys()):
                            if config_name != "系统默认配置":
                                self._valid_configs[config_name] = val
                                all_model_names.append(config_name)
        except Exception as e:
            logger.error(f"[ERROR] 加载自定义模型配置失败: {e}")

        setting = Settings.get_instance()
        saved_providers = setting.llm_saved_providers.value or {}

        for provider_name, provider_config in FREE_PROVIDERS.items():
            if provider_name not in self._valid_configs:
                if provider_name in saved_providers:
                    config = saved_providers[provider_name].copy()
                else:
                    config = provider_config.copy()
                    config.pop("备注", None)
                    config.pop("认证方式", None)
                    config.pop("获取地址", None)
                self._valid_configs[provider_name] = config
                all_model_names.append(provider_name)

        self._setup_combo_with_icons(all_model_names)
        self.model_combo.setDisabled(len(all_model_names) == 0)

        saved_model = setting.llm_selected_model.value
        if saved_model and saved_model in self._valid_configs:
            idx = self.model_combo.findText(saved_model)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
        elif current_text in self._valid_configs:
            idx = self.model_combo.findText(current_text)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
        elif self.model_combo.count() > 0:
            self.model_combo.setCurrentIndex(0)

    def _setup_combo_with_icons(self, model_names: List[str]):
        self.model_combo.clear()
        for name in model_names:
            if name in PROVIDER_ICONS:
                icon_name = PROVIDER_ICONS.get(name, "API")
                icon = get_icon(icon_name)
                self.model_combo.addItem(icon=icon, text=name)
            else:
                self.model_combo.addItem(name)

    def _load_agent_list(self):
        """加载智能体列表到选择器"""
        if not self._agent_manager or not hasattr(self, "input_area"):
            return
        self._suppress_agent_intro = True
        agents = self._agent_manager.list_agents()
        self.input_area._agent_combo.clear()
        for agent in agents:
            self.input_area._agent_combo.addItem(agent.name, agent.description)
        if self.input_area._agent_combo.count() > 0:
            self.input_area._agent_combo.setCurrentIndex(0)
            self._current_agent = self.input_area._agent_combo.currentText()
        self._suppress_agent_intro = False

    def _on_agent_changed(self, agent_name: str):
        """智能体切换处理"""
        if not agent_name or not self._chat_engine:
            return
        self._current_agent = agent_name
        self._chat_engine.switch_agent(agent_name)
        self._update_agent_status(agent_name)
        if not getattr(self, "_suppress_agent_intro", False):
            self._show_agent_intro(agent_name)

    def _show_agent_intro(self, agent_name: str):
        """显示智能体介绍卡片"""
        if not self._agent_manager:
            return
        agent = self._agent_manager.get_agent(agent_name)
        if not agent:
            return

        intro_md = f"""\
### 🤖 已切换到智能体：{agent.name}

{agent.description}

"""
        card = MessageCard(parent=self, role="assistant", timestamp="系统")
        card.update_content(intro_md)
        card.finish_streaming()
        self._add_chat_widget(card)
        self._scroll_to_bottom()

    def _update_agent_status(self, agent_name: str):
        """更新智能体状态显示"""
        if not self._agent_manager or not hasattr(self, "input_area"):
            return
        agent = self._agent_manager.get_agent(agent_name)
        if agent:
            tools_count = len(agent.tools) if agent.tools else 0
            self.input_area._agent_combo.setToolTip(
                f"{agent.name}: {agent.description}\n可用工具: {tools_count}个"
            )

    def _on_task_state_changed(self, task_state):
        if not task_state:
            return
        self._latest_task_state = task_state

    def _suggest_agent(self, user_text: str) -> Optional[str]:
        """基于用户输入智能推荐合适的智能体"""
        if not user_text or not self._agent_manager:
            return None

        text_lower = user_text.lower()

        agent_keywords = {
            "web-developer": [
                "html",
                "css",
                "javascript",
                "react",
                "vue",
                "angular",
                "node",
                "前端",
                "后端",
                "网站",
                "网页",
                "http",
                "api",
                "npm",
                "webpack",
                "vite",
                "浏览器",
                "样式",
                "组件",
                "前端开发",
                "后端开发",
            ],
            "python-reviewer": [
                "python",
                "py",
                "django",
                "flask",
                "fastapi",
                "爬虫",
                "数据分析",
                "机器学习",
                "ai",
                "模型",
                "算法",
                "函数",
                "类",
                "代码审查",
                "优化",
                "性能",
                "bug",
                "调试",
                "错误",
            ],
        }

        for agent_name, keywords in agent_keywords.items():
            if not keywords:
                continue
            for keyword in keywords:
                if keyword in text_lower:
                    if self._agent_manager.get_agent(agent_name):
                        return agent_name

        return None

    def _create_new_session(self):
        session = self.session_manager.create_new_session()
        self._current_history_index = None
        self.history_btn.setChecked(False)
        self._clear_chat_area()
        self.title_edit.setText("新对话")
        self.node_preview.clear_nodes()
        if self._todo_floating_widget:
            self._todo_floating_widget.clear()
        if self._tool_executor:
            self._tool_executor.clear_todo_list()
        if self._question_floating_widget:
            self._question_floating_widget.clear()
        self._question_tool_call_id = None
        self._load_agent_list()
        self._on_task_state_changed(session.task_state)
        agent = (
            self._agent_manager.get_agent(self._current_agent)
            if self._agent_manager
            else None
        )
        agent_name = agent.name if agent else ""
        agent_desc = agent.description if agent else ""
        welcome_card = create_welcome_card(self, agent_name, agent_desc)
        welcome_card._is_welcome = True
        welcome_card.contextActionRequested.connect(self.handle_recommended_question)
        QTimer.singleShot(300, lambda: self._add_chat_widget(welcome_card))

    def _display_current_session(self):
        self._clear_chat_area()
        self._history_preview_messages = None
        self._history_preview_title = ""

        session = self.session_manager.get_current_session()
        if not session:
            return
        self._on_task_state_changed(session.task_state)

        if self._current_history_index is not None:
            title = self.history_manager.get_current_title(self._current_history_index)
            if title:
                self.title_edit.setText(title)

        self._message_batch = list(session.messages)
        self._message_batch_index = 0
        self._batch_size = 4
        self._load_message_batch()

    def _display_preview_session(self):
        self._clear_chat_area()

        if self._history_preview_title:
            self.title_edit.setText(self._history_preview_title)

        self._message_batch = list(self._history_preview_messages or [])
        self._message_batch_index = 0
        self._batch_size = 4
        self._load_message_batch()

    def _load_message_batch(self):
        """分批加载消息，避免卡顿"""
        batch = self._message_batch[
            self._message_batch_index : self._message_batch_index + self._batch_size
        ]

        for msg in batch:
            role = msg.get("role")

            if role == "user":
                content = self._sanitize_user_message_for_display(
                    msg.get("content", "")
                )
                self._append_user_message(
                    content,
                    timestamp=msg.get(
                        "timestamp", datetime.now().strftime("%Y-%m-%d %H:%M")
                    ),
                    tag_params=msg.get("params", {}),
                )

            elif role == "assistant":
                card = self._append_assistant_message(
                    timestamp=msg.get(
                        "timestamp", datetime.now().strftime("%Y-%m-%d %H:%M")
                    )
                )
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = "\n".join(
                        [
                            item.get("text", "")
                            for item in content
                            if item.get("type") == "text"
                        ]
                    )

                tool_calls = msg.get("tool_calls", [])
                tool_results = msg.get("tool_results", [])

                if tool_calls:
                    self._render_merged_tool_calls(
                        card, tool_calls, tool_results, content
                    )
                else:
                    card.update_content(content)
                card.finish_streaming()
            else:
                continue

        self._message_batch_index += len(batch)

        if self._message_batch_index < len(self._message_batch):
            QTimer.singleShot(0, self._load_message_batch)
        else:
            QTimer.singleShot(10, self._scroll_to_bottom)
            self._update_node_preview()

    def _render_merged_tool_calls(
        self, card, tool_calls: list, tool_results: list, final_content: str = ""
    ):
        """渲染合并消息中的工具调用和结果 + 最终回复"""
        combined_content = ""

        for tc in tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "unknown")
            args = func.get("arguments", {})

            args_dict = json.loads(args) if isinstance(args, str) else args

            result_content = ""
            for tr in tool_results:
                if tr.get("tool_call_id") == tc.get("id"):
                    result_content = tr.get("content", "")
                    break

            tool_block = format_tool_block(
                tool_name,
                args_dict,
                result_content,
                True,
            )

            if combined_content:
                combined_content += "\n\n"
            combined_content += tool_block

        if final_content:
            if combined_content:
                combined_content += "\n\n---\n\n"
            combined_content += final_content

        if combined_content:
            card.update_content(combined_content)

    def _initialize_history_manager(self):
        canvas_name = getattr(self.homepage, "workflow_name", "default") or "default"
        self.history_manager = HistoryManager(canvas_name)

    def _toggle_history_mode(self, enabled: bool):
        if enabled:
            if self._history_preview_session_data is None:
                current_session = self.session_manager.get_current_session()
                self._history_preview_session_data = (
                    current_session.to_dict() if current_session else None
                )
                self._history_preview_history_index = self._current_history_index
            self._in_history_mode = True
            self.chat_layout.setAlignment(Qt.AlignTop)
            self._display_history_sessions()
        else:
            self._in_history_mode = False
            self.chat_layout.setAlignment(Qt.AlignBottom)
            if self._history_preview_opening:
                self._history_preview_opening = False
                self._display_preview_session()
                return
            if self._history_preview_session_data:
                restored_session = ChatSession.from_dict(
                    self._history_preview_session_data
                )
                self.session_manager.set_current_session(restored_session)
            self._current_history_index = self._history_preview_history_index
            self._history_preview_session_data = None
            self._history_preview_history_index = None
            self._history_preview_messages = None
            self._history_preview_title = ""
            self._display_current_session()

    def _toggle_shell_mode(self, enabled: bool):
        self._is_shell_mode = enabled
        if enabled:
            self.input_area.setPlaceholderText("输入Shell命令，按Enter执行")
            self.title_edit.setText("Shell执行")
        else:
            self.input_area.setPlaceholderText("enter 发送信息, shift+enter 换行")
            self.title_edit.setText("新对话")

    def _execute_shell_command(self, cmd: str):
        self._append_user_message(
            cmd, timestamp=datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        self._is_streaming = True
        self._toggle_send_stop(True)

        def on_result(result_text: str):
            self._is_streaming = False
            self._toggle_send_stop(False)
            card = self._append_assistant_message()
            card.update_content(f"```\n{result_text}\n```")
            card.finish_streaming()
            self._scroll_to_bottom()

        task = ShellExecutionTask(cmd, on_result)
        self._gen_thread_pool.start(task)

    def _display_history_sessions(self):
        self._clear_chat_area()

        history_list = self.history_manager.get_history_list()
        if not history_list:
            placeholder = QLabel("暂无历史对话记录", self)
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #999;")
            self.chat_layout.addWidget(placeholder)
            return

        reversed_history = list(enumerate(history_list[::-1]))
        for display_idx, session in reversed_history:
            title = session["title"]
            last_time = session["last_time"]
            original_index = len(history_list) - 1 - display_idx

            is_current = (
                self._current_history_index is not None
                and self._current_history_index == original_index
            )

            card = self._create_history_card(
                title, last_time, original_index, is_current=is_current
            )
            self.chat_layout.addWidget(card)

        self._scroll_to_bottom()

    def _create_history_card(
        self, title: str, last_time: str, index: int, is_current: bool = False
    ) -> QWidget:
        card = CardWidget(self)

        base_style = "background-color: transparent; border-radius: 6px; padding: 8px; color: white;"
        if is_current:
            card.setStyleSheet(
                "background-color: #ff6f00; border-radius: 6px; padding: 8px; color: white;"
            )
        else:
            card.setStyleSheet(base_style)

        card.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 4)

        title_label = QLabel(title[:200], card)
        title_label.setWordWrap(True)
        time_label = QLabel(last_time, card)
        if is_current:
            title_label.setStyleSheet(
                "color: white; font-weight: bold; background-color: transparent;"
            )
            time_label.setStyleSheet("color: rgba(255,255,255,0.8);")
        else:
            time_label.setStyleSheet("color: #aaa;")

        delete_btn = TransparentToolButton(FluentIcon.DELETE, card)
        delete_btn.setFixedSize(24, 24)
        delete_btn.clicked.connect(lambda _, i=index: self._delete_history_session(i))

        layout.addWidget(title_label, 1)
        layout.addStretch()
        layout.addWidget(time_label)
        layout.addWidget(delete_btn)

        card.mousePressEvent = lambda e, i=index: self._load_history_session(i)

        return card

    def _clear_chat_area(self):
        self._current_assistant_card = None
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _sanitize_user_message_for_display(self, content: str) -> str:
        if not isinstance(content, str):
            return content

        pattern = re.compile(
            r"^\[Task Stage:.*?\]\n\[Current Goal:.*?\]\n\[Verification:.*?\]\n\n",
            re.DOTALL,
        )
        return pattern.sub("", content, count=1)

    def _on_clear_shortcut(self):
        self._clear_chat_area()
        self.node_preview.clear_nodes()
        session = self.session_manager.get_current_session()
        if session:
            session.clear()
            self._on_task_state_changed(session.task_state)
        agent = (
            self._agent_manager.get_agent(self._current_agent)
            if self._agent_manager
            else None
        )
        agent_name = agent.name if agent else ""
        agent_desc = agent.description if agent else ""
        welcome_card = create_welcome_card(self, agent_name, agent_desc)
        welcome_card._is_welcome = True
        welcome_card.contextActionRequested.connect(self.handle_recommended_question)
        QTimer.singleShot(300, lambda: self._add_chat_widget(welcome_card))
        self.title_edit.setText("新对话")

    def _add_chat_widget(self, widget: QWidget):
        if isinstance(widget, MessageCard):
            widget.sync_width()
            if widget.role == "user":
                self.chat_layout.addWidget(widget, 0, Qt.AlignRight)
            else:
                self.chat_layout.addWidget(widget, 0, Qt.AlignLeft)
        else:
            self.chat_layout.addWidget(widget)

    def _delete_history_session(self, index: int):
        self.history_manager.delete_history(index)
        self._display_history_sessions()

    def _load_history_session(self, index: int):
        messages = self.history_manager.get_session_by_index(index)
        if messages is None:
            return
        self._history_preview_messages = list(messages)
        self._history_preview_title = self.history_manager.get_current_title(index)
        self._current_history_index = index
        self._in_history_mode = False
        self.chat_layout.setAlignment(Qt.AlignBottom)
        self._history_preview_opening = True
        self.history_btn.setChecked(False)

    def _append_user_message(
        self, content: str, timestamp: str = None, tag_params: dict = None
    ):
        card = MessageCard(
            parent=self,
            role="user",
            timestamp=timestamp,
            tag_params=tag_params
            or {key: value for key, value in self.context_selector.context.items()},
        )
        # card.viewer._install_dialog_filter()
        card.update_content(content)
        card.finish_streaming()
        card.deleteRequested.connect(lambda: self._delete_message(card))
        card.actionRequested.connect(self._on_code_action)
        self._add_chat_widget(card)
        self._scroll_to_bottom()

        self._update_node_preview()
        return card

    def _append_assistant_message(self, timestamp: str = None) -> MessageCard:
        card = MessageCard(parent=self, role="assistant", timestamp=timestamp)
        card.viewer._install_dialog_filter()
        card.actionRequested.connect(self._on_code_action)
        card.regenerateRequested.connect(lambda: self._regenerate_message(card))
        card.contextActionRequested.connect(self.handle_recommended_question)
        if hasattr(self.homepage, "on_context_action"):
            card.contextActionRequested.connect(self.homepage.on_context_action)
        else:
            card.contextActionRequested.connect(self.contextActionRequested.emit)
        self._add_chat_widget(card)
        self._scroll_to_bottom()
        return card

    def _update_assistant_message(self, card: MessageCard, new_content: str):
        card.update_content(new_content)
        if self._is_streaming:
            self._scroll_to_bottom()

    def _update_node_preview(self):
        session = self.session_manager.get_current_session()
        if not session:
            return

        node_data = []
        current_user_msg = None

        for msg in session.messages:
            if msg["role"] == "user":
                current_user_msg = msg.get("content", "")[:30]
            elif msg["role"] == "assistant" and current_user_msg:
                timestamp = (
                    msg.get("timestamp", "")[-5:] if msg.get("timestamp") else ""
                )
                node_data.append((current_user_msg, timestamp))
                current_user_msg = None

        if current_user_msg:
            node_data.append((current_user_msg, ""))

        self.node_preview.update_nodes(node_data)

    def _on_node_preview_clicked(self, index: int):
        session = self.session_manager.get_current_session()
        if not session:
            return

        pair_index = 0
        for i, msg in enumerate(session.messages):
            if msg["role"] == "user":
                if pair_index == index:
                    card_index = i
                    for j in range(i + 1, len(session.messages)):
                        if isinstance(self.chat_layout.itemAt(j), type(None)):
                            continue
                        widget = self.chat_layout.itemAt(j).widget()
                        if (
                            widget
                            and hasattr(widget, "role")
                            and widget.role == "assistant"
                        ):
                            card_index = j
                            break
                    scroll_area = self.chat_scroll_area
                    if scroll_area:
                        y = 0
                        for k in range(card_index):
                            item = self.chat_layout.itemAt(k)
                            if item and item.widget():
                                y += item.widget().height() + 5
                        scroll_area.verticalScrollBar().setValue(y)
                    return
                pair_index += 1

    def _on_scroll_changed(self, value):
        scroll_bar = self.chat_scroll_area.verticalScrollBar()
        viewport_height = self.chat_scroll_area.viewport().height()
        visible_top = scroll_bar.value()
        visible_bottom = visible_top + viewport_height

        user_msg_indices = []
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if not item or not item.widget():
                continue
            widget = item.widget()
            if not isinstance(widget, MessageCard):
                continue
            if widget.role != "user":
                continue
            y = 0
            for j in range(i):
                item_j = self.chat_layout.itemAt(j)
                if item_j and item_j.widget():
                    y += item_j.widget().height() + 5
            widget_bottom = y + widget.height()
            if widget_bottom > visible_top and y < visible_bottom:
                user_msg_indices.append(i)

        if user_msg_indices:
            first_visible_idx = user_msg_indices[0]
            pair_index = 0
            for i in range(first_visible_idx):
                item = self.chat_layout.itemAt(i)
                if item and item.widget() and isinstance(item.widget(), MessageCard):
                    if item.widget().role == "user":
                        pair_index += 1
            self.node_preview.set_visible_node(pair_index)
        else:
            self.node_preview.set_visible_node(-1)

    def _delete_message(self, card: MessageCard):
        card_index = -1
        for i in range(self.chat_layout.count()):
            if self.chat_layout.itemAt(i).widget() is card:
                card_index = i
                break
        if card_index == -1:
            return

        session = self.session_manager.get_current_session()
        if not session:
            return

        to_remove_indices = [card_index]
        if card.role == "user" and card_index + 1 < self.chat_layout.count():
            next_widget = self.chat_layout.itemAt(card_index + 1).widget()
            if isinstance(next_widget, MessageCard) and next_widget.role == "assistant":
                to_remove_indices.append(card_index + 1)

        for idx in sorted(to_remove_indices, reverse=True):
            item = self.chat_layout.itemAt(idx)
            if item and item.widget():
                w = item.widget()
                self.chat_layout.removeWidget(w)
                w.deleteLater()
            if idx < len(session.messages):
                session.messages.pop(idx)

        self._update_node_preview()

    def _regenerate_message(self, card: MessageCard):
        session = self.session_manager.get_current_session()
        if not session:
            return

        if card.role != "assistant":
            return

        card_uuid = id(card)

        ui_card_map = {}
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), MessageCard):
                ui_card_map[id(item.widget())] = i

        card_pos = ui_card_map.get(card_uuid, -1)
        if card_pos < 0:
            return

        user_card_pos = -1
        for i in range(card_pos - 1, -1, -1):
            item = self.chat_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), MessageCard):
                if item.widget().role == "user":
                    user_card_pos = i
                    break

        if user_card_pos >= 0:
            user_card = self.chat_layout.itemAt(user_card_pos).widget()
            if hasattr(user_card, "viewer"):
                user_input = user_card.viewer.get_plain_text()
            else:
                user_input = ""
            if hasattr(user_card, "context_tags"):
                user_params = user_card.context_tags
            else:
                user_params = None

            self.chat_layout.removeWidget(user_card)
            user_card.deleteLater()
            if user_card_pos < len(session.messages):
                session.messages.pop(user_card_pos)
            card_pos -= 1

            card_uuid = id(card)
            ui_card_map = {}
            for i in range(self.chat_layout.count()):
                item = self.chat_layout.itemAt(i)
                if item and item.widget() and isinstance(item.widget(), MessageCard):
                    ui_card_map[id(item.widget())] = i
            card_pos = ui_card_map.get(card_uuid, card_pos)
        else:
            return

        if user_params:
            user_input = (
                "\n".join([value[1] for value in user_params.values()])
                + "\n\n"
                + user_input
            )

        self._delete_message(card)
        self._on_send_clicked(user_input)

    def _on_code_action(self, code: str, action: str = "copy"):
        if action == "insert":
            self.insertResponse.emit(code)
        elif action == "create":
            self.createResponse.emit(code)
        elif action == "copy":
            clipboard = QApplication.clipboard()
            clipboard.setText(code)
            InfoBar.success(
                "已复制",
                "",
                duration=1500,
                parent=self.homepage,
                position=InfoBarPosition.TOP_RIGHT,
            )

    def _scroll_to_bottom(self):
        def _do_scroll():
            self.chat_scroll_area.verticalScrollBar().setValue(
                self.chat_scroll_area.verticalScrollBar().maximum()
            )
            session = self.session_manager.get_current_session()
            if session:
                user_count = sum(
                    1 for msg in session.messages if msg.get("role") == "user"
                )
                if user_count > 0:
                    self.node_preview.set_visible_node(user_count - 1)

        QTimer.singleShot(10, _do_scroll)

    def handle_recommended_question(self, content: str, action: str):
        if action == "ask":
            self.input_area.clear()
            self.send_preset_question(content)

    def send_preset_question(self, question: str):
        if not isinstance(question, str) or not question.strip():
            return

        if self._in_history_mode:
            self.history_btn.setChecked(False)
            self._toggle_history_mode(False)
        self._on_send_clicked(user_text=question.strip())

    def _on_send_clicked(self, user_text: str = ""):
        if self._is_streaming:
            self._on_stop_clicked()

        if not user_text:
            user_text = self.input_area.toPlainText().strip()

        if self._is_shell_mode:
            if not user_text:
                return
            self.input_area.clear()
            self._execute_shell_command(user_text)
            return

        if not user_text:
            return

        context_params = {k: v for k, v in self.context_selector.context.items()}

        self.input_area.clear()

        self._append_user_message(user_text)

        assistant_card = self._append_assistant_message()

        self._is_streaming = True
        self._toggle_send_stop(True)
        self._chat_engine.send_message(user_text, context_params)
        self._current_assistant_card = assistant_card
        self._maybe_generate_topic_summary()

    def _on_stream_started(self):
        self._is_streaming = True
        self._accumulated_content = ""

    def _on_content_received(self, content_piece: str):
        if self._current_assistant_card:
            self._update_assistant_message(self._current_assistant_card, content_piece)

        if not hasattr(self, "_accumulated_content"):
            self._accumulated_content = ""
        self._accumulated_content += content_piece

    def _on_tool_call_started(
        self, tool_call_id: str, tool_name: str, arguments: dict, round_id: str = None
    ):
        import time

        self._current_tool_start_time = time.time()
        self._current_tool_call_id = tool_call_id
        self._current_tool_name = tool_name
        self._current_tool_args = arguments

        if tool_name == "question":
            question_text = arguments.get("question", "")
            options = arguments.get("options", [])
            multiple = arguments.get("multiple", False)
            if question_text:
                self._question_tool_call_id = tool_call_id
                if not isinstance(options, list):
                    options = []
                self._question_floating_widget.show_question(
                    question_text, options, multiple
                )
            return

        if tool_name in ("todowrite", "todoread"):
            self._todo_floating_widget.setVisible(True)
            return

        if tool_name == "task":
            agent_name = arguments.get("agent", "unknown")
            task_desc = arguments.get("description", "")

            self._sub_agent_floating_widget.start_task(agent_name, task_desc)

            self._connect_sub_agent_signals(arguments)

            return

        self._tool_floating_widget.start_tool(tool_name, arguments)

    def _connect_sub_agent_signals(self, arguments: dict):
        """连接子智能体信号，支持延迟检查"""

        def try_connect():
            if not hasattr(self._tool_executor, "_builtin_tools"):
                return
            if not hasattr(self._tool_executor._builtin_tools, "_sub_agent_manager"):
                return

            sub_agent_mgr = self._tool_executor._builtin_tools._sub_agent_manager
            if not sub_agent_mgr or not sub_agent_mgr._running_tasks:
                return

            last_task_id = list(sub_agent_mgr._running_tasks.keys())[-1]
            if not last_task_id:
                return

            executor = sub_agent_mgr._running_tasks.get(last_task_id)
            if not executor:
                return

            def on_progress(msg):
                self._sub_agent_floating_widget.update_progress(msg)

            def on_tool_call(tool_name, args):
                self._sub_agent_floating_widget.add_tool_call(tool_name, args)

            def on_tool_result(tool_name, result, success):
                self._sub_agent_floating_widget.add_tool_result(
                    tool_name, result, success
                )

            def on_finished(result):
                success = not (
                    result
                    and (
                        "error" in result.lower()
                        or "失败" in result
                        or "timeout" in result.lower()
                    )
                )
                self._sub_agent_floating_widget.finish_task(result, success)

            try:
                executor.progress_updated.disconnect()
            except:
                pass
            try:
                executor.tool_call_started.disconnect()
            except:
                pass
            try:
                executor.tool_result_received.disconnect()
            except:
                pass
            try:
                executor.finished_with_result.disconnect()
            except:
                pass

            executor.progress_updated.connect(on_progress)
            executor.tool_call_started.connect(on_tool_call)
            executor.tool_result_received.connect(on_tool_result)
            executor.finished_with_result.connect(on_finished)

        QTimer.singleShot(100, try_connect)

    def _on_tool_cancelled(self):
        """工具执行被用户中止"""
        logger.info("[ToolFloatingWidget] Tool execution cancelled by user")
        self._tool_floating_widget.finish_tool("用户中止", success=False)

        tool_call_id = getattr(self, "_current_tool_call_id", None)
        tool_name = getattr(self, "_current_tool_name", "unknown")
        tool_args = getattr(self, "_current_tool_args", {})

        if tool_call_id and self._current_assistant_card:
            separator = "\n\n"
            tool_block = format_tool_block(
                tool_name,
                tool_args,
                "[工具执行已被用户中止]",
                False,
            )
            self._current_assistant_card.update_content(separator + tool_block)
            self._scroll_to_bottom()

        if hasattr(self, "_chat_engine") and self._chat_engine:
            worker = getattr(self._chat_engine, "_current_worker", None)
            if worker:
                worker.cancel()

    def _on_tool_result_received(
        self, tool_call_id: str, tool_name: str, arguments: dict, result: Any
    ):
        import time

        elapsed = (
            time.time() - self._current_tool_start_time
            if hasattr(self, "_current_tool_start_time")
            else 0
        )

        success = result.success if hasattr(result, "success") else True

        if tool_name not in ("question", "task", "todowrite", "todoread"):
            self._tool_floating_widget.show_if_needed(elapsed)
            self._tool_floating_widget.finish_tool(str(result)[:200], success)

        if tool_name in ("todowrite", "todoread"):
            todos = self._tool_executor.todo_list if self._tool_executor else []
            self._todo_floating_widget.update_todos(todos)
            self._todo_floating_widget.setVisible(True)

        content = str(result)
        tool_block = format_tool_block(
            tool_name,
            arguments or {},
            content,
            success,
        )

        if self._current_assistant_card:
            separator = "\n\n"
            self._current_assistant_card.update_content(separator + tool_block)

        self._scroll_to_bottom()

    def _find_latest_assistant_card(self) -> Optional[MessageCard]:
        for i in range(self.chat_layout.count() - 1, -1, -1):
            item = self.chat_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, MessageCard) and widget.role == "assistant":
                    return widget
        return None

    def _on_stream_finished(self, response: str):
        self._is_streaming = False
        self._toggle_send_stop(False)

        if self._current_assistant_card:
            self._current_assistant_card.finish_streaming()
            self._sync_current_assistant_card_to_session()

        if self.history_manager:
            self._save_current_session_to_history()

    def _sync_current_assistant_card_to_session(self):
        if self._history_preview_messages is not None:
            return

        session = self.session_manager.get_current_session()
        if not session or not self._current_assistant_card:
            return

        viewer = getattr(self._current_assistant_card, "viewer", None)
        if not viewer or not hasattr(viewer, "get_plain_text"):
            return

        content = viewer.get_plain_text()
        if not content or not str(content).strip():
            return

        assistant_message = {
            "role": "assistant",
            "content": content,
            "timestamp": self._current_assistant_card.timestamp,
        }

        if session.messages and session.messages[-1].get("role") == "assistant":
            session.messages[-1] = assistant_message
        else:
            session.messages.append(assistant_message)
        session._update_timestamp()

    def _save_current_session_to_history(self):
        saved_messages = []

        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, MessageCard):
                    role = widget.role
                    content = ""
                    if hasattr(widget, "viewer") and hasattr(
                        widget.viewer, "get_plain_text"
                    ):
                        content = widget.viewer.get_plain_text()
                    if content:
                        saved_messages.append(
                            {
                                "role": role,
                                "content": content,
                                "timestamp": widget.timestamp,
                            }
                        )

        if saved_messages:
            if self._current_history_index is not None:
                self.history_manager.update_session(
                    self._current_history_index, saved_messages
                )
            else:
                self.history_manager.save_session(saved_messages)
                self._current_history_index = 0
        self._update_node_preview()

    def _on_engine_error(self, error: str):
        if self._current_assistant_card:
            self._current_assistant_card.stop_streaming_anim()
            self._current_assistant_card.set_error_state(True)
            self._current_assistant_card.update_content(error)
            self._sync_current_assistant_card_to_session()
        self._is_streaming = False
        self._toggle_send_stop(False)

    def _on_user_message_added(self, user_text: str):
        pass

    def _on_skill_requested(self, method: str, params: dict):
        result = self._tool_executor.execute_skill(method, params)
        content = (
            f"[Skill Result] {result}"
            if "error" not in result
            else f"[Skill Error] {result.get('error')}"
        )
        new_card = self._append_assistant_message()
        new_card.update_content(str(content))
        new_card.finish_streaming()
        self._scroll_to_bottom()

    def _on_shell_command_requested(self, cmd: str):
        import subprocess

        try:
            res = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=60
            )
            output = res.stdout.strip()
            error_out = res.stderr.strip()
            combined = "\n".join([output, error_out]).strip()
            tool_card = self._append_assistant_message()
            tool_card.update_content("Shell command result:\n" + (combined or ""))
            tool_card.finish_streaming()
            self._scroll_to_bottom()
        except Exception as e:
            err_card = self._append_assistant_message()
            err_card.update_content(f"[Shell execution error] {e}")
            err_card.finish_streaming()
            self._scroll_to_bottom()

    def _on_question_asked(
        self, tool_call_id: str, question: str, options: list, multiple: bool = False
    ):
        self._question_tool_call_id = tool_call_id
        if not isinstance(options, list):
            options = []
        self._question_floating_widget.show_question(question, options, multiple)

    def _on_question_answered(self, answer: str):
        if not self._question_tool_call_id:
            return

        tool_call_id = self._question_tool_call_id
        self._question_tool_call_id = None

        if self._chat_engine:
            self._chat_engine.provide_question_answer(answer)

    def _on_question_cancelled(self):
        """用户关闭问题窗口时，返回空答案让大模型继续"""
        if not self._question_tool_call_id:
            return

        self._question_tool_call_id = None

        if self._chat_engine:
            self._chat_engine.provide_question_answer("")

    def _on_agent_switched(self, agent_name: str):
        """智能体切换回调 - 丝滑切换，不清空对话"""
        pass

    def _maybe_generate_topic_summary(self):
        selected_name = self.model_combo.currentText()
        llm_config = self._valid_configs.get(selected_name)
        if not llm_config:
            logger.warning("[Topic Summary] No LLM config found, skipping")
            return
        session = self.session_manager.get_current_session()
        if not session:
            logger.warning("[Topic Summary] No session found, skipping")
            return

        user_messages = [m for m in session.messages if m.get("role") == "user"]
        if not user_messages:
            logger.warning("[Topic Summary] No user messages found, skipping")
            return
        previous_summary = ""
        if self._current_history_index is not None:
            previous_summary = self.history_manager.get_topic_summary(
                self._current_history_index
            )

        long_term_memory = (
            self._memory_manager.get_context_string() if self._memory_manager else ""
        )

        existing_memories = (
            self._memory_manager.get_user_memories() if self._memory_manager else []
        )

        task = TopicSummaryTask(
            messages=session.messages,
            llm_config=llm_config,
            callback=self._on_topic_summary_generated,
            previous_summary=previous_summary if previous_summary else None,
            long_term_memory=long_term_memory,
            existing_memories=existing_memories,
        )
        self._gen_thread_pool.start(task)

    def _on_topic_summary_generated(self, result, error: str = None):
        if error:
            logger.error(f"[Topic Summary] Failed to generate: {error}")
            return
        if not result:
            return

        if isinstance(result, dict):
            summary = result.get("topic_summary", "")
            should_update_memory = result.get("should_update_memory", False)
            memory_content = result.get("memory_content", "")
        else:
            summary = result
            should_update_memory = False
            memory_content = ""

        if not summary:
            return

        clean_summary = summary.strip()
        if len(clean_summary) > 20:
            clean_summary = clean_summary[:20] + "..."

        if self._current_history_index is None:
            self.history_manager.save_session(
                self.session_manager.get_current_session().messages
            )
            self._current_history_index = 0

        self.history_manager.update_topic_summary(
            self._current_history_index, clean_summary
        )

        session = self.session_manager.get_current_session()
        if session:
            session.set_topic_summary(clean_summary)

        self._update_title_display(clean_summary)

        if should_update_memory and memory_content and self._memory_manager:
            self._memory_manager.add_user_memory(memory_content)
            logger.info(
                f"[Topic Summary] Added to long-term memory: {memory_content[:50]}..."
            )
        else:
            logger.info(
                f"[Topic Summary] Memory update skipped (should_update={should_update_memory}, content={bool(memory_content)})"
            )

    def _update_title_display(self, title: str):
        self.title_edit.setText(title)

    def _show_soul_memory(self):
        if not self._memory_manager:
            return
        user_memories = self._memory_manager.get_user_memories()

        dialog = MemoryManagerDialog(user_memories, self)
        dialog.memoryUpdated.connect(self._on_memory_updated)
        dialog.exec_()

    def _on_memory_updated(self, memories: list):
        if not self._memory_manager:
            return
        self._memory_manager.update_user_memories(memories)
        InfoBar.success("已保存", "长期记忆已更新", parent=self, duration=1500)

    def _on_title_double_click(self, event):
        from PyQt5.QtWidgets import QInputDialog, QLineEdit

        current_title = self.title_edit.text()
        new_title, ok = QInputDialog.getText(
            self, "编辑标题", "请输入新标题:", QLineEdit.Normal, current_title
        )
        if ok and new_title.strip():
            self._update_title(new_title.strip())

    def _update_title(self, new_title: str):
        self.title_edit.setText(new_title)
        if self._current_history_index is not None:
            self.history_manager.update_session_title(
                self._current_history_index, new_title
            )

    def _auto_save_current_session(self):
        session = self.session_manager.get_current_session()
        if not session or not session.messages:
            return

        if self._current_history_index is not None:
            self.history_manager.update_session(
                self._current_history_index, session.messages
            )
        else:
            self.history_manager.save_session(session.messages)
            self._current_history_index = 0

        return self.history_manager.get_current_title(self._current_history_index)

    def _toggle_send_stop(self, is_sending: bool):
        if is_sending:
            self.model_combo.setDisabled(True)
            self.history_btn.setDisabled(True)
            self.input_area.toggle_send_button(False)
        else:
            self.model_combo.setDisabled(False)
            self.history_btn.setDisabled(False)
            self.input_area.toggle_send_button(True)

    def _on_stop_clicked(self):
        if self._chat_engine:
            self._chat_engine.stop()
        self._is_streaming = False
        self._toggle_send_stop(False)
        if self._current_assistant_card:
            self._current_assistant_card.stop_streaming_anim()
        InfoBar.warning(
            title="已中止",
            content="问答请求已被手动中止。",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self,
        )

    def _create_context_menu(self):
        self._context_menu_actions = {}
        self.menu_btn.clicked.connect(self._show_context_menu)

    def _show_context_menu(self):
        from PyQt5.QtWidgets import QMenu

        menu = QMenu(self)
        export_action = menu.addAction("导出对话记录")
        export_action.triggered.connect(self._export_conversation)
        clear_action = menu.addAction("清空当前对话")
        clear_action.triggered.connect(self._clear_current_conversation)
        menu.exec_(self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomRight()))

    def _export_conversation(self):
        session = self.session_manager.get_current_session()
        if not session or not session.messages:
            InfoBar.warning("无法导出", "当前没有对话内容", parent=self)
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出对话",
            f"对话_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            "Markdown Files (*.md);;Text Files (*.txt)",
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"# 对话记录\n\n")
                f.write(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                for msg in session.messages:
                    role = "用户" if msg.get("role") == "user" else "助手"
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        content = "\n".join(
                            [
                                item.get("text", "")
                                for item in content
                                if item.get("type") == "text"
                            ]
                        )
                    f.write(f"## {role}\n\n{content}\n\n")
            InfoBar.success("导出成功", f"已保存到: {file_path}", parent=self)
        except Exception as e:
            InfoBar.error("导出失败", str(e), parent=self)

    def _clear_current_conversation(self):
        self._create_new_session()
        InfoBar.success("已清空", "开始新的对话", parent=self, duration=1500)
