# -*- coding: utf-8 -*-
import os
import re
from pathlib import Path

import sip
import ctypes
from datetime import datetime
from typing import Optional, Dict, Any, List

from PyQt5.QtCore import (
    Qt,
    QTimer,
    pyqtSignal,
    QThreadPool,
)
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QApplication,
    QWidget,
    QFileDialog,
)

# 注册 QProcess::ExitStatus 元类型，解决跨线程信号连接问题
# PyInstaller 打包后，uvicorn 可能创建子进程，需要此注册
try:
    qRegisterMetaType("QProcess::ExitStatus")
except NameError:
    # PyQt5 中 qRegisterMetaType 是内置函数，不需要导入
    pass

from loguru import logger
from qfluentwidgets import (
    setFont,
    ComboBox,
    FluentIcon,
    SingleDirectionScrollArea,
    InfoBar,
    InfoBarPosition,
    CardWidget,
    TransparentToolButton,
)

from app.utils.config import Settings
from app.utils.utils import get_icon
from app.llm_chatter.constants import (
    FREE_PROVIDERS,
    PROVIDER_ICONS,
    PROVIDER_MODELS,
)
from app.llm_chatter.core import (
    ChatEngine,
    ToolExecutor,
    MemoryManagerCore,
)
from app.llm_chatter.core.agent import AgentManager
from app.llm_chatter.utils.chat_session import (
    SessionManager,
    ChatSession,
)
from app.llm_chatter.utils.history_manager import (
    HistoryManager,
)
from app.llm_chatter.utils.worker import (
    TopicSummaryTask,
    ShellExecutionTask,
)
from app.llm_chatter.widgets.bottom_input_area import (
    SendableTextEdit,
)
from app.llm_chatter.widgets.context_usage_ring import (
    ContextUsageRing,
)
from app.llm_chatter.widgets.conversation_node_preview import (
    ConversationNodePreview,
)
from app.llm_chatter.widgets.llm_config_popup import (
    LLMConfigPopup,
)
from app.llm_chatter.widgets.history_popup import (
    HistoryPopup,
)
from app.llm_chatter.widgets.memory_manager import (
    MemoryManagerDialog,
)
from app.llm_chatter.widgets.message_card import (
    MessageCard,
    create_welcome_card,
)
from app.llm_chatter.widgets.question_floating_widget import (
    QuestionFloatingWidget,
)
from app.llm_chatter.widgets.sub_agent_floating_widget import (
    SubAgentFloatingWidget,
)
from app.llm_chatter.widgets.todo_floating_widget import (
    TodoFloatingWidget,
)
from app.llm_chatter.widgets.tool_floating_widget import (
    ToolFloatingWidget,
)
from app.llm_chatter.widgets.llm_settings_card import (
    LLMSettingsCard,
)
from app.llm_chatter.widgets.base_settings_card import (
    BaseSettingsCard,
)
from app.llm_chatter.widgets.model_config_card import (
    ModelConfigCard,
)
from app.llm_chatter.widgets.model_selector_popup import (
    ModelSelectorPopup,
)
from app.llm_chatter.widgets.history_card import (
    HistoryCard,
)
from app.tool_window import (
    ToolWindow,
    DockPosition,
    DockCategory,
)
from app.llm_chatter.utils.message_content import (
    consolidate_messages,
    content_to_text,
    get_user_round_ranges,
    group_messages_for_display,
)
from app.llm_chatter.widgets.file_undo_dialog import (
    FileUndoPreviewDialog,
)
from app.llm_chatter.utils.diff_viewer import (
    DiffHtmlGenerator,
    DiffViewerWindow,
)


class OpenAIChatToolWindow(ToolWindow):
    name = "飘狐 DriFox"
    icon = get_icon("drifox")
    singleton = True
    default_position = DockPosition.TOP
    CATEGORIES = [DockCategory.PROJECT]
    display_order = 30
    session_manager = None
    _valid_configs: Dict[str, Dict[str, Any]] = {}
    history_manager = None
    _agent_manager: Optional[AgentManager] = None
    _current_agent: str = "plan"
    _in_history_mode = False
    _current_session_id: Optional[str] = None
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
    _tool_cancelled_by_user: bool = False
    _cancelled_tool_call_id: Optional[str] = None
    _todo_floating_widget = None
    _question_floating_widget = None
    _question_tool_call_id = None
    _history_preview_session_data: Optional[dict] = None
    _history_preview_history_index: Optional[int] = None
    _history_preview_opening: bool = False
    _window_active: bool = True
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
        self._session_card_cache: Dict[str, List[MessageCard]] = {}
        self._welcome_card_cache: Dict[str, MessageCard] = {}
        self._displayed_session_id: Optional[str] = None
        self._history_popup = None
        self._gen_thread_pool = QThreadPool()
        self._gen_thread_pool.setMaxThreadCount(2)
        self._pending_scroll_to_bottom = False
        self._last_visible_user_pair_index = -1
        self._scroll_bottom_timer = QTimer(self)
        self._scroll_bottom_timer.setSingleShot(True)
        self._scroll_bottom_timer.setInterval(24)
        self._scroll_bottom_timer.timeout.connect(self._do_scroll_to_bottom)
        # resize 防抖定时器 - 性能优化：增加防抖时间减少卡顿
        self._resize_debounce_timer = QTimer(self)
        self._resize_debounce_timer.setSingleShot(True)
        self._resize_debounce_timer.setInterval(100)  # 100ms 防抖，减少 resize 期间的计算
        self._resize_debounce_timer.timeout.connect(self._do_debounced_resize)
        # resize 完成后更新所有卡片的定时器（延迟更新非可见区域卡片）
        self._resize_complete_timer = QTimer(self)
        self._resize_complete_timer.setSingleShot(True)
        self._resize_complete_timer.setInterval(500)  # resize 结束后 500ms 再更新所有卡片
        self._resize_complete_timer.timeout.connect(self._sync_all_cards_width)
        self._pending_resize_sync = False
        self.toolStartUiSyncRequested.connect(
            self._handle_tool_start_ui_sync, type=Qt.BlockingQueuedConnection
        )
        self.homepage = homepage
        self._is_streaming = False
        homepage.installEventFilter(self)
        self._window_active = homepage.isActiveWindow()
        # 问题修复：初始化未定义的属性
        self._pending_permission_tool_call_id: Optional[str] = None
        self._question_tool_call_id: Optional[str] = None
        self._current_assistant_round_index: Optional[int] = None  # 跟踪当前应分配给 assistant 的 round_index
        self.session_manager = SessionManager()
        self.session_manager.create_new_session()
        self._current_session_id = self.session_manager.get_current_session().session_id
        app = QApplication.instance()
        if app is not None:
            try:
                app.aboutToQuit.connect(self._auto_save_current_session)
            except Exception:
                pass
        if hasattr(self.homepage, "global_variables_changed"):
            self.homepage.global_variables_changed.connect(self._load_model_configs)
        self._initialize_managers()

        # 设置文件操作记录的会话上下文
        if self._tool_executor:
            self._tool_executor.set_session_context(self._current_session_id)

    def _initialize_managers(self):
        """初始化核心管理器"""
        canvas_name = getattr(self.homepage, "workflow_name", "default") or "default"

        self._memory_manager = MemoryManagerCore(canvas_name)
        self._tool_executor = ToolExecutor(self.homepage, workdir=Path(__file__).parent.parent.parent)
        self._tool_executor.set_memory_manager(self._memory_manager)
        self._tool_executor.set_llm_config_getter(self._get_current_model_config)
        self._tool_executor.set_session_messages_getter(
            self._get_current_session_messages_for_tools
        )
        self._agent_manager = AgentManager()

        from app.llm_chatter.core.sub_agent_executor import (
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
            get_context_provider=lambda: None,
            tool_executor=self._tool_executor,
            agent_manager=self._agent_manager,
            get_chat_cards=self._get_chat_cards_for_engine,
            get_memory_context=self._build_memory_context_for_engine,
        )

        self._chat_engine.set_callback("content_received", self._on_content_received)
        self._chat_engine.set_callback("reasoning_content_received", self._on_reasoning_content_received)
        self._chat_engine.set_callback("tool_call_started", self._on_tool_call_started)
        self._chat_engine.set_callback(
            "tool_call_sync_requested", self._request_tool_start_ui_sync
        )
        self._chat_engine.set_callback(
            "tool_result_received", self._on_tool_result_received
        )
        self._chat_engine.set_callback("stream_started", self._on_stream_started)
        self._chat_engine.set_callback("stream_finished", self._on_stream_finished)
        self._chat_engine.set_callback("messages_updated", self._on_messages_updated)
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
        self._chat_engine.set_callback(
            "permission_approval_requested", self._on_permission_approval_requested
        )

        self._initialize_history_manager()

        # # 自动启动 LLM API 服务
        # self._init_llm_api_service()

    def _init_llm_api_service(self):
        """初始化 LLM API 服务"""
        from app.utils.config import Settings
        from app.llm_chatter.api import (
            LLMAPIService,
            APISessionHandler,
            is_service_running,
        )

        setting = Settings.get_instance()

        # 注册服务商列表获取回调
        def get_providers_list():
            return [{"name": name} for name in self._valid_configs.keys()]

        # 创建并注册 API 会话处理器（复用 UI 的 ChatEngine 和 SessionManager）
        self._api_session_handler = APISessionHandler(self)
        LLMAPIService.set_session_handler(self._api_session_handler)

        # 根据配置决定是否启动服务
        if setting.llm_api_enabled.value:
            if not is_service_running():
                service = LLMAPIService()
                service.port = setting.llm_api_port.value
                service.start(background=True)
        else:
            # 确保服务未启动
            if is_service_running():
                from app.llm_chatter.api import (
                    stop_llm_api_service,
                )

                stop_llm_api_service()

    def _setup_title_bar(self):
        """设置标题栏按钮"""
        title_bar = self.get_title_bar()
        # # 创建极简模式切换按钮
        # self._minimal_btn = TransparentToolButton(get_icon("极简"), self)
        # self._minimal_btn.setFixedSize(28, 28)
        # self._minimal_btn.setToolTip("极简模式")
        # self._minimal_btn.setCheckable(True)
        # self._minimal_btn.toggled.connect(self._toggle_minimal_mode)
        # title_bar.add_button(self._minimal_btn)
        # self._minimal_mode = False
        # self._minimal_status_widget = None
        # 创建复制窗口按钮
        self._copy_btn = TransparentToolButton(FluentIcon.COPY, self)
        self._copy_btn.setToolTip("复制窗口")
        self._copy_btn.clicked.connect(self._duplicate_window)
        title_bar.add_button(self._copy_btn)
        # 创建设置按钮
        self._settings_btn = TransparentToolButton(FluentIcon.SETTING, self)
        self._settings_btn.setFixedSize(28, 28)
        self._settings_btn.setToolTip("设置")
        self._settings_btn.clicked.connect(self._toggle_settings_card)
        title_bar.add_button(self._settings_btn)
        # # 创建 API 文档按钮
        # self._api_btn = TransparentToolButton(get_icon("Global"), self)
        # self._api_btn.setToolTip("API 文档 (http://localhost:8765/docs)")
        # self._api_btn.clicked.connect(self._open_api_docs)
        # title_bar.add_button(self._api_btn)

    def _toggle_settings_card(self):
        """切换设置卡片的显示"""
        if self._settings_popup.isVisible():
            self._settings_popup.hide()
        else:
            self._settings_popup.show()

    def _open_api_docs(self):
        """打开 API 文档页面"""
        from app.llm_chatter.api import open_docs
        open_docs()

    def _duplicate_window(self):
        """复制当前窗口并以弹窗方式显示"""
        try:
            # 创建新的窗口实例
            new_instance = OpenAIChatToolWindow(self.homepage, None)
            # 延迟调用，确保 UI 初始化完成
            QTimer.singleShot(100, lambda: new_instance._restore_latest_or_create_session())

            # 复制模型选择（确保两个实例都已初始化 UI）
            try:
                if (
                    hasattr(self, "_current_provider_name")
                    and hasattr(new_instance, "_current_provider_name")
                    and self._current_provider_name
                ):
                    new_instance._current_provider_name = self._current_provider_name
                    new_instance._current_model_name = self._current_model_name
                    new_instance._update_model_selector_btn()
            except Exception:
                pass  # 忽略模型复制失败

            # 设置 session 初始化的标志，避免重复创建新 session
            # 并标记为新会话模式，跳过历史会话恢复
            # 注意：不要设置 _session_initialized，让 showEvent 正常执行初始化
            new_instance._skip_restore_history = True  # 跳过历史会话恢复

            # 以弹窗方式显示
            from app.side_dock_area import ToolPopupDialog

            popup = ToolPopupDialog(new_instance, None)
            popup.setWindowTitle(f"{self.name} - 副本")
            popup.resize(600, 900)
            # 保存引用防止被垃圾回收
            if not hasattr(self, '_popup_refs'):
                self._popup_refs = []
            self._popup_refs.append(popup)
            popup.show()
        except Exception as e:
            from qfluentwidgets import InfoBar

            InfoBar.error("复制失败", str(e), parent=self)

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
        """获取当前选中的模型配置，实时从系统配置读取"""
        selected_name = self._current_provider_name if self._current_provider_name else (list(self._valid_configs.keys())[0] if self._valid_configs else "")

        setting = Settings.get_instance()

        saved_providers = setting.llm_saved_providers.value or {}
        if selected_name in saved_providers:
            return saved_providers[selected_name].copy()

        custom_vars = getattr(self.homepage, "global_variables", None)
        if custom_vars and hasattr(custom_vars, "custom"):
            if selected_name in custom_vars.custom:
                return custom_vars.custom[selected_name].value.copy()

        return self._valid_configs.get(selected_name, {})

    def _build_memory_context_for_engine(self, query: str = "") -> str:
        if not self._memory_manager:
            return ""
        return self._memory_manager.get_context_string(query=query, limit=8)

    def _get_current_session_messages_for_tools(self) -> List[Dict[str, Any]]:
        session = self.session_manager.get_current_session()
        if not session:
            return []
        return list(session.messages or [])

    def showEvent(self, event):
        if getattr(self, "_session_initialized", False):
            super().showEvent(event)
            return
        self._session_initialized = True

        workflow_name = getattr(self.homepage, "workflow_name", None)
        is_canvas = workflow_name is not None
        if is_canvas and self._current_agent != "canvas":
            self._on_agent_changed("canvas")
        QTimer.singleShot(0, self._load_agent_list)
        QTimer.singleShot(0, self._restore_latest_or_create_session)
        QTimer.singleShot(100, self._load_model_configs)
        super().showEvent(event)

    def _is_on_canvas(self):
        """检查当前是否在画布界面"""
        if not hasattr(self.homepage, "ui_manager") or not self.homepage.ui_manager:
            return False
        side_dock = getattr(self.homepage.ui_manager, "side_dock_area", None)
        if not side_dock:
            return False
        is_canvas = side_dock.context_id == DockCategory.CANVAS
        return is_canvas

    def _restore_latest_or_create_session(self):
        # 如果是新复制的窗口，跳过历史会话恢复
        if getattr(self, "_skip_restore_history", False):
            self._create_new_session()
            return
        if self._restore_latest_session():
            return
        self._create_new_session()

    def _create_new_session(self):
        if self._is_streaming and self._chat_engine:
            self._chat_engine.stop()
            self._is_streaming = False
            self._toggle_send_stop(False)

        try:
            self._auto_save_current_session()
        except Exception:
            logger.exception(
                "Failed to auto-save current session before creating a new one"
            )

        self._cache_current_session_cards()
        session = self.session_manager.create_new_session()
        self._current_session_id = session.session_id
        self._history_preview_messages = None
        self._history_preview_session_data = None
        self._history_preview_opening = False
        self._clear_chat_area()
        self.title_edit.setText("新对话")
        self.node_preview.clear_nodes()
        if self._todo_floating_widget:
            self._todo_floating_widget.clear()
        if self._tool_executor:
            self._tool_executor.clear_todo_list()
            self._tool_executor.set_session_context(self._current_session_id)
        if self._question_floating_widget:
            self._question_floating_widget.clear()
        self._question_tool_call_id = None
        self._load_agent_list()
        self._on_task_state_changed(session.task_state)

        is_canvas = getattr(self.homepage, "workflow_name", None) is not None
        if is_canvas and self._current_agent != "canvas":
            self._on_agent_changed("canvas")

        QTimer.singleShot(0, self._show_initial_welcome)
        self._refresh_context_usage_indicator()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

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

        # right_layout 保持简化，仅保留 context_usage_ring
        right_layout = QHBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        self.context_usage_ring = ContextUsageRing(self)
        right_layout.addWidget(self.context_usage_ring)

        session_bar_layout.addLayout(left_layout)
        session_bar_layout.addStretch()
        session_bar_layout.addLayout(right_layout)
        layout.addLayout(session_bar_layout)

        self._settings_popup = LLMSettingsCard(self)
        self._settings_popup.setVisible(False)
        self._settings_popup.closed.connect(self._on_settings_closed)
        self._settings_popup.configChanged.connect(self._load_model_configs)

        self._todo_floating_widget = TodoFloatingWidget(self)
        self._todo_floating_widget.setVisible(False)
        layout.addWidget(self._todo_floating_widget)

        self._sub_agent_floating_widget = SubAgentFloatingWidget(self)
        self._sub_agent_floating_widget.setVisible(False)

        self._tool_floating_widget = ToolFloatingWidget(self)
        self._tool_floating_widget.setVisible(False)

        layout.addWidget(self._settings_popup)

        self.chat_scroll_area = SingleDirectionScrollArea(self)
        self.chat_scroll_area.setMinimumHeight(10)
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
        self.chat_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background: transparent;")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(8, 8, 8, 8)
        self.chat_layout.setSpacing(8)
        self.chat_layout.setAlignment(Qt.AlignBottom)
        self.chat_scroll_area.setWidget(self.chat_container)

        layout.addWidget(self.chat_scroll_area, 1)

        layout.addWidget(self._sub_agent_floating_widget)
        layout.addWidget(self._tool_floating_widget)

        # 模型配置卡片 - 在消息列表下方，和工具卡片同位置
        self._model_config_card = BaseSettingsCard("模型配置", "🔧", self)
        self._model_config_card.setMaximumHeight(120)
        self._model_config_popup = ModelConfigCard()
        self._model_config_popup.configApplied.connect(self._on_config_applied)
        self._model_config_card.content_layout.addWidget(self._model_config_popup)
        self._model_config_card.setVisible(False)
        layout.addWidget(self._model_config_card)

        # 历史会话卡片 - 在消息列表下方，和工具卡片同位置
        self._history_card = BaseSettingsCard("历史会话", "📜", self)
        self._history_card.setFixedHeight(350)
        self._history_popup_card = HistoryCard()
        self._history_popup_card.sessionSelected.connect(self._on_history_session_selected)
        self._history_popup_card.sessionArchived.connect(self._archive_history_session)
        self._history_popup_card.sessionRenamed.connect(self._rename_history_session)
        self._history_popup_card.refreshRequested.connect(self._refresh_history_toggle_panel)
        self._history_card.content_layout.addWidget(self._history_popup_card)
        self._history_card.setVisible(False)
        layout.addWidget(self._history_card)

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
        hlayout.setSpacing(6)

        # 模型选择 - 扁平式上拉选择器（类似 OpenCode 风格）
        self.current_model_btn = QWidget(self)
        self.current_model_btn.setCursor(Qt.PointingHandCursor)
        self.current_model_btn.setStyleSheet("""
            QWidget {
                background-color: rgba(255, 255, 255, 0.06);
                border-radius: 8px;
                padding: 0px;
            }
            QWidget:hover {
                background-color: rgba(255, 255, 255, 0.10);
            }
        """)
        self.current_model_btn.mousePressEvent = lambda e: self._show_model_selector_popup()
        btn_layout = QHBoxLayout(self.current_model_btn)
        btn_layout.setContentsMargins(8, 4, 12, 4)
        btn_layout.setSpacing(6)
        self._model_btn_icon = QLabel(self.current_model_btn)
        self._model_btn_icon.setFixedSize(18, 18)
        btn_layout.addWidget(self._model_btn_icon)
        self._model_btn_text = QLabel("正在加载...", self.current_model_btn)
        self._model_btn_text.setStyleSheet("color: #f3f6fc; font-size: 13px; font-weight: bold; background: transparent;")
        btn_layout.addWidget(self._model_btn_text)
        btn_layout.addStretch()
        self.current_model_btn.setFixedHeight(30)
        hlayout.addWidget(self.current_model_btn)
        # 记下当前选中的服务商和模型，供弹窗使用
        self._current_provider_name = ""
        self._current_model_name = ""

        self.settings_btn = TransparentToolButton(get_icon("模型选择"), self)
        self.settings_btn.setToolTip("模型参数配置")
        self.settings_btn.clicked.connect(self._toggle_model_config_card)
        hlayout.addWidget(self.settings_btn)

        hlayout.addSpacing(12)  # 和其他按钮分隔

        hlayout.addStretch(1)  # 弹性空间，把其他按钮挤到右边

        self.new_session_btn = TransparentToolButton(FluentIcon.ADD, self)
        self.new_session_btn.setFixedSize(26, 26)
        self.new_session_btn.setToolTip("新建对话")
        self.new_session_btn.clicked.connect(self._create_new_session)

        self.memory_btn = TransparentToolButton(get_icon("长期记忆"), self)
        self.memory_btn.setFixedSize(26, 26)
        self.memory_btn.setToolTip("长期记忆管理")
        self.memory_btn.clicked.connect(self._show_soul_memory)

        self.history_btn = TransparentToolButton(FluentIcon.HISTORY, self)
        self.history_btn.setFixedSize(26, 26)
        self.history_btn.setToolTip("历史会话")
        self.history_btn.clicked.connect(self._toggle_history_card)

        # Diff 按钮 - 查看文件差异
        self.diff_btn = TransparentToolButton(get_icon("差异对比"), self)
        self.diff_btn.setFixedSize(26, 26)
        self.diff_btn.setToolTip("查看文件差异")
        self.diff_btn.clicked.connect(self._open_diff_viewer)

        hlayout.addWidget(self.diff_btn)
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

    def _on_model_changed(self, provider_name: str, model_name: str):
        """从模型选择器选中模型后的回调"""
        if provider_name:
            self._current_provider_name = provider_name
            self._current_model_name = model_name
            setting = Settings.get_instance()
            setting.set(setting.llm_selected_model, provider_name, save=True)
            self._update_model_selector_btn()
            self._refresh_context_usage_indicator()

    def _show_model_selector_popup(self):
        """显示扁平式模型选择上拉框"""
        provider_models_data = []
        for provider_name, config in self._valid_configs.items():
            model_list = []
            if "模型列表" in config:
                saved_models = config["模型列表"]
                if isinstance(saved_models, str):
                    try:
                        import ast; saved_models = ast.literal_eval(saved_models)
                    except Exception:
                        saved_models = []
                if isinstance(saved_models, list):
                    model_list = list(saved_models)
            elif provider_name in PROVIDER_MODELS:
                model_list = list(PROVIDER_MODELS[provider_name])
            cur_model = config.get("模型名称", "")
            if cur_model and cur_model not in model_list:
                model_list.insert(0, cur_model)
            if not model_list and cur_model:
                model_list = [cur_model]
            is_current = provider_name == self._current_provider_name
            provider_models_data.append((provider_name, model_list, is_current))

        if not hasattr(self, "_model_selector_popup") or not self._model_selector_popup:
            from app.llm_chatter.widgets.model_selector_popup import ModelSelectorPopup
            self._model_selector_popup = ModelSelectorPopup(self)
            self._model_selector_popup.modelSelected.connect(self._on_model_selected_from_popup)

        self._model_selector_popup.set_providers_data(
            provider_models_data, self._current_provider_name or "", self._current_model_name or "",
        )
        self._model_selector_popup.show_at(self.current_model_btn)

    def _on_model_selected_from_popup(self, provider_name: str, model_name: str):
        """从弹窗选中模型后切换"""
        self._current_provider_name = provider_name
        self._current_model_name = model_name
        if provider_name in self._valid_configs:
            self._valid_configs[provider_name]["模型名称"] = model_name
        setting = Settings.get_instance()
        setting.set(setting.llm_selected_model, provider_name, save=True)
        self._update_model_selector_btn()
        self._refresh_context_usage_indicator()

    def _update_model_selector_btn(self):
        """更新模型选择按钮的图标和文字显示"""
        if not hasattr(self, "current_model_btn"):
            return
        # 设置图标
        icon = None
        if self._current_provider_name:
            icon_name = PROVIDER_ICONS.get(self._current_provider_name, "")
            if icon_name:
                icon = get_icon(icon_name)

        if icon and not icon.isNull():
            self._model_btn_icon.setPixmap(icon.pixmap(18, 18))
        else:
            self._model_btn_icon.clear()

        # 设置文字
        if self._current_provider_name and self._current_model_name:
            self._model_btn_text.setText(self._current_model_name)
            self.current_model_btn.setToolTip(f"{self._current_provider_name} · {self._current_model_name}")
        elif self._current_provider_name:
            self._model_btn_text.setText(self._current_provider_name)
            self.current_model_btn.setToolTip(self._current_provider_name)
        else:
            self._model_btn_text.setText("选择模型...")
            self.current_model_btn.setToolTip("")

    def _on_context_selection_changed(self, _selected_keys=None):
        self._refresh_context_usage_indicator()

    def _refresh_context_usage_indicator(self):
        ring = getattr(self, "context_usage_ring", None)
        if not ring:
            return

        if not self._chat_engine:
            ring.set_usage(0, 0, 0)
            return

        session = self.session_manager.get_current_session()
        llm_config = self._get_current_model_config()
        snapshot = self._chat_engine.get_context_usage_snapshot(session, llm_config)
        ring.set_usage(
            snapshot.get("percent", 0),
            snapshot.get("used_tokens", 0),
            snapshot.get("budget_tokens", 0),
            snapshot.get("compaction", {}),
        )

    def _open_settings_popup(self):
        """打开设置卡片"""
        self._settings_popup.show()
        self._settings_popup.raise_()
        self._settings_popup.activateWindow()

    def _on_settings_closed(self):
        """设置卡片关闭时的回调"""
        # 可以在这里添加一些清理逻辑
        pass

    def _toggle_model_config_card(self):
        """切换模型配置卡片的显示"""
        # 隐藏其他卡片
        self._history_card.hide()
        self._settings_popup.hide()

        # 切换当前卡片
        if self._model_config_card.isVisible():
            self._model_config_card.hide()
        else:
            # 每次打开都重新加载配置
            self._load_model_config_to_card()
            self._model_config_card.show()

    def _load_model_config_to_card(self):
        """加载当前模型配置到卡片（仅参数配置，不显示连接信息）"""
        current_name = self._current_provider_name if self._current_provider_name else "无"
        setting = Settings.get_instance()

        saved_providers = setting.llm_saved_providers.value or {}
        provider_config = saved_providers.get(current_name, {})
        custom_vars = getattr(self.homepage, "global_variables", None)
        if current_name in (
            custom_vars.custom
            if custom_vars and hasattr(custom_vars, "custom")
            else {}
        ):
            config = custom_vars.custom[current_name].value.copy()
        else:
            config = provider_config.copy()
            config.pop("备注", None)
            config.pop("获取地址", None)
        # 只保留参数配置，移除连接信息
        config.pop("模型名称", None)
        config.pop("API_URL", None)
        config.pop("API_KEY", None)
        config.pop("模型列表", None)

        self._model_config_popup.set_config(current_name, config)

    def _toggle_history_card(self):
        """切换历史会话卡片的显示"""
        # 隐藏其他卡片
        self._model_config_card.hide()
        self._settings_popup.hide()

        # 切换当前卡片
        if self._history_card.isVisible():
            self._history_card.hide()
        else:
            self._history_card.show()
            # 刷新数据
            self._refresh_history_toggle_panel()

    def _refresh_history_toggle_panel(self):
        """刷新历史面板数据"""
        current_idx = (
            self.history_manager.find_index_by_session_id(self._current_session_id)
            if self._current_session_id and self.history_manager
            else None
        )
        history_list = self.history_manager.get_history_list() if self.history_manager else []
        self._history_popup_card.set_history(history_list, current_idx)

    def _on_history_session_selected(self, index: int):
        """从历史面板选择会话"""
        if index == -1:
            # 新建会话
            self._create_new_session()
        else:
            self._load_history_session_from_popup(index)
        # 关闭历史会话卡片
        self._history_card.hide()

    def _open_history_popup(self):
        if self._history_popup is None:
            self._history_popup = HistoryPopup(parent=self)
            self._history_popup.sessionSelected.connect(
                self._load_history_session_from_popup
            )
            self._history_popup.sessionArchived.connect(self._archive_history_session)
            self._history_popup.sessionRenamed.connect(self._rename_history_session)

        history_list = (
            self.history_manager.get_history_list() if self.history_manager else []
        )
        current_idx = (
            self.history_manager.find_index_by_session_id(self._current_session_id)
            if self._current_session_id
            else None
        )
        self._history_popup.set_history(history_list, current_idx)
        self._history_popup.show_at(self.history_btn)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 使用防抖避免频繁同步，只有在需要时才同步
        if not self._pending_resize_sync:
            self._pending_resize_sync = True
            self._resize_debounce_timer.start()
            # 重置 resize 完成定时器，将在 resize 结束后更新所有卡片
            self._resize_complete_timer.stop()
            self._resize_complete_timer.start()

    def _do_debounced_resize(self):
        """防抖执行卡片宽度同步 - 性能优化：只更新可见区域的卡片"""
        self._pending_resize_sync = False
        
        # 获取滚动区域视口
        scroll_area = getattr(self, 'chat_scroll_area', None)
        if scroll_area:
            viewport_rect = scroll_area.viewport().rect()
            viewport_top = scroll_area.verticalScrollBar().value()
            viewport_bottom = viewport_top + viewport_rect.height()
        
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if not (item and item.widget() and isinstance(item.widget(), MessageCard)):
                continue
            
            card = item.widget()
            
            # 性能优化：只同步可见区域的卡片
            if scroll_area:
                card_rect = card.geometry()
                card_top = card_rect.top()
                card_bottom = card_rect.bottom()
                
                # 如果卡片完全不可见（上下都不在视口内），跳过
                if card_bottom < viewport_top - 100 or card_top > viewport_bottom + 100:
                    continue
            
            card.sync_width()
    
    def _sync_all_cards_width(self):
        """resize 完成后更新所有卡片的宽度（包括非可见区域的）"""
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), MessageCard):
                item.widget().sync_width(force=True)
    
    def _sync_visible_cards_on_scroll(self):
        """滚动时更新新进入可见区域的卡片"""
        scroll_area = getattr(self, 'chat_scroll_area', None)
        if not scroll_area:
            return
        
        viewport_rect = scroll_area.viewport().rect()
        viewport_top = scroll_area.verticalScrollBar().value()
        viewport_bottom = viewport_top + viewport_rect.height()
        
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if not (item and item.widget() and isinstance(item.widget(), MessageCard)):
                continue
            
            card = item.widget()
            card_rect = card.geometry()
            card_top = card_rect.top()
            card_bottom = card_rect.bottom()
            
            # 只更新可见区域附近（缓冲200px）的卡片
            if card_bottom < viewport_top - 200 or card_top > viewport_bottom + 200:
                continue
            
            card.sync_width()

    def _on_config_applied(self, new_config: dict):
        current_name = self._current_provider_name
        if not current_name:
            return
        is_free_provider = current_name in FREE_PROVIDERS

        if is_free_provider:
            # 只更新参数，保留连接信息
            saved_providers = Settings.get_instance().llm_saved_providers.value or {}
            old_config = saved_providers.get(current_name, self._valid_configs.get(current_name, {}))
            old_config.update(new_config)
            self._valid_configs[current_name] = old_config
            saved_providers[current_name] = old_config
            Settings.get_instance().set(Settings.get_instance().llm_saved_providers, saved_providers, save=True)
            self._load_model_configs()
            InfoBar.success("已保存", "配置已保存到本地。", parent=self, duration=1500)
        else:
            if (
                hasattr(self.homepage, "global_variables")
                and self.homepage.global_variables
            ):
                custom_vars = self.homepage.global_variables.custom
                if current_name in custom_vars:
                    old_config = custom_vars[current_name].value
                    old_config.update(new_config)
                    custom_vars[current_name].value = old_config
                    self.homepage._on_global_variables_changed(
                        "custom", current_name, "update"
                    )

                self._load_model_configs()
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
        old_provider = self._current_provider_name
        old_model = self._current_model_name

        self._valid_configs.clear()

        setting = Settings.get_instance()
        default_config = {
            "模型名称": setting.llm_model.value,
            "API_KEY": setting.llm_api_key.value,
            "API_URL": setting.llm_api_base.value,
            "最大Token": setting.llm_max_tokens.value,
            "温度": setting.llm_temperature.value,
            "启用技能": setting.llm_enabled_skills.value,
        }
        try:
            custom_vars = getattr(self.homepage, "global_variables", None)
            if custom_vars and hasattr(custom_vars, "custom"):
                for config_name, var_obj in custom_vars.custom.items():
                    if hasattr(var_obj, "value") and isinstance(var_obj.value, dict):
                        val = var_obj.value
                        if {"API_URL", "API_KEY", "模型名称"}.issubset(val.keys()):
                            self._valid_configs[config_name] = val
        except Exception as e:
            logger.error(f"[ERROR] 加载自定义模型配置失败: {e}")

        saved_providers = setting.llm_saved_providers.value or {}
        for provider_name in saved_providers:
            config = saved_providers[provider_name].copy()
            config.pop("备注", None)
            config.pop("获取地址", None)
            self._valid_configs[provider_name] = config

        # 恢复或设置当前选中的服务商和模型
        if saved_model and saved_model in self._valid_configs:
            self._current_provider_name = saved_model
        elif old_provider and old_provider in self._valid_configs:
            self._current_provider_name = old_provider
        else:
            self._current_provider_name = list(self._valid_configs.keys())[0] if self._valid_configs else ""

        if self._current_provider_name:
            provider_config = self._valid_configs.get(self._current_provider_name, {})
            self._current_model_name = provider_config.get("模型名称", "")
        else:
            self._current_model_name = ""

        self._update_model_selector_btn()
        self._refresh_context_usage_indicator()

    def _load_agent_list(self):
        """加载智能体列表到选择器（仅显示 primary agents）"""
        if not self._agent_manager or not hasattr(self, "input_area"):
            return
        self._suppress_agent_intro = True
        agents = self._agent_manager.list_primary_agents()
        self.input_area._agent_combo.clear()
        for agent in agents:
            self.input_area._agent_combo.addItem(agent.name, agent.description)
        if self.input_area._agent_combo.count() > 0:
            self.input_area._agent_combo.setCurrentIndex(0)
            self._current_agent = self.input_area._agent_combo.currentText()
        self._suppress_agent_intro = False

    def _on_agent_changed(self, agent_name: str):
        """智能体切换处理"""
        logger.info(f"[DEBUG] _on_agent_changed called: agent_name={agent_name}")
        if not agent_name or not self._chat_engine:
            logger.info(
                f"[DEBUG] _on_agent_changed: early return, agent_name={agent_name}, _chat_engine={self._chat_engine}"
            )
            return
        self._current_agent = agent_name
        self._chat_engine.switch_agent(agent_name)
        if hasattr(self, "input_area") and hasattr(self.input_area, "_agent_combo"):
            idx = self.input_area._agent_combo.findText(agent_name)
            if idx >= 0:
                self.input_area._agent_combo.blockSignals(True)
                self.input_area._agent_combo.setCurrentIndex(idx)
                self.input_area._agent_combo.blockSignals(False)
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
            mode = agent.mode
            hidden = "hidden" if agent.hidden else "visible"
            self.input_area._agent_combo.setToolTip(
                f"{agent.name}: {agent.description}\nMode: {mode}, {hidden}"
            )

    def _on_task_state_changed(self, task_state):
        if not task_state:
            return
        self._latest_task_state = task_state

    def _create_new_session(self):
        if self._chat_engine:
            self._chat_engine.stop()

        self._is_streaming = False
        self._tool_cancelled_by_user = False
        self._toggle_send_stop(False)

        if self._tool_floating_widget:
            self._tool_floating_widget.clear()
            self._tool_floating_widget.setVisible(False)

        if self._sub_agent_floating_widget:
            self._sub_agent_floating_widget.setVisible(False)

        try:
            self._auto_save_current_session()
        except Exception:
            logger.exception(
                "Failed to auto-save current session before creating a new session"
            )

        self._cache_current_session_cards()
        session = self.session_manager.create_new_session()
        self._current_session_id = session.session_id
        self._history_preview_messages = None
        self._history_preview_session_data = None
        self._history_preview_opening = False
        self._clear_chat_area()
        self.title_edit.setText("新对话")
        self.node_preview.clear_nodes()
        if self._todo_floating_widget:
            self._todo_floating_widget.clear()
        if self._tool_executor:
            self._tool_executor.clear_todo_list()
            self._tool_executor.set_session_context(self._current_session_id)  # 同步更新 session_id
        if self._question_floating_widget:
            self._question_floating_widget.clear()
        self._question_tool_call_id = None
        self._load_agent_list()
        self._on_task_state_changed(session.task_state)

        is_canvas = self._is_on_canvas()
        logger.info(f"[DEBUG] _create_new_session: is_on_canvas={is_canvas}")
        if is_canvas:
            self._on_agent_changed("canvas")

        QTimer.singleShot(0, self._show_initial_welcome)
        self._refresh_context_usage_indicator()

    def _display_current_session(self):
        session = self.session_manager.get_current_session()
        if not session:
            self._clear_chat_area()
            return

        self._on_task_state_changed(session.task_state)
        self.title_edit.setText(session.topic_summary or session.name or "新对话")

        # 关键修复：同步 _current_session_id 与实际显示的会话
        self._current_session_id = session.session_id

        if self._restore_cached_session_cards(session):
            self._update_node_preview()
            self._refresh_context_usage_indicator()
            # 恢复缓存卡片后，多次滚动确保在底部
            QTimer.singleShot(50, self._scroll_to_bottom)
            QTimer.singleShot(150, self._scroll_to_bottom)
            return

        self._clear_chat_area()
        self._message_batch = group_messages_for_display(session.messages)
        self._message_batch_index = 0
        self._batch_size = 4

        if not self._message_batch:
            self._show_initial_welcome()
            return

        self._load_message_batch()

    def _show_initial_welcome(self):
        """仅在UI上显示欢迎卡片，不改动Session数据"""
        self._clear_chat_area(delete_widgets=False)
        welcome_card = self._get_or_create_welcome_card()
        self._displayed_session_id = None
        self._add_chat_widget(welcome_card)

    def _hide_welcome_cards(self):
        """隐藏所有欢迎卡片"""
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if getattr(widget, "_is_welcome", False):
                    widget.hide()

    def _load_message_batch(self):
        """分批加载消息，避免卡顿"""
        session = self.session_manager.get_current_session()
        if session:
            self._displayed_session_id = session.session_id
            # 关键修复：同步 _current_session_id 与实际显示的会话
            self._current_session_id = session.session_id

        self._render_message_to_card(self._message_batch)

        # 延迟滚动，确保卡片渲染完成后再滚动到底部
        # 使用多次滚动确保卡片高度变化后仍能保持在底部
        QTimer.singleShot(50, self._scroll_to_bottom)
        QTimer.singleShot(150, self._scroll_to_bottom)
        self._update_node_preview()
        self._refresh_context_usage_indicator()

    def _initialize_history_manager(self):
        canvas_name = getattr(self.homepage, "workflow_name", "default") or "default"
        self.history_manager = HistoryManager(canvas_name)

    def _restore_latest_session(self) -> bool:
        if not self.history_manager:
            logger.info("[DEBUG] _restore_latest_session: no history_manager")
            return False

        latest = self.history_manager.load_most_recently_updated_session()
        if not latest:
            logger.info(
                "[DEBUG] _restore_latest_session: no most recently updated session"
            )
            return False

        messages = latest.get("messages", [])
        if not messages:
            logger.info("[DEBUG] _restore_latest_session: no messages")
            return False

        session_id = latest.get("session_id", "")
        restored = ChatSession.from_dict(
            {
                "session_id": session_id,
                "name": latest.get("title") or latest.get("name") or "最近会话",
                "messages": messages,
                "topic_summary": latest.get("title", ""),
                "compaction_state": latest.get("compaction_state", {}),
                "compaction_cache": latest.get("compaction_cache", {}),
                "created_at": latest.get("created_at"),
                "last_updated": latest.get("last_updated"),
            }
        )
        self.session_manager.set_current_session(restored)
        self._history_preview_messages = None
        self._current_session_id = session_id
        self.title_edit.setText(latest.get("title") or "最近会话")
        self._load_agent_list()
        if self._tool_executor:
            self._tool_executor.set_session_context(self._current_session_id)
        is_canvas = getattr(self.homepage, "workflow_name", None) is not None
        logger.info(f"[DEBUG] _restore_latest_session: is_on_canvas={is_canvas}")
        if is_canvas and self._current_agent != "canvas":
            self._on_agent_changed("canvas")
        self._display_current_session()
        self._refresh_context_usage_indicator()
        return True

    def _toggle_history_mode(self, enabled: bool):
        if enabled:
            self._cache_current_session_cards()
            if self._current_session_id is None:
                curr_session = self.session_manager.get_current_session()
                if curr_session and curr_session.messages:
                    self._history_preview_session_data = curr_session.to_dict()
                else:
                    self._history_preview_session_data = None

            self._in_history_mode = True
            self.chat_layout.setAlignment(Qt.AlignTop)
            self._display_history_sessions()
        else:
            self._in_history_mode = False
            self.chat_layout.setAlignment(Qt.AlignBottom)

            if self._history_preview_opening:
                self._history_preview_opening = False
                self._history_preview_messages = None
                self._display_current_session()
            else:
                if self._history_preview_session_data:
                    from app.llm_chatter.utils.chat_session import (
                        ChatSession,
                    )

                    restored = ChatSession.from_dict(self._history_preview_session_data)
                    self.session_manager.set_current_session(restored)
                    self._current_session_id = restored.session_id
                    self._history_preview_session_data = None

                self._history_preview_messages = None
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

    def _open_diff_viewer(self):
        """打开差异查看窗口，显示当前会话修改文件的 git diff"""
        try:
            # 获取当前会话 ID
            session_id = self._current_session_id
            if not session_id:
                InfoBar.warning("提示", "当前没有活动会话", parent=self)
                return

            # 从 ToolExecutor 获取当前会话的文件操作记录
            if not self._tool_executor:
                InfoBar.warning("提示", "工具执行器未初始化", parent=self)
                return

            # 获取文件操作记录
            from app.llm_chatter.utils.file_operation_recorder import FileOperationRecorder
            from app.llm_chatter.utils.session_store import SessionStore

            session_store = SessionStore()
            file_recorder = FileOperationRecorder(session_store)

            # 获取当前会话的所有文件操作
            operations = file_recorder.get_all_operations_for_session(session_id)

            if not operations:
                InfoBar.info("提示", "当前会话没有文件修改记录", parent=self)
                return

            # 提取文件路径列表（去重）
            file_paths = list({op.get("file_path") for op in operations if op.get("file_path")})

            if not file_paths:
                InfoBar.info("提示", "未找到修改的文件", parent=self)
                return

            # 生成 git diff
            try:
                diff_output = DiffHtmlGenerator.get_diff_for_files(file_paths, session_id)
            except Exception as e:
                logger.warning(f"[DiffViewer] 获取 git diff 失败: {e}")
                diff_output = ""

            # 生成 HTML 报告
            html = DiffHtmlGenerator.generate_html_report(diff_output or "", session_id)

            # 创建并显示差异查看窗口
            viewer = DiffViewerWindow(parent=self)
            viewer.load_html(html)
            viewer.show()

            logger.info(f"[DiffViewer] 已打开差异查看窗口，文件数: {len(file_paths)}")

        except ImportError as e:
            logger.error(f"[DiffViewer] 导入模块失败: {e}")
            InfoBar.error("错误", f"功能加载失败: {str(e)}", parent=self)
        except Exception as e:
            logger.exception(f"[DiffViewer] 打开差异查看器失败: {e}")
            InfoBar.error("错误", f"打开差异查看器失败: {str(e)}", parent=self)

    def _display_history_sessions(self):
        self._clear_chat_area()

        history_list = self.history_manager.get_history_list()
        if not history_list:
            placeholder = QLabel("暂无历史对话记录", self)
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #999;")
            self.chat_layout.addWidget(placeholder)
            return

        current_idx = (
            self.history_manager.find_index_by_session_id(self._current_session_id)
            if self._current_session_id
            else None
        )

        reversed_history = list(enumerate(history_list[::-1]))
        for display_idx, session in reversed_history:
            title = session["title"]
            last_time = session["last_time"]
            original_index = len(history_list) - 1 - display_idx

            is_current = current_idx is not None and current_idx == original_index

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

    def _clear_chat_area(self, delete_widgets: bool = True):
        self._current_assistant_card = None
        self._displayed_session_id = None
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            if item.widget():
                if delete_widgets:
                    item.widget().deleteLater()
                else:
                    item.widget().hide()

    def _take_chat_widgets(self) -> List[QWidget]:
        widgets: List[QWidget] = []
        self._current_assistant_card = None
        self._displayed_session_id = None
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            if item and item.widget():
                item.widget().hide()
                widgets.append(item.widget())
        return widgets

    def _cache_current_session_cards(self):
        session = self.session_manager.get_current_session()
        widgets = self._take_chat_widgets()
        if not session or not session.messages:
            return

        message_cards = [
            w
            for w in widgets
            if isinstance(w, MessageCard) and self._is_widget_alive(w)
        ]
        if message_cards:
            self._session_card_cache[session.session_id] = message_cards

        self._cleanup_session_card_cache()

    def _cleanup_session_card_cache(self):
        from app.llm_chatter.constants import (
            MAX_SESSION_CARD_CACHE_SIZE,
        )

        if len(self._session_card_cache) <= MAX_SESSION_CARD_CACHE_SIZE:
            all_session_ids = {
                s.session_id for s in self.session_manager.get_all_sessions()
            }
            stale_ids = set(self._session_card_cache.keys()) - all_session_ids
            for sid in stale_ids:
                self._session_card_cache.pop(sid, None)
            return

        all_session_ids = {
            s.session_id for s in self.session_manager.get_all_sessions()
        }
        stale_ids = set(self._session_card_cache.keys()) - all_session_ids
        for sid in stale_ids:
            self._session_card_cache.pop(sid, None)

        if len(self._session_card_cache) > MAX_SESSION_CARD_CACHE_SIZE:
            current_ids = all_session_ids & set(self._session_card_cache.keys())
            for sid in list(self._session_card_cache.keys()):
                if sid not in current_ids:
                    self._session_card_cache.pop(sid, None)
                    if len(self._session_card_cache) <= MAX_SESSION_CARD_CACHE_SIZE:
                        break

    def _is_widget_alive(self, widget: Optional[QWidget]) -> bool:
        if widget is None:
            return False
        try:
            return not sip.isdeleted(widget)
        except Exception:
            return False

    def _restore_cached_session_cards(self, session: ChatSession) -> bool:
        if not session.messages:
            return False

        cached_cards = self._session_card_cache.get(session.session_id)
        if not cached_cards:
            return False

        alive_cards = [card for card in cached_cards if self._is_widget_alive(card)]
        if len(alive_cards) != len(cached_cards):
            self._session_card_cache.pop(session.session_id, None)
        if not alive_cards:
            return False

        self._clear_chat_area(delete_widgets=False)
        for card in alive_cards:
            self._add_chat_widget(card)
        self._displayed_session_id = session.session_id
        # 关键修复：同步 _current_session_id 与实际显示的会话
        self._current_session_id = session.session_id
        self._current_assistant_card = (
            alive_cards[-1]
            if alive_cards and alive_cards[-1].role == "assistant"
            else None
        )
        return True

    def _get_or_create_welcome_card(self) -> MessageCard:
        agent = (
            self._agent_manager.get_agent(self._current_agent)
            if self._agent_manager
            else None
        )
        agent_name = agent.name if agent else ""
        agent_desc = agent.description if agent else ""
        cache_key = agent_name or "__default__"
        welcome_card = self._welcome_card_cache.get(cache_key)
        if not self._is_widget_alive(welcome_card):
            welcome_card = create_welcome_card(self, agent_name, agent_desc)
            welcome_card._is_welcome = True
            welcome_card.contextActionRequested.connect(
                self.handle_recommended_question
            )
            self._welcome_card_cache[cache_key] = welcome_card
        return welcome_card

    def _sanitize_user_message_for_display(self, content: str) -> str:
        if not isinstance(content, str):
            return content

        pattern = re.compile(
            r"^\[Task Stage:.*?\]\n\[Current Goal:.*?\]\n\[Verification:.*?\]\n\n",
            re.DOTALL,
        )
        return pattern.sub("", content, count=1)

    def _render_message_to_card(self, batches: List[List[Dict[str, Any]]]):
        for batch in batches:
            role = batch[0].get("role")
            timestamp = batch[0].get(
                "timestamp", datetime.now().strftime("%Y-%m-%d %H:%M")
            )

            if role == "user":
                content = self._sanitize_user_message_for_display(
                    batch[0].get("content", "")
                )
                self._append_user_message(
                    content,
                    timestamp=timestamp,
                    tag_params=batch[0].get("params", {}),
                )

            if role == "assistant" or role == "tool":
                assistant_card = self._append_assistant_message(timestamp=timestamp)
                for msg in batch:
                    if msg.get("role") == "assistant" and msg.get("content", ""):
                        assistant_card.append_text(msg.get("content", {}))
                    elif msg.get("role") == "tool" and msg.get("content", ""):
                        assistant_card.append_tool_result(
                            tool_name=msg.get("name", ""),
                            arguments=msg.get("arguments", {}),
                            result=msg.get("content", ""),
                            success=bool(msg.get("success", True)),
                            tool_call_id=msg.get("tool_call_id", ""),
                        )
                assistant_card.finish_streaming()

    def _get_rendered_message_cards(self) -> List[MessageCard]:
        cards: List[MessageCard] = []
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if not item or not item.widget():
                continue
            widget = item.widget()
            if not isinstance(widget, MessageCard):
                continue
            if getattr(widget, "_is_welcome", False):
                continue
            if widget.role not in ("user", "assistant"):
                continue
            cards.append(widget)
        return cards

    def _get_current_user_round_index(self) -> int:
        """获取当前 user message 应该是第几个 user（从 0 开始）"""
        count = 0
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if not item or not item.widget():
                continue
            widget = item.widget()
            if isinstance(widget, MessageCard) and widget.role == "user":
                count += 1
        return count

    def _find_user_round_index_for_card(self, card: MessageCard) -> Optional[int]:
        round_index = 0
        for rendered_card in self._get_rendered_message_cards():
            if rendered_card.role != "user":
                continue
            if rendered_card is card:
                return round_index
            round_index += 1
        return None

    def findRoundIndexForCard(self, card: MessageCard) -> Optional[int]:
        """
        供 MessageCard 回调使用，根据 assistant card 查找对应的 round_index。
        通过遍历布局找到该 assistant card 前面的 user card 数量来确定 round_index。
        """
        if not card or card.role != "assistant":
            return None
        # 遍历布局，统计该 assistant card 之前有多少 user card
        round_index = 0
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if not item or not item.widget():
                continue
            widget = item.widget()
            if not isinstance(widget, MessageCard):
                continue
            if widget is card:
                # 找到了，返回当前 round_index
                return round_index
            if widget.role == "user":
                round_index += 1
        return None

    def _remove_cards_for_round(self, round_index: int) -> bool:
        session = self.session_manager.get_current_session()
        if not session:
            return False

        canonical_messages = consolidate_messages(session.messages)
        round_ranges = get_user_round_ranges(canonical_messages)
        if round_index < 0 or round_index >= len(round_ranges):
            return False

        start_idx, end_idx = round_ranges[round_index]
        cards_to_remove = end_idx - start_idx

        user_card_idx = 0
        removed = 0
        removing = False
        widgets_to_remove = []

        # 遍历 chat_layout，直接统计可见的 user card 数量来确定 round_index 对应的位置
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if not item or not item.widget():
                continue
            widget = item.widget()
            if not isinstance(widget, MessageCard):
                continue
            if getattr(widget, "_is_welcome", False):
                continue
            if widget.role not in ("user", "assistant"):
                continue

            if widget.role == "user":
                if user_card_idx == round_index:
                    widgets_to_remove.append(widget)
                    removed += 1
                    removing = True
                else:
                    removing = False
                user_card_idx += 1
            elif widget.role == "assistant" and removing:
                widgets_to_remove.append(widget)
                removed += 1

            if removed >= cards_to_remove:
                break

        logger.info(
            f"[DELETE] Cards to remove: {len(widgets_to_remove)}, cards_to_remove: {cards_to_remove}"
        )

        # 实际执行删除
        for widget in widgets_to_remove:
            try:
                if not self._is_widget_alive(widget):
                    logger.warning(f"[DELETE] Widget already deleted: {widget}")
                    continue

                # 先从 layout 移除
                layout_removed = False
                for i in range(self.chat_layout.count()):
                    item = self.chat_layout.itemAt(i)
                    if item and item.widget() is widget:
                        self.chat_layout.removeItem(item)
                        layout_removed = True
                        break

                if layout_removed:
                    widget.deleteLater()
                    logger.info(f"[DELETE] Widget deleted: role={widget.role}")
                else:
                    logger.warning(
                        f"[DELETE] Widget not found in layout: role={widget.role}"
                    )
            except Exception as e:
                logger.error(f"[DELETE] Error deleting widget: {e}")

        return removed > 0

    def _remove_cards_from_round(self, round_index: int) -> bool:
        rendered_cards = self._get_rendered_message_cards()
        user_card_count = sum(1 for c in rendered_cards if c.role == "user")
        if round_index >= user_card_count:
            return False

        user_card_idx = 0
        removing = False
        widgets_to_remove = []
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if not item or not item.widget():
                continue
            widget = item.widget()
            if not isinstance(widget, MessageCard):
                continue
            if getattr(widget, "_is_welcome", False):
                continue
            if widget.role not in ("user", "assistant"):
                continue

            if widget.role == "user":
                if user_card_idx >= round_index:
                    widgets_to_remove.append(widget)
                    removing = True
                else:
                    user_card_idx += 1
            elif widget.role == "assistant" and removing:
                widgets_to_remove.append(widget)

        for widget in widgets_to_remove:
            for i in range(self.chat_layout.count()):
                item = self.chat_layout.itemAt(i)
                if item and item.widget() is widget:
                    self.chat_layout.removeItem(item)
                    break
            widget.deleteLater()

        return True

    def _invalidate_current_session_card_cache(self):
        session = self.session_manager.get_current_session()
        if not session:
            return
        self._session_card_cache.pop(session.session_id, None)

    def _persist_session_after_mutation(self):
        session = self.session_manager.get_current_session()
        if not session:
            return

        session.set_messages(session.messages, preserve_compaction=False)

        if not session.messages:
            if self._current_session_id is not None and self.history_manager:
                idx = self.history_manager.find_index_by_session_id(
                    self._current_session_id
                )
                if idx is not None:
                    self.history_manager.archive_history(idx)
                self._current_session_id = None
            return

        if self.history_manager:
            if self._current_session_id is not None:
                idx = self.history_manager.find_index_by_session_id(
                    self._current_session_id
                )
                if idx is not None:
                    self.history_manager.update_session(
                        idx,
                        session.messages,
                        compaction_state=getattr(session, "compaction_state", {}),
                        compaction_cache=getattr(session, "compaction_cache", {}),
                    )
                else:
                    self.history_manager.save_session(
                        session.messages,
                        session_id=session.session_id,
                        compaction_state=getattr(session, "compaction_state", {}),
                        compaction_cache=getattr(session, "compaction_cache", {}),
                    )
                    self._current_session_id = session.session_id
            else:
                self.history_manager.save_session(
                    session.messages,
                    session_id=session.session_id,
                    compaction_state=getattr(session, "compaction_state", {}),
                    compaction_cache=getattr(session, "compaction_cache", {}),
                )
                self._current_session_id = session.session_id

    def _refresh_session_view_after_mutation(self):
        self._invalidate_current_session_card_cache()
        self._history_preview_messages = None
        self._display_current_session()
        self._refresh_context_usage_indicator()

    def _sync_current_assistant_card_ref(self):
        self._current_assistant_card = None
        for i in range(self.chat_layout.count() - 1, -1, -1):
            item = self.chat_layout.itemAt(i)
            if not item or not item.widget():
                continue
            widget = item.widget()
            if not isinstance(widget, MessageCard):
                continue
            if getattr(widget, "_is_welcome", False):
                continue
            if widget.role == "assistant":
                self._current_assistant_card = widget
                return

    def _finalize_local_session_mutation(self):
        self._invalidate_current_session_card_cache()
        self._history_preview_messages = None
        session = self.session_manager.get_current_session()
        if not session or not session.messages:
            self._clear_chat_area()
            self.node_preview.clear_nodes()
            self._current_assistant_card = None
            self._show_initial_welcome()
            self._refresh_context_usage_indicator()
            return

        self._sync_current_assistant_card_ref()
        self._update_node_preview()
        self._refresh_context_usage_indicator()
        self._sync_node_preview_to_scroll()

    def _on_clear_shortcut(self):
        session = self.session_manager.get_current_session()
        if session:
            self._session_card_cache.pop(session.session_id, None)
        self._clear_chat_area()
        self.node_preview.clear_nodes()
        if session:
            session.clear()
            self._on_task_state_changed(session.task_state)
        welcome_card = self._get_or_create_welcome_card()
        QTimer.singleShot(0, lambda: self._add_chat_widget(welcome_card))
        self.title_edit.setText("新对话")

    def _add_chat_widget(self, widget: QWidget):
        if not self._is_widget_alive(widget):
            return
        widget.show()
        if isinstance(widget, MessageCard):
            widget.sync_width()
            if widget.role == "user":
                self.chat_layout.addWidget(widget, 0, Qt.AlignRight)
            else:
                self.chat_layout.addWidget(widget, 0, Qt.AlignLeft)
        else:
            self.chat_layout.addWidget(widget)

    def _archive_history_session(self, index: int):
        history_list = self.history_manager.get_history_list()
        if index < 0 or index >= len(history_list):
            return

        target_session_id = history_list[index].get("session_id")
        archived_current = (
            self._current_session_id is not None
            and target_session_id == self._current_session_id
        )

        old_session_manager = self.session_manager
        old_chat_engine = self._chat_engine

        # 清理归档会话的文件操作记录和备份
        if self._tool_executor and self._tool_executor.file_recorder:
            self._tool_executor.file_recorder.clear_session(target_session_id)
            logger.info(f"[FileRecorder] 已清理归档会话的文件操作记录: {target_session_id}")

        archived = self.history_manager.archive_history(index)

        if archived_current and archived:
            self.session_manager = SessionManager()
            self.session_manager.create_new_session()
            new_session = self.session_manager.get_current_session()
            self._current_session_id = new_session.session_id

            if old_chat_engine and hasattr(old_chat_engine, "set_session_manager"):
                old_chat_engine.set_session_manager(self.session_manager)

            if self._tool_executor:
                self._tool_executor.set_session_context(self._current_session_id)

            self._clear_chat_area()
            self._show_initial_welcome()
            self.title_edit.setText("新对话")

        # 刷新历史会话卡片
        if self._history_card.isVisible():
            self._refresh_history_toggle_panel()

    def _rename_history_session(self, index: int, new_title: str):
        if not self.history_manager:
            return
        self.history_manager.update_session_title(index, new_title)
        # 刷新历史会话卡片
        if self._history_card.isVisible():
            self._refresh_history_toggle_panel()

    def _load_history_session(self, index: int):
        self._load_history_session_from_popup(index)

    def _load_history_session_from_popup(self, index: int):
        if self._is_streaming:
            self._on_stop_clicked()

        try:
            self._auto_save_current_session()
        except Exception:
            logger.exception(
                "Failed to auto-save current session before loading history"
            )

        self._tool_executor.reset_session_state()

        history_list = self.history_manager.get_history_list()
        if index < 0 or index >= len(history_list):
            return

        session_record = history_list[index]
        session_id = session_record.get("session_id")
        messages = self.history_manager.get_session_by_index(index)
        if not messages:
            return

        title = self.history_manager.get_current_title(index)
        restored = ChatSession.from_dict(
            {
                "session_id": session_id,
                "name": title or "历史对话",
                "messages": messages,
                "topic_summary": title or "",
                "compaction_state": session_record.get("compaction_state", {}),
                "compaction_cache": session_record.get("compaction_cache", {}),
            }
        )
        self.session_manager.set_current_session(restored)
        self._history_preview_messages = None
        self._current_session_id = session_id
        self.title_edit.setText(title or "历史对话")
        if self._history_popup:
            self._history_popup.close()

        # 更新工具执行器的会话上下文
        if self._tool_executor:
            self._tool_executor.set_session_context(self._current_session_id)

        self._display_current_session()

        # 刷新历史会话卡片
        if self._history_card.isVisible():
            self._refresh_history_toggle_panel()

    def _append_user_message(
        self, content: str, timestamp: str = None, tag_params: dict = None
    ):
        session = self.session_manager.get_current_session()
        if session:
            self._displayed_session_id = session.session_id
        
        # 计算当前 user message 的 round_index
        user_round_index = self._get_current_user_round_index()
        
        card = MessageCard(
            parent=self,
            role="user",
            timestamp=timestamp,
            tag_params=tag_params
            or {},
        )
        card._round_index = user_round_index
        card.update_content(content)
        card.finish_streaming()
        card.deleteRequested.connect(lambda: self._delete_message(card))
        card.undoRequested.connect(lambda: self._undo_from_message(card))
        card.actionRequested.connect(self._on_code_action)
        self._add_chat_widget(card)
        self._scroll_to_bottom()

        # 更新当前 assistant 的 round_index 为这个 user message 的索引
        self._current_assistant_round_index = user_round_index

        self._update_node_preview()
        return card

    def _append_assistant_message(self, timestamp: str = None) -> MessageCard:
        session = self.session_manager.get_current_session()
        if session:
            self._displayed_session_id = session.session_id
        card = MessageCard(parent=self, role="assistant", timestamp=timestamp)
        # 设置卡片对应的 round_index（来自之前 user message 分配的）
        card._round_index = self._current_assistant_round_index
        card.viewer._install_dialog_filter()
        card.actionRequested.connect(self._on_code_action)
        card.contextActionRequested.connect(self.handle_recommended_question)
        card.toolDiffRequested.connect(self._on_tool_diff_requested)
        card.cardDiffRequested.connect(self._on_card_diff_requested)
        card.saveFileRequested.connect(self._on_save_file_requested)
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
        messages = consolidate_messages(session.messages)

        node_data = []
        current_user_msg = None

        for msg in messages:
            if msg["role"] == "user":
                current_user_msg = content_to_text(msg.get("content", ""))[:30]
            elif msg["role"] == "assistant" and current_user_msg:
                timestamp = (
                    msg.get("timestamp", "")[-5:] if msg.get("timestamp") else ""
                )
                node_data.append((current_user_msg, timestamp))
                current_user_msg = None

        if current_user_msg:
            node_data.append((current_user_msg, ""))

        self.node_preview.update_nodes(node_data)
        self._sync_node_preview_to_scroll()

    def _sync_node_preview_to_scroll(self):
        if not hasattr(self, "chat_scroll_area") or not hasattr(self, "node_preview"):
            return

        user_widgets = []
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if not item or not item.widget():
                continue
            widget = item.widget()
            if isinstance(widget, MessageCard) and widget.role == "user":
                user_widgets.append(widget)

        if not user_widgets:
            self._last_visible_user_pair_index = -1
            self.node_preview.set_visible_node(-1)
            self.node_preview.set_progress_position(-1)
            return

        scroll_bar = self.chat_scroll_area.verticalScrollBar()
        viewport_height = self.chat_scroll_area.viewport().height()
        visible_top = scroll_bar.value()
        anchor_y = visible_top + max(viewport_height / 2, 1)
        user_tops = [widget.y() for widget in user_widgets]

        if len(user_tops) == 1:
            progress = 0.0
        elif anchor_y <= user_tops[0]:
            progress = 0.0
        elif anchor_y >= user_tops[-1]:
            progress = float(len(user_tops) - 1)
        else:
            progress = 0.0
            for idx in range(len(user_tops) - 1):
                start_top = user_tops[idx]
                end_top = user_tops[idx + 1]
                if start_top <= anchor_y <= end_top:
                    span = max(end_top - start_top, 1)
                    ratio = (anchor_y - start_top) / span
                    progress = idx + ratio
                    break

        visible_index = min(
            max(int(round(progress)), 0),
            len(user_tops) - 1,
        )
        self.node_preview.set_progress_position(progress)
        if visible_index != self._last_visible_user_pair_index:
            self._last_visible_user_pair_index = visible_index
            self.node_preview.set_visible_node(visible_index)

    def _on_node_preview_clicked(self, index: int):
        pair_index = 0
        target_widget = None
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if not item or not item.widget():
                continue
            widget = item.widget()
            if not isinstance(widget, MessageCard):
                continue
            if widget.role == "user":
                if pair_index == index:
                    target_widget = widget
                    break
                pair_index += 1

        if target_widget:
            self.node_preview.set_progress_position(index)
            self.chat_scroll_area.verticalScrollBar().setValue(target_widget.y())

    def _on_scroll_changed(self, value):
        self._sync_node_preview_to_scroll()
        # 性能优化：滚动时延迟更新新可见区域的卡片宽度
        QTimer.singleShot(100, self._sync_visible_cards_on_scroll)

    def _truncate_session_from_user_round(self, round_index: int) -> bool:
        session = self.session_manager.get_current_session()
        if not session:
            return False

        canonical_messages = consolidate_messages(session.messages)
        round_ranges = get_user_round_ranges(canonical_messages)
        if round_index < 0 or round_index >= len(round_ranges):
            return False

        cutoff_index = round_ranges[round_index][0]
        session.set_messages(
            canonical_messages[:cutoff_index], preserve_compaction=False
        )
        self._persist_session_after_mutation()
        self._remove_cards_from_round(round_index)
        self._finalize_local_session_mutation()
        return True

    def _delete_message(self, card: MessageCard):
        if card.role != "user":
            return
        round_index = self._find_user_round_index_for_card(card)
        if round_index is None:
            return
        self._delete_user_round(round_index)

    def _delete_user_round(self, round_index: int):
        session = self.session_manager.get_current_session()
        if not session:
            return

        logger.info(f"[DELETE] Starting deletion: round_index={round_index}")

        # Step 1: 先删除UI卡片，确保用户立即看到效果
        ui_deleted = self._remove_cards_for_round(round_index)
        logger.info(f"[DELETE] UI cards deleted: {ui_deleted}")

        # Step 2: 更新 session 数据
        canonical_messages = consolidate_messages(session.messages)
        round_ranges = get_user_round_ranges(canonical_messages)
        if round_index < 0 or round_index >= len(round_ranges):
            logger.warning(f"[DELETE] Invalid round_index: {round_index}")
            return

        start_idx, end_idx = round_ranges[round_index]
        new_messages = canonical_messages[:start_idx] + canonical_messages[end_idx:]
        session.set_messages(new_messages, preserve_compaction=False)

        logger.info(
            f"[DELETE] Session messages updated: {len(canonical_messages)} -> {len(new_messages)}"
        )

        # Step 3: 保存session数据
        try:
            self._persist_session_after_mutation()
            logger.info("[DELETE] Session persisted successfully")
        except Exception as e:
            logger.error(f"[DELETE] Failed to persist session: {e}")

        # Step 4: 收尾处理
        self._finalize_local_session_mutation()

    def _undo_from_message(self, card: MessageCard):
        if card.role != "user":
            return
        round_index = self._find_user_round_index_for_card(card)
        if round_index is None:
            return

        if self._is_streaming:
            self._on_stop_clicked()

        # 获取待回滚的文件操作（从该轮次到最后的全部）
        all_call_ids = self._get_all_tool_call_ids_from_round(round_index)
        

        # 如果有文件操作，显示预览对话框
        if all_call_ids and self._tool_executor and self._tool_executor.file_recorder:
            # 获取所有 call_id 对应的操作
            operations = []
            for call_id in all_call_ids:
                ops = self._tool_executor.file_recorder.get_operations_for_preview(
                    self._current_session_id, call_id
                )
                operations.extend(ops)
            # 去重（基于 id 或 file_path+call_id 组合）
            seen = set()
            unique_ops = []
            for op in operations:
                key = (op.get("id"), op.get("file_path"), op.get("call_id"))
                if key not in seen:
                    seen.add(key)
                    unique_ops.append(op)
            operations = unique_ops
            
            
            if operations:
                dialog = FileUndoPreviewDialog(operations, self)
                result = dialog.exec_()

                if result == FileUndoPreviewDialog.CANCEL:
                    return  # 取消撤销，什么都不做

                # 执行回滚 - 只还原选中的操作
                selected_ops = dialog.get_selected_operations()
                if selected_ops:
                    result = self._tool_executor.file_recorder.rollback_operations(selected_ops)
                    self._show_undo_result(result)

        user_input = card.get_plain_text()
        context_tags = card.context_tags.copy()
        if not self._truncate_session_from_user_round(round_index):
            return

        self.input_area.setPlainText(user_input)
        self.input_area.moveCursor(QTextCursor.End)
        self.input_area._on_text_changed()
        self.input_area.setFocus()

    def _get_last_tool_call_id_after_round(self, round_index: int) -> Optional[str]:
        """获取指定 round_index 之后最后一个 tool_call_id"""
        session = self.session_manager.get_current_session()
        if not session:
            return None

        canonical_messages = consolidate_messages(session.messages)
        round_ranges = get_user_round_ranges(canonical_messages)

        if round_index < 0 or round_index >= len(round_ranges):
            return None

        # 获取该 round 之后的所有消息的 start index
        _, end_idx = round_ranges[round_index]

        # 查找 end_idx 之后的所有 tool_call_id
        last_call_id = None
        for i in range(end_idx, len(canonical_messages)):
            msg = canonical_messages[i]
            if msg.get("role") == "tool":
                call_id = msg.get("tool_call_id")
                if call_id:
                    last_call_id = call_id

        return last_call_id

    def _get_all_tool_call_ids_from_round(self, round_index: int) -> List[str]:
        """获取从指定 round 到最后的所有 tool_call_id"""
        session = self.session_manager.get_current_session()
        if not session:
            return []

        canonical_messages = consolidate_messages(session.messages)
        round_ranges = get_user_round_ranges(canonical_messages)

        if round_index < 0 or round_index >= len(round_ranges):
            return []

        # 获取该 round 的起始位置，之后的所有消息都需要统计
        start_idx, _ = round_ranges[round_index]
        
        # 从该 round 的 user 消息开始，遍历到消息列表末尾
        call_ids = []
        for i in range(start_idx, len(canonical_messages)):
            msg = canonical_messages[i]
            role = msg.get("role")
            if role == "assistant":
                tool_calls = msg.get("tool_calls", [])
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        tid = tc.get("id")
                        if tid and tid not in call_ids:
                            call_ids.append(tid)
            elif role == "tool":
                # 也从 tool 消息中提取 tool_call_id
                tid = msg.get("tool_call_id")
                if tid and tid not in call_ids:
                    call_ids.append(tid)

        return call_ids

    def _get_tool_call_ids_in_round(self, round_index: int) -> List[str]:
        """获取指定 round 范围内的所有 tool_call_id（不包括后续 round）"""
        session = self.session_manager.get_current_session()
        if not session:
            return []

        canonical_messages = consolidate_messages(session.messages)
        round_ranges = get_user_round_ranges(canonical_messages)

        if round_index < 0 or round_index >= len(round_ranges):
            return []

        # 获取该 round 的范围
        start_idx, end_idx = round_ranges[round_index]
        
        # 只遍历该 round 范围内的消息
        call_ids = []
        for i in range(start_idx, end_idx):
            msg = canonical_messages[i]
            role = msg.get("role")
            if role == "assistant":
                tool_calls = msg.get("tool_calls", [])
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        tid = tc.get("id")
                        if tid and tid not in call_ids:
                            call_ids.append(tid)
            elif role == "tool":
                tid = msg.get("tool_call_id")
                if tid and tid not in call_ids:
                    call_ids.append(tid)

        return call_ids

    def _show_undo_result(self, result):
        """显示撤销结果"""
        if result.failed_count > 0:
            failed_list = "\n".join(f"  - {f}" for f in result.failed_files[:5])
            InfoBar.warning(
                "部分文件回滚失败",
                f"成功: {result.success_count}, 失败: {result.failed_count}\n{failed_list}",
                parent=self,
                duration=5000,
            )
        elif result.success_count > 0:
            InfoBar.success(
                "文件已回滚",
                f"已恢复 {result.success_count} 个文件",
                parent=self,
                duration=3000,
            )

    def _on_tool_diff_requested(self, tool_call_id: str):
        """
        处理工具差异对比请求
        
        Args:
            tool_call_id: 工具调用 ID
        """
        if not tool_call_id:
            return
        
        session = self.session_manager.get_current_session()
        if not session:
            return
        
        session_id = session.session_id
        
        # 检查是否有 file_recorder
        if not self._tool_executor or not self._tool_executor.file_recorder:
            logger.warning("[LLMChatter] file_recorder 未初始化")
            return
        
        try:
            # 获取该 tool_call_id 对应的文件操作记录
            operations = self._tool_executor.file_recorder.get_operations_for_preview(
                session_id=session_id,
                call_id=tool_call_id
            )
            
            if not operations:
                InfoBar.warning(
                    "无差异信息",
                    "此工具没有修改任何文件，或备份信息已丢失",
                    duration=3000,
                    parent=self,
                    position=InfoBarPosition.TOP_RIGHT,
                )
                return
            
            # 只取该工具产生的第一个文件操作（通常每个工具只修改一个文件）
            op = operations[0]
            backup_path = op.get("backup_path", "")

            if not backup_path:
                InfoBar.warning(
                    "无差异信息",
                    "备份路径无效",
                    duration=3000,
                    parent=self,
                    position=InfoBarPosition.TOP_RIGHT,
                )
                return

            # 编辑前备份路径 -> 编辑后备份路径（固定后缀 .after.bak）
            from pathlib import Path
            import difflib

            backup_file = Path(backup_path)
            after_backup_path = str(backup_file.with_suffix('.after.bak'))
            after_backup_file = Path(after_backup_path)

            # 检查编辑后备份是否存在
            if not after_backup_file.exists():
                InfoBar.warning(
                    "无差异信息",
                    "编辑后备份文件不存在，可能该工具执行于早期版本",
                    duration=3000,
                    parent=self,
                    position=InfoBarPosition.TOP_RIGHT,
                )
                return

            try:
                # 读取编辑前和编辑后的备份文件进行对比
                with open(backup_path, 'r', encoding='utf-8', errors='replace') as f:
                    old_content = f.read()
                with open(after_backup_path, 'r', encoding='utf-8', errors='replace') as f:
                    new_content = f.read()
            except FileNotFoundError as e:
                InfoBar.error(
                    "文件不存在",
                    f"无法读取备份文件: {e}",
                    duration=3000,
                    parent=self,
                    position=InfoBarPosition.TOP_RIGHT,
                )
                return
            except Exception as e:
                InfoBar.error(
                    "读取失败",
                    f"无法读取备份文件: {e}",
                    duration=3000,
                    parent=self,
                    position=InfoBarPosition.TOP_RIGHT,
                )
                return

            # 生成 unified diff（确保每行都有换行符，处理单行文件无末尾换行符的情况）
            def normalize_lines(content):
                lines = content.splitlines(keepends=True)
                if lines and not lines[-1].endswith('\n'):
                    lines[-1] += '\n'
                return lines

            old_lines = normalize_lines(old_content)
            new_lines = normalize_lines(new_content)

            diff = difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=backup_file.name,
                tofile=backup_file.name,
                lineterm='\n'
            )
            
            diff_output = ''.join(diff)
            
            # 生成并显示差异对比
            from app.llm_chatter.utils.diff_viewer import (
                DiffHtmlGenerator,
                DiffViewerWindow,
            )
            
            html = DiffHtmlGenerator.generate_html_report(diff_output, "")
            
            viewer = DiffViewerWindow(parent=self)
            viewer.load_html(html)
            viewer.show()
            
        except Exception as e:
            logger.error(f"[LLMChatter] 显示工具差异失败: {e}")
            InfoBar.error(
                "差异显示失败",
                str(e),
                duration=3000,
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
            )

    def _on_card_diff_requested(self, round_index: int):
        """
        处理卡片级差异对比请求，汇总一次对话中所有工具调用的文件修改。

        Args:
            round_index: 用户回合索引
        """
        if round_index is None:
            return

        session = self.session_manager.get_current_session()
        if not session:
            return

        session_id = session.session_id

        # 检查是否有 file_recorder
        if not self._tool_executor or not self._tool_executor.file_recorder:
            logger.warning("[LLMChatter] file_recorder 未初始化")
            return

        try:
            # 获取该 round 范围内的所有 tool_call_id
            all_call_ids = self._get_tool_call_ids_in_round(round_index)

            if not all_call_ids:
                InfoBar.warning(
                    "无差异信息",
                    "此对话没有修改任何文件",
                    duration=3000,
                    parent=self,
                    position=InfoBarPosition.TOP_RIGHT,
                )
                return

            # 收集所有工具的文件操作
            all_operations = []
            for call_id in all_call_ids:
                operations = self._tool_executor.file_recorder.get_operations_for_preview(
                    session_id=session_id,
                    call_id=call_id
                )
                if operations:
                    all_operations.extend(operations)

            if not all_operations:
                InfoBar.warning(
                    "无差异信息",
                    "此对话没有修改任何文件，或备份信息已丢失",
                    duration=3000,
                    parent=self,
                    position=InfoBarPosition.TOP_RIGHT,
                )
                return

            # 为每个文件生成差异
            from pathlib import Path
            import difflib

            def normalize_lines(content):
                lines = content.splitlines(keepends=True)
                if lines and not lines[-1].endswith('\n'):
                    lines[-1] += '\n'
                return lines

            diff_parts = []
            for op in all_operations:
                backup_path = op.get("backup_path", "")
                if not backup_path:
                    continue

                backup_file = Path(backup_path)
                after_backup_path = str(backup_file.with_suffix('.after.bak'))
                after_backup_file = Path(after_backup_path)

                if not after_backup_file.exists():
                    continue

                try:
                    with open(backup_path, 'r', encoding='utf-8', errors='replace') as f:
                        old_content = f.read()
                    with open(after_backup_path, 'r', encoding='utf-8', errors='replace') as f:
                        new_content = f.read()
                except Exception:
                    continue

                old_lines = normalize_lines(old_content)
                new_lines = normalize_lines(new_content)

                diff = difflib.unified_diff(
                    old_lines,
                    new_lines,
                    fromfile=f"a/{backup_file.name}",
                    tofile=f"b/{backup_file.name}",
                    lineterm='\n'
                )
                diff_output = ''.join(diff)
                if diff_output:
                    diff_parts.append(diff_output)

            if not diff_parts:
                InfoBar.warning(
                    "无差异信息",
                    "无法生成任何差异信息",
                    duration=3000,
                    parent=self,
                    position=InfoBarPosition.TOP_RIGHT,
                )
                return

            # 合并所有差异
            combined_diff = '\n'.join(diff_parts)

            # 生成并显示差异对比
            from app.llm_chatter.utils.diff_viewer import (
                DiffHtmlGenerator,
                DiffViewerWindow,
            )

            html = DiffHtmlGenerator.generate_html_report(combined_diff, "")
            viewer = DiffViewerWindow(parent=self)
            viewer.load_html(html)
            viewer.show()

        except Exception as e:
            logger.error(f"[LLMChatter] 显示卡片差异失败: {e}")
            InfoBar.error(
                "差异显示失败",
                str(e),
                duration=3000,
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
            )

    def _on_save_file_requested(self, code: str, lang: str):
        """
        处理保存文件请求

        Args:
            code: 代码内容
            lang: 代码语言
        """
        # 语言到文件后缀的映射
        LANG_EXT_MAP = {
            "python": ".py",
            "py": ".py",
            "javascript": ".js",
            "js": ".js",
            "typescript": ".ts",
            "ts": ".ts",
            "html": ".html",
            "htm": ".html",
            "css": ".css",
            "scss": ".scss",
            "sass": ".sass",
            "less": ".less",
            "json": ".json",
            "yaml": ".yaml",
            "yml": ".yaml",
            "xml": ".xml",
            "markdown": ".md",
            "md": ".md",
            "shell": ".sh",
            "bash": ".sh",
            "sh": ".sh",
            "sql": ".sql",
            "go": ".go",
            "java": ".java",
            "c": ".c",
            "cpp": ".cpp",
            "c++": ".cpp",
            "csharp": ".cs",
            "cs": ".cs",
            "rust": ".rs",
            "ruby": ".rb",
            "php": ".php",
            "swift": ".swift",
            "kotlin": ".kt",
            "scala": ".scala",
            "r": ".r",
            "lua": ".lua",
            "perl": ".pl",
            "powershell": ".ps1",
            "dockerfile": "Dockerfile",
            "makefile": "Makefile",
            "toml": ".toml",
            "ini": ".ini",
            "cfg": ".cfg",
            "conf": ".conf",
            "txt": ".txt",
            "csv": ".csv",
            "vue": ".vue",
            "jsx": ".jsx",
            "tsx": ".tsx",
            "graphql": ".graphql",
            "proto": ".proto",
            "docker": "Dockerfile",
        }

        # 获取文件后缀
        lang_lower = lang.lower() if lang else ""
        ext = LANG_EXT_MAP.get(lang_lower, ".txt")

        # 如果是 Dockerfile 或 Makefile 等特殊文件名，直接使用
        if lang_lower in ("dockerfile", "makefile"):
            default_name = lang_lower
        else:
            # 尝试从代码中提取类名/函数名作为建议文件名
            import re
            class_match = re.search(r'class\s+(\w+)', code)
            func_match = re.search(r'def\s+(\w+)|function\s+(\w+)', code)
            if class_match:
                default_name = class_match.group(1)
            elif func_match:
                default_name = func_match.group(1) or func_match.group(2)
            else:
                default_name = "code"
            default_name += ext

        # 弹出文件保存对话框
        from PyQt5.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存代码文件",
            default_name,
            f"代码文件 (*{ext});;所有文件 (*.*)"
        )

        if not file_path:
            return

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code)
            InfoBar.success(
                "文件已保存",
                file_path,
                duration=3000,
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
            )
        except Exception as e:
            logger.error(f"[LLMChatter] 保存文件失败: {e}")
            InfoBar.error(
                "保存失败",
                str(e),
                duration=3000,
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
            )

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
        self._pending_scroll_to_bottom = True
        self._scroll_bottom_timer.start()

    def _do_scroll_to_bottom(self):
        if not self._pending_scroll_to_bottom:
            return
        scroll_bar = self.chat_scroll_area.verticalScrollBar()
        max_val = scroll_bar.maximum()
        scroll_bar.setValue(max_val)
        # 再次设置确保卡片高度变化后仍在底部
        scroll_bar.setValue(max_val)
        self._pending_scroll_to_bottom = False
        self._sync_node_preview_to_scroll()

    def handle_recommended_question(self, content: str, action: str):
        if action == "ask":
            self.input_area.clear()
            self.send_preset_question(content)

    def send_preset_question(self, question: str):
        if not isinstance(question, str) or not question.strip():
            return

        if self._history_popup and self._history_popup.isVisible():
            self._history_popup.close()
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

        self._hide_welcome_cards()

        context_params = {}

        self.input_area.clear()
        self._append_user_message(user_text, tag_params=context_params)

        assistant_card = self._append_assistant_message()

        self._is_streaming = True
        self._toggle_send_stop(True)

        # 关键修复：确保 ToolExecutor 使用正确的 session_id
        session = self.session_manager.get_current_session()
        if session and self._tool_executor:
            self._tool_executor.set_session_context(session.session_id)

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

    def _on_reasoning_content_received(self, reasoning_piece: str):
        """处理 DeepSeek 思考内容（流式接收）"""
        if self._current_assistant_card:
            self._current_assistant_card.append_reasoning(reasoning_piece)

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

        self._tool_cancelled_by_user = True
        self._cancelled_tool_call_id = getattr(self, "_current_tool_call_id", None)
        self._tool_floating_widget.finish_tool("用户中止", success=False)

        tool_call_id = getattr(self, "_current_tool_call_id", None)
        tool_name = getattr(self, "_current_tool_name", "unknown")
        tool_args = getattr(self, "_current_tool_args", {})

        if tool_call_id and self._current_assistant_card:
            self._current_assistant_card.append_tool_result(
                tool_name=tool_name,
                arguments=tool_args,
                result="[工具执行已被用户中止]",
                success=False,
                tool_call_id=tool_call_id,
            )
            self._scroll_to_bottom()

    def _on_tool_result_received(
        self, tool_call_id: str, tool_name: str, arguments: dict, result: Any
    ):
        import time

        if (
            self._tool_cancelled_by_user
            and tool_call_id == self._cancelled_tool_call_id
        ):
            error_msg = str(getattr(result, "error", "") or "")
            if "用户中止" in error_msg:
                self._tool_floating_widget.finish_tool("用户中止", success=False)
                return
            return

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

        if self._current_assistant_card:
            self._current_assistant_card.append_tool_result(
                tool_name=tool_name,
                arguments=arguments or {},
                result=content,
                success=success,
                tool_call_id=tool_call_id,
            )

        self._scroll_to_bottom()

    def _find_latest_assistant_card(self) -> Optional[MessageCard]:
        for i in range(self.chat_layout.count() - 1, -1, -1):
            item = self.chat_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, MessageCard) and widget.role == "assistant":
                    return widget
        return None

    def _notify_if_inactive(self, title: str, message: str):
        setting = Settings.get_instance()
        if not setting.llm_notify_enabled.value:
            return

        if not self._should_show_inactive_notification():
            return

        sound_type = setting.llm_notify_sound.value
        if sound_type != "none":
            QApplication.beep()

        if self.homepage and self.homepage.window():
            win = self.homepage.window()
            if hasattr(win, "tray_icon") and win.tray_icon:
                win.tray_icon.showMessage(
                    title, message, win.tray_icon.MessageIcon(1), 4000
                )

    def _should_show_inactive_notification(self) -> bool:
        """Only notify when the app window is not effectively visible to the user."""
        window = None
        if self.homepage and self.homepage.window():
            window = self.homepage.window()
        else:
            window = self.window()

        if window is None:
            return True

        if not window.isVisible() or window.isMinimized():
            return True

        native_result = self._is_window_in_foreground_native(window)
        if native_result is not None:
            return not native_result

        app = QApplication.instance()
        active_window = app.activeWindow() if app is not None else None

        # When the current app is not foreground, the chat reply should notify.
        if active_window is None:
            return True

        if active_window is window:
            return False

        return not window.isActiveWindow()

    def _is_window_in_foreground_native(self, window) -> Optional[bool]:
        """Use the OS foreground window when available to avoid Qt focus misreads."""
        if os.name != "nt":
            return None

        try:
            user32 = ctypes.windll.user32
            foreground_hwnd = user32.GetForegroundWindow()
            if not foreground_hwnd:
                return None

            foreground_pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(
                foreground_hwnd, ctypes.byref(foreground_pid)
            )
            return foreground_pid.value == os.getpid()
        except Exception:
            return None

    def _on_notification_clicked(self):
        window = self.window()
        if window:
            window.show()
            if window.isMinimized():
                window.showNormal()
            window.activateWindow()

    def _on_stream_finished(self, response: str):
        self._is_streaming = False
        self._tool_cancelled_by_user = False
        self._cancelled_tool_call_id = None
        self._toggle_send_stop(False)

        if self._current_assistant_card:
            self._current_assistant_card.finish_streaming()
        if self.history_manager:
            self._save_current_session_to_history()

        if self.input_area:
            self.input_area.setFocus()

        session = self.session_manager.get_current_session()
        if session and session.messages:
            last_msg = session.messages[-1] if session.messages else None
            if last_msg and last_msg.get("role") == "assistant":
                content = last_msg.get("content", "")
                if isinstance(content, list):
                    from app.llm_chatter.utils.message_content import (
                        content_to_text,
                    )

                    content = content_to_text(content)
                preview = content[:50] + "..." if len(content) > 50 else content
                current_title = self.title_edit.text() if self.title_edit else "对话完成"
                self._notify_if_inactive(current_title, preview)

    def _save_current_session_to_history(self):
        session = self.session_manager.get_current_session()
        saved_messages = list(session.messages or []) if session else []
        if not saved_messages:
            return

        system_prompt = getattr(session, "system_prompt", "") or ""
        # 优先使用已有的 topic_summary，避免被用户消息前30字覆盖
        session_title = getattr(session, "topic_summary", "") or ""

        if self._current_session_id is not None:
            idx = self.history_manager.find_index_by_session_id(
                self._current_session_id
            )
            if idx is not None:
                self.history_manager.update_session(
                    idx,
                    saved_messages,
                    compaction_state=getattr(session, "compaction_state", {}),
                    compaction_cache=getattr(session, "compaction_cache", {}),
                    system_prompt=system_prompt,
                )
            else:
                self.history_manager.save_session(
                    saved_messages,
                    title=session_title,  # 使用已有的 topic_summary
                    session_id=session.session_id if session else None,
                    compaction_state=getattr(session, "compaction_state", {}),
                    compaction_cache=getattr(session, "compaction_cache", {}),
                    system_prompt=system_prompt,
                )
                self._current_session_id = session.session_id if session else None
        else:
            self.history_manager.save_session(
                saved_messages,
                title=session_title,  # 使用已有的 topic_summary
                session_id=session.session_id if session else None,
                compaction_state=getattr(session, "compaction_state", {}),
                compaction_cache=getattr(session, "compaction_cache", {}),
                system_prompt=system_prompt,
            )
            self._current_session_id = session.session_id if session else None

        self._update_node_preview()

    def _on_messages_updated(self, messages: List[Dict[str, Any]]):
        session = self.session_manager.get_current_session()
        if not session:
            return

        self._history_preview_messages = None
        session.set_messages(messages or [], preserve_compaction=True)
        self._refresh_context_usage_indicator()

    def _on_engine_error(self, error: str):
        self._tool_cancelled_by_user = False

        if self._current_assistant_card:
            self._current_assistant_card.stop_streaming_anim()
            self._current_assistant_card.set_error_state(True)
            self._current_assistant_card.update_content(error)

        self._is_streaming = False

        if self._tool_floating_widget:
            self._tool_floating_widget.clear()
            self._tool_floating_widget.setVisible(False)

        self._toggle_send_stop(False)

        current_title = self.title_edit.text() if self.title_edit else "对话"
        self._notify_if_inactive(f"{current_title} - 错误", error[:100])

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
        self._notify_if_inactive("需要回答问题", question[:100])

    def _on_question_answered(self, answer: str):
        if self._pending_permission_tool_call_id:
            tool_call_id = self._pending_permission_tool_call_id
            self._pending_permission_tool_call_id = None
            if answer == "允许":
                self._chat_engine.approve_tool_permission(tool_call_id, False)
            elif answer == "允许且该轮对话自动允许":
                self._chat_engine.approve_tool_permission(tool_call_id, True)
            else:
                self._chat_engine.deny_tool_permission(tool_call_id)
            if self.input_area:
                self.input_area.setFocus()
            return

        if not self._question_tool_call_id:
            return

        tool_call_id = self._question_tool_call_id
        self._question_tool_call_id = None

        if self._chat_engine:
            self._chat_engine.provide_question_answer(answer)

        if self.input_area:
            self.input_area.setFocus()

    def _on_question_cancelled(self):
        """用户关闭问题窗口时，返回空答案让大模型继续"""
        if self._pending_permission_tool_call_id:
            tool_call_id = self._pending_permission_tool_call_id
            self._pending_permission_tool_call_id = None
            self._chat_engine.deny_tool_permission(tool_call_id)
            if self.input_area:
                self.input_area.setFocus()
            return

        if not self._question_tool_call_id:
            return

        self._question_tool_call_id = None

        if self._chat_engine:
            self._chat_engine.provide_question_answer("")

        if self.input_area:
            self.input_area.setFocus()

    def _on_agent_switched(self, agent_name: str):
        """智能体切换回调 - 丝滑切换，不清空对话"""
        pass

    def _on_permission_approval_requested(
        self, tool_call_id: str, tool_name: str, arguments: dict
    ):
        self._pending_permission_tool_call_id = tool_call_id
        self._pending_permission_auto_allow = False
        try:
            arg_str = str(arguments)[:200] if arguments else ""
            question_text = f"工具 `{tool_name}` 需要权限执行。\n\n参数: {arg_str}"
            options = ["允许", "允许且该轮对话自动允许", "不允许"]
            self._question_floating_widget.show_question(question_text, options, False)
        except Exception as e:
            logger.error(f"[Permission] Approval error: {e}")
            self._chat_engine.deny_tool_permission(tool_call_id)
            self._pending_permission_tool_call_id = None

    def _maybe_generate_topic_summary(self):
        selected_name = self._current_provider_name if self._current_provider_name else "系统默认配置"
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
        if self._current_session_id is not None:
            idx = self.history_manager.find_index_by_session_id(
                self._current_session_id
            )
            if idx is not None:
                previous_summary = self.history_manager.get_topic_summary(idx)

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
            memory_category = result.get("memory_category", "task_preference")
            hit_memories = result.get("hit_memories", [])
        else:
            summary = result
            should_update_memory = False
            memory_content = ""
            memory_category = "task_preference"
            hit_memories = []

        if not summary:
            return

        clean_summary = summary.strip()
        session = self.session_manager.get_current_session()

        # 先设置 session 的 topic_summary，避免 save_session 时 title 为空
        if session:
            session.set_topic_summary(clean_summary)

        if self._current_session_id is None and session and session.messages:
            self.history_manager.save_session(
                session.messages if session else [],
                title=clean_summary,  # 使用生成的摘要作为标题
                session_id=session.session_id if session else None,
                compaction_state=getattr(session, "compaction_state", {}),
                compaction_cache=getattr(session, "compaction_cache", {}),
            )
            self._current_session_id = session.session_id if session else None

        if self._current_session_id is not None:
            idx = self.history_manager.find_index_by_session_id(
                self._current_session_id
            )
            if idx is not None:
                self.history_manager.update_topic_summary(idx, clean_summary)

        self._update_title_display(clean_summary)

        if should_update_memory and memory_content and self._memory_manager:
            self._memory_manager.add_user_memory(
                memory_content,
                source="topic_summary",
                confidence=0.8,
                category=memory_category,
            )
            logger.info(
                f"[Topic Summary] Added to long-term memory [{memory_category}]: {memory_content[:50]}..."
            )
        else:
            logger.info(
                f"[Topic Summary] Memory update skipped (should_update={should_update_memory}, content={bool(memory_content)})"
            )

        if hit_memories and self._memory_manager:
            self._memory_manager.touch_memories(hit_memories)
            logger.info(
                f"[Topic Summary] Touched {len(hit_memories)} existing memories"
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
        if self._current_session_id is not None:
            idx = self.history_manager.find_index_by_session_id(
                self._current_session_id
            )
            if idx is not None:
                self.history_manager.update_session_title(idx, new_title)

    def _auto_save_current_session(self):
        session = self.session_manager.get_current_session()
        if not session or not session.messages:
            return

        system_prompt = getattr(session, "system_prompt", "") or ""

        if self._current_session_id is not None:
            idx = self.history_manager.find_index_by_session_id(
                self._current_session_id
            )
            if idx is not None:
                self.history_manager.update_session(
                    idx,
                    session.messages,
                    compaction_state=getattr(session, "compaction_state", {}),
                    compaction_cache=getattr(session, "compaction_cache", {}),
                    system_prompt=system_prompt,
                )
            else:
                self.history_manager.save_session(
                    session.messages,
                    session_id=session.session_id,
                    compaction_state=getattr(session, "compaction_state", {}),
                    compaction_cache=getattr(session, "compaction_cache", {}),
                    system_prompt=system_prompt,
                )
                self._current_session_id = session.session_id
        else:
            self.history_manager.save_session(
                session.messages,
                session_id=session.session_id,
                compaction_state=getattr(session, "compaction_state", {}),
                compaction_cache=getattr(session, "compaction_cache", {}),
                system_prompt=system_prompt,
            )
            self._current_session_id = session.session_id

        if self._current_session_id:
            idx = self.history_manager.find_index_by_session_id(
                self._current_session_id
            )
            if idx is not None:
                return self.history_manager.get_current_title(idx)
        return None

    def closeEvent(self, event):
        try:
            self._auto_save_current_session()
        except Exception:
            pass
        super().closeEvent(event)

    def _toggle_send_stop(self, is_sending: bool):
        if is_sending:
            self.history_btn.setDisabled(True)
            self.input_area.toggle_send_button(False)
        else:
            self.history_btn.setDisabled(False)
            self.input_area.toggle_send_button(True)

    def _on_stop_clicked(self):
        self._tool_cancelled_by_user = False
        interrupted_messages: List[Dict[str, Any]] = []

        if self._chat_engine:
            interrupted_messages = self._chat_engine.stop() or []

        self._is_streaming = False

        if self._tool_floating_widget:
            self._tool_floating_widget.clear()
            self._tool_floating_widget.setVisible(False)

        self._toggle_send_stop(False)
        if self._current_assistant_card:
            self._current_assistant_card.stop_streaming_anim()
            self._current_assistant_card.finish_streaming()

        if interrupted_messages:
            self._on_messages_updated(interrupted_messages)
            if self.history_manager:
                self._save_current_session_to_history()
        InfoBar.warning(
            title="已中止",
            content="问答请求已被手动中止。",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self,
        )
        if self.input_area:
            self.input_area.setFocus()

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
