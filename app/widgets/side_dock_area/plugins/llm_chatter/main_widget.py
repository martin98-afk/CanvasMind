# -*- coding: utf-8 -*-
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThreadPool
from PyQt5.QtGui import QFont, QIcon, QStandardItem, QStandardItemModel
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

from app.server_manager.mcp_server.stdio_server import GlobalMcpServer
from app.utils.config import Settings
from app.utils.utils import get_icon
from app.widgets.side_dock_area.plugins.llm_chatter.utils.chat_session import (
    SessionManager,
)
from app.widgets.side_dock_area.plugins.llm_chatter.utils.history_manager import (
    HistoryManager,
)
from app.widgets.side_dock_area.plugins.llm_chatter.utils.worker import (
    OpenAIChatWorker,
    TitleGenerationTask,
    TopicSummaryTask,
    ShellExecutionTask,
)
from app.widgets.side_dock_area.plugins.llm_chatter.utils.builtin_tools import (
    BuiltinTools,
    get_builtin_tools_schema,
    ToolResult,
)
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.bottom_input_area import (
    SendableTextEdit,
)
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.context_selector import (
    ContextSelector,
)
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.llm_config_popup import (
    LLMConfigPopup,
)
from app.widgets.side_dock_area.plugins.llm_chatter.constants import (
    FREE_PROVIDERS,
    PROVIDER_ICONS,
)
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.message_card import (
    MessageCard,
    create_welcome_card,
)
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.conversation_node_preview import (
    ConversationNodePreview,
)
from app.widgets.side_dock_area.plugins.llm_chatter.widgets.memory_manager import (
    MemoryManagerDialog,
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
    _builtin_tools: Optional[BuiltinTools] = None
    _is_continuing: bool = False
    _processed_tool_ids: set = set()  # 防止重复处理工具调用
    insertResponse = pyqtSignal(str)
    createResponse = pyqtSignal(str)
    contextActionRequested = pyqtSignal(str, str)
    skillExecutionRequested = pyqtSignal(str, dict)
    userInterventionRequested = pyqtSignal(dict)
    _gen_thread_pool = QThreadPool()
    # Signals for execution results coming from the execution engine
    executionResultProduced = pyqtSignal(str)
    _system_prompt = """# 角色
你是大模型对话执行型智能体，具备分析、记忆、推理、以及执行能力。你的目标是在专业级别的对话中，既提供高质量的回答，又能通过调用技能、执行命令等方式落地执行用户的需求。

职责与行为准则
- 以清晰、专业的语言输出，必要时附带可执行的步骤（命令、代码、API 调用等）。
- 遇到不清晰的需求时，主动提出澄清问题或给出可操作的分步方案。
- 始终优先使用长期记忆和历史对话上下文来提升回答相关性。
- 如需扩展能力，优先通过内部技能/工具执行，而非直接输出未验证的信息。

## 可用内置工具
你可以使用以下内置工具来完成任务：

1. **read(filePath, offset, limit)** - 读取文件内容
2. **write(filePath, content)** - 创建或覆盖文件
3. **edit(filePath, oldString, newString, replaceAll)** - 精确字符串替换编辑文件
4. **grep(pattern, path, include)** - 使用正则表达式搜索文件内容
5. **glob(pattern, path)** - 通过 glob 模式查找文件
6. **list(path)** - 列出目录内容
7. **patch(filePath, patch_content)** - 对文件应用补丁
8. **bash(command, timeout)** - 执行 shell 命令
9. **webfetch(url, format)** - 获取网页内容
10. **websearch(query, num_results)** - 网络搜索
11. **todowrite(todos)** - 创建和更新待办事项列表
12. **todoread()** - 读取待办事项列表
13. **skill(name)** - 加载技能文档
14. **question(question, options)** - 向用户提问

**工具调用格式**：
```builtin_tool_call
{"name": "工具名", "args": {"参数1": "值1", ...}}
```

## 追问与行动规范
- 当你预测到用户接下来可能需要的帮助时，请按以下格式给出追问清单（放在回复末尾）：
- [问题描述](ask)
- 如需执行，请在拟议行动后附上你将执行的第一步（如调用技能、运行命令等）以便用户确认。"""

    def __init__(self, homepage, button):
        super().__init__(homepage, button)
        self._gen_thread_pool.setMaxThreadCount(2)
        self.homepage = homepage
        self._worker: Optional[OpenAIChatWorker] = None
        self._is_streaming = False
        self.session_manager.create_new_session()
        if hasattr(self.homepage, "global_variables_changed"):
            self.homepage.global_variables_changed.connect(self._load_model_configs)
        self._initialize_history_manager()
        self._initialize_builtin_tools()

    def _initialize_builtin_tools(self):
        import os

        # 使用项目根目录作为默认工作目录
        workdir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        try:
            if hasattr(self.homepage, "workflow_name") and self.homepage.workflow_name:
                canvas_name = self.homepage.workflow_name
                workspace_path = (
                    Path(workdir)
                    / "canvas_files"
                    / "workflows"
                    / canvas_name
                    / "workspace"
                )
                if workspace_path.exists():
                    workdir = str(workspace_path)
        except Exception:
            pass
        logger.info(f"[BuiltinTools] Initialized with workdir: {workdir}")
        self._builtin_tools = BuiltinTools(self.homepage, workdir)

    def showEvent(self, event):
        if not self._first_show:
            self._first_show = True
            QTimer.singleShot(0, lambda: self._create_new_session())
        super().showEvent(event)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)

        session_bar_layout = QHBoxLayout()
        session_bar_layout.setContentsMargins(0, 0, 0, 0)
        session_bar_layout.setSpacing(4)

        left_layout = QHBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self.title_edit = QLabel("新对话", self)
        self.title_edit.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                font-size: 14px;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                background-color: transparent;
            }
            QLabel:hover {
                background-color: #3d3d3d;
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

        self.chat_scroll_area = SingleDirectionScrollArea(self)
        self.chat_scroll_area.setMinimumWidth(400)
        self.chat_scroll_area.setStyleSheet(
            "background-color: transparent; border: none;"
        )
        self.chat_scroll_area.setWidgetResizable(True)
        self.chat_scroll_area.setViewportMargins(0, 0, 10, 0)

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(3, 3, 3, 3)
        self.chat_layout.setSpacing(5)
        self.chat_layout.setAlignment(Qt.AlignBottom)
        self.chat_scroll_area.setWidget(self.chat_container)

        layout.addWidget(self.chat_scroll_area, 1)

        self.node_preview = ConversationNodePreview(self)
        self.node_preview.nodeClicked.connect(self._on_node_preview_clicked)
        layout.addWidget(self.node_preview)

        hlayout = QHBoxLayout()
        hlayout.setContentsMargins(0, 0, 0, 0)
        hlayout.setSpacing(0)
        self.context_selector = ContextSelector(self)
        hlayout.addWidget(self.context_selector)
        hlayout.addStretch(1)

        self.typing_label = CaptionLabel("", self)
        self.typing_label.setStyleSheet("color: #888; font-size: 12px;")
        self.typing_label.setVisible(False)
        hlayout.addWidget(self.typing_label)

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
        self.input_area.setMaximumHeight(80)
        setFont(self.input_area, 15)
        self.input_area.sendMessageRequested.connect(self._on_send_clicked)
        self.input_area.stopMessageRequested.connect(self._on_stop_clicked)
        self.input_area.clearRequested.connect(self._on_clear_shortcut)
        self.input_area.newSessionRequested.connect(self._create_new_session)
        layout.addWidget(self.input_area)

    def set_system_prompt(self, prompt):
        self._system_prompt += prompt

    def _on_model_changed(self, model_name: str):
        if model_name:
            setting = Settings.get_instance()
            setting.set(setting.llm_selected_model, model_name, save=True)

    def _open_settings_popup(self):
        # 懒加载 popup
        if self._settings_popup is None:
            self._settings_popup = LLMConfigPopup(parent=self)
            self._settings_popup.configApplied.connect(self._on_config_applied)

        # 准备初始配置
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
        # 在设置按钮下方弹出
        self._settings_popup.show_at(self.settings_btn)

    def _on_config_applied(self, new_config: dict):
        current_name = self.model_combo.currentText()

        # 检查是否是系统预置的免费供应商
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
            # 系统预置的免费供应商配置，保存到本地
            self._valid_configs[current_name] = new_config
            setting = Settings.get_instance()
            saved_providers = setting.llm_saved_providers.value or {}
            saved_providers[current_name] = new_config
            setting.set(setting.llm_saved_providers, saved_providers, save=True)
            InfoBar.success("已保存", "配置已保存到本地。", parent=self, duration=1500)
        else:
            # 用户自定义配置，保存到 global_variables
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
                    # 新增自定义配置
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

        # 收集所有模型名称（系统 + 自定义）
        all_model_names = ["系统默认配置"]

        # 加载用户自定义配置
        try:
            custom_vars = getattr(self.homepage, "global_variables", None)
            if custom_vars and hasattr(custom_vars, "custom"):
                for config_name, var_obj in custom_vars.custom.items():
                    if hasattr(var_obj, "value") and isinstance(var_obj.value, dict):
                        val = var_obj.value
                        if {"API_URL", "API_KEY", "模型名称"}.issubset(val.keys()):
                            # 避免自定义配置名与"系统默认配置"冲突
                            if config_name != "系统默认配置":
                                self._valid_configs[config_name] = val
                                all_model_names.append(config_name)
        except Exception as e:
            # 建议至少打印错误
            logger.error(f"[ERROR] 加载自定义模型配置失败: {e}")

        # 添加免费模型供应商配置
        setting = Settings.get_instance()
        saved_providers = setting.llm_saved_providers.value or {}

        for provider_name, provider_config in FREE_PROVIDERS.items():
            if provider_name not in self._valid_configs:
                # 检查是否有已保存的配置
                if provider_name in saved_providers:
                    config = saved_providers[provider_name].copy()
                else:
                    config = provider_config.copy()
                    config.pop("备注", None)
                    config.pop("认证方式", None)
                    config.pop("获取地址", None)
                self._valid_configs[provider_name] = config
                all_model_names.append(provider_name)

        # ✅ 关键：一次性添加所有模型名
        self._setup_combo_with_icons(all_model_names)
        self.model_combo.setDisabled(len(all_model_names) == 0)

        # 恢复之前选中的项
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
        """为模型选择器添加图标，供应商显示图标，普通配置不显示"""
        self.model_combo.clear()
        for name in model_names:
            if name in PROVIDER_ICONS:
                icon_name = PROVIDER_ICONS.get(name, "API")
                icon = get_icon(icon_name)
                self.model_combo.addItem(icon=icon, text=name)
            else:
                self.model_combo.addItem(name)

    def _create_new_session(self):
        session = self.session_manager.create_new_session()
        self._current_history_index = None
        self.history_btn.setChecked(False)
        self._clear_chat_area()
        self.title_edit.setText("新对话")
        self.node_preview.clear_nodes()
        welcome_card = create_welcome_card(self)
        welcome_card._is_welcome = True
        welcome_card.contextActionRequested.connect(self.handle_recommended_question)
        QTimer.singleShot(300, lambda: self.chat_layout.addWidget(welcome_card))

    def _display_current_session(self):
        """清空布局并重新加载当前会话的所有消息"""
        self._clear_chat_area()

        session = self.session_manager.get_current_session()
        if not session:
            return

        if self._current_history_index is not None:
            title = self.history_manager.get_current_title(self._current_history_index)
            if title:
                self.title_edit.setText(title)

        for msg in session.messages:
            if msg["role"] == "user":
                self._append_user_message(
                    msg["content"],
                    timestamp=msg.get("timestamp", datetime.now().strftime("%H:%M")),
                    tag_params=msg.get("params", {}),
                )
            elif msg["role"] == "assistant":
                card = self._append_assistant_message()
                card.update_content(msg["content"])
            else:
                continue

        QTimer.singleShot(10, self._scroll_to_bottom)
        self._update_node_preview()

    # 历史对话管理
    def _initialize_history_manager(self):
        canvas_name = getattr(self.homepage, "workflow_name", "default")
        if not canvas_name:
            canvas_name = "default"
        self.history_manager = HistoryManager(canvas_name)

    def _toggle_history_mode(self, enabled: bool):
        if enabled:
            self._in_history_mode = True
            self.chat_layout.setAlignment(Qt.AlignTop)  # 关键：防止垂直拉伸
            self._display_history_sessions()
        else:
            self._in_history_mode = False
            self.chat_layout.setAlignment(Qt.AlignBottom)  # 关键：防止垂直拉伸
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
        """执行Shell命令并显示结果（异步执行，不阻塞UI）"""
        self._append_user_message(cmd, timestamp=datetime.now().strftime("%H:%M"))
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

        # 倒序显示（最新在上）
        reversed_history = list(enumerate(history_list[::-1]))  # (display_idx, session)
        for display_idx, session in reversed_history:
            title = session["title"]
            last_time = session["last_time"]

            # 计算原始索引：因为 reversed，原始索引 = total - 1 - display_idx
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

        # 默认样式
        base_style = "background-color: #2d2d2d; border-radius: 6px; padding: 8px; background-color: transparent;"
        if is_current:
            # 橙色高亮（可按你偏好调整）
            card.setStyleSheet(
                "background-color: #ff6f00; border-radius: 6px; padding: 8px; color: white;"
            )
        else:
            card.setStyleSheet(base_style)

        card.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 4)

        title_label = CaptionLabel(title[:200], card)
        title_label.setWordWrap(True)
        time_label = CaptionLabel(last_time, card)
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
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_clear_shortcut(self):
        self._clear_chat_area()
        self.node_preview.clear_nodes()
        session = self.session_manager.get_current_session()
        if session:
            session.clear()
        welcome_card = create_welcome_card(self)
        welcome_card._is_welcome = True
        welcome_card.contextActionRequested.connect(self.handle_recommended_question)
        QTimer.singleShot(300, lambda: self.chat_layout.addWidget(welcome_card))
        self.title_edit.setText("新对话")

    def _delete_history_session(self, index: int):
        self.history_manager.delete_history(index)
        self._display_history_sessions()

    def _load_history_session(self, index: int):
        messages = self.history_manager.get_session_by_index(index)
        if messages is None:
            return
        self.session_manager.set_session_from_messages(messages)
        self._current_history_index = index  # 关键：标记当前正在编辑哪个历史
        self._in_history_mode = False
        self.chat_layout.setAlignment(Qt.AlignBottom)  # 关键：防止垂直拉伸
        self.history_btn.setChecked(False)
        self._display_current_session()

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
        card.viewer._install_dialog_filter()
        card.update_content(content)
        card.finish_streaming()
        card.deleteRequested.connect(lambda: self._delete_message(card))
        card.actionRequested.connect(self._on_code_action)
        self.chat_layout.addWidget(card)
        self._scroll_to_bottom()
        self._update_node_preview()
        return card

    def _append_assistant_message(self) -> MessageCard:
        card = MessageCard(parent=self, role="assistant")
        card.viewer._install_dialog_filter()
        card.actionRequested.connect(self._on_code_action)
        card.regenerateRequested.connect(lambda: self._regenerate_message(card))
        card.contextActionRequested.connect(self.handle_recommended_question)
        if hasattr(self.homepage, "on_context_action"):
            card.contextActionRequested.connect(self.homepage.on_context_action)
        else:
            card.contextActionRequested.connect(self.contextActionRequested.emit)
        self.chat_layout.addWidget(card)
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

        # 如果最后是用户消息没有对应回复，也显示出来
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

    def _delete_message(self, card: MessageCard):
        """删除用户消息时，连带删除下一条助手消息（如果存在）"""
        # 找到 card 在 layout 中的索引
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

        # 如果是用户消息，尝试删除下一条（助手）
        to_remove_indices = [card_index]
        if card.role == "user" and card_index + 1 < self.chat_layout.count():
            next_widget = self.chat_layout.itemAt(card_index + 1).widget()
            if isinstance(next_widget, MessageCard) and next_widget.role == "assistant":
                to_remove_indices.append(card_index + 1)

        # 从后往前删，避免索引错乱
        for idx in sorted(to_remove_indices, reverse=True):
            item = self.chat_layout.itemAt(idx)
            if item and item.widget():
                w = item.widget()
                self.chat_layout.removeWidget(w)
                w.deleteLater()
            # 同步删除 session 中的消息
            if idx < len(session.messages):
                session.messages.pop(idx)

        self._update_node_preview()

    def _remove_message_at_index(self, index: int):
        if 0 <= index < self.chat_layout.count():
            item = self.chat_layout.itemAt(index)
            if item and item.widget():
                widget = item.widget()
                self.chat_layout.removeWidget(widget)
                widget.deleteLater()

            session = self.session_manager.get_current_session()
            if session and 0 <= index < len(session.messages):
                session.messages.pop(index)

    def _regenerate_message(self, card: MessageCard):
        session = self.session_manager.get_current_session()
        if not session:
            return

        # 找到该卡片的索引
        card_index = -1
        for i in range(self.chat_layout.count()):
            if self.chat_layout.itemAt(i).widget() is card:
                card_index = i
                break

        # 验证索引有效性
        if card_index <= 0 or card_index >= len(session.messages):
            return

        # 重构当时的用户输入
        user_input = session.messages[card_index - 1]["content"]
        params = session.messages[card_index - 1].get("params")
        if params:
            user_input = (
                "\n".join([value[1] for value in params.values()])
                + "\n\n"
                + user_input
                + "\n\n回复内容:\n"
            )
        # 删除当前助手消息
        self._delete_message(card)
        # 重新发送
        self._on_send_clicked(user_input)

    def _on_code_action(self, code: str, action: str = "copy"):
        """统一处理代码块操作：插入、新建、复制等"""
        if action == "insert":
            self.insertResponse.emit(code)  # 如果需要向上转发
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
        QTimer.singleShot(
            10,
            lambda: self.chat_scroll_area.verticalScrollBar().setValue(
                self.chat_scroll_area.verticalScrollBar().maximum()
            ),
        )

    def handle_recommended_question(self, content: str, action: str):
        if action == "ask":
            session = self.session_manager.get_current_session()
            session.add_user_message(
                content=content,
                params={
                    key: value for key, value in self.context_selector.context.items()
                },
            )
            self.input_area.clear()
            self._append_user_message(content)
            self.send_preset_question(content)

    def send_preset_question(self, question: str):
        """
        从外部传入一个预制问题并自动开始生成回复。

        Args:
            question (str): 预设的用户提问内容
        """
        if not isinstance(question, str) or not question.strip():
            return

        # 如果处于历史模式，退出历史模式并回到当前会话
        if self._in_history_mode:
            self.history_btn.setChecked(False)
            self._toggle_history_mode(False)
        # 触发标准发送流程（复用已有逻辑）
        self._on_send_clicked(user_text=question.strip())

    def _on_send_clicked(self, user_text: str = ""):
        if self._is_streaming:
            self._on_stop_clicked()

        # 清空已处理的工具调用集合
        self._processed_tool_ids.clear()

        # Shell模式：直接执行命令
        if self._is_shell_mode:
            if not user_text:
                user_text = self.input_area.toPlainText().strip()
            if not user_text:
                return
            self.input_area.clear()
            self._execute_shell_command(user_text)
            return

        self.input_area.toggle_send_button(False)

        # 1. 获取当前会话和配置
        session = self.session_manager.get_current_session()
        selected_name = self.model_combo.currentText()
        llm_config = self._valid_configs.get(selected_name)

        if not llm_config:
            InfoBar.error("配置无效", "请检查模型设置", parent=self)
            return

        # 2. 处理用户输入
        if not user_text:
            user_text = self.input_area.toPlainText().strip()
            if not user_text:
                return
            session.add_user_message(
                content=user_text,
                params={k: v for k, v in self.context_selector.context.items()},
            )
            self.input_area.clear()
            self._append_user_message(user_text)

        # 3. 构造消息列表 (System Prompt)
        messages = []
        full_system_prompt = (
            self._system_prompt + "\n" + llm_config.get("系统提示", "").strip()
        ).strip()

        # 注入长期记忆到系统提示
        long_term_memory = self._get_long_term_memory_context()
        if long_term_memory:
            full_system_prompt += f"\n\n{long_term_memory}"

        messages.append({"role": "system", "content": full_system_prompt})

        # 4. 注入历史消息
        for msg in session.messages[:-1]:
            content = msg["content"]
            if isinstance(content, list):  # 简化多模态历史
                content = "\n".join(
                    [item["text"] for item in content if item["type"] == "text"]
                )
            messages.append({"role": msg["role"], "content": content})

        # 5. 处理当前消息的多模态逻辑
        model_name = str(llm_config.get("模型名称", "")).lower()
        supports_vision = any(
            x in model_name for x in ["4o", "vision", "vl", "gemini", "claude-3"]
        )
        has_image = any([item[-1] for item in self.context_selector._context_cache])

        if supports_vision and has_image:
            user_content = self.context_selector.get_multimodal_context_items()
            user_content.append({"type": "text", "text": user_text})
            messages.append({"role": "user", "content": user_content})
        else:
            context_text = self.context_selector.get_text_context()
            messages.append({"role": "user", "content": context_text + user_text})

        # 6. 准备助手卡片
        assistant_card = self._append_assistant_message()

        # 7. 启动 Worker (透传整个 llm_config 字典)
        self._is_streaming = True
        available_tools = self._get_available_builtin_tools()
        logger.info(f"[LLM] Starting chat with {len(available_tools)} tools available")

        self._worker = OpenAIChatWorker(
            messages=messages,
            llm_config=llm_config,  # 直接传递字典，Worker 内部会动态解析
            tools=available_tools,
        )

        # 信号连接
        self._worker.content_received.connect(
            lambda c: self._on_content_received(c, assistant_card)
        )
        self._worker.tool_call_received.connect(
            lambda tc: self._on_tool_call_received(tc, assistant_card)
        )
        self._worker.error_occurred.connect(lambda e: self._on_error(e, assistant_card))
        self._worker.finished_with_content.connect(
            lambda r: self._on_worker_finished(r, assistant_card)
        )
        self._worker.start()
        # 保存 llm_config 以便后续执行阶段使用
        self._last_llm_config = llm_config

        self._toggle_send_stop(True)

    def _on_error(self, error: str, card: MessageCard):
        card.update_content(error)
        self._is_streaming = False
        self._toggle_send_stop(False)
        self.input_area.toggle_send_button(True)

    def _on_worker_finished(self, response: str, card: MessageCard):
        self._is_streaming = False
        card.finish_streaming()

        # 如果是继续对话，不要立即启用输入，等待下一轮工具调用
        if self._is_continuing:
            logger.info("[WorkerFinished] Continuing mode - not enabling input yet")
            self._is_continuing = False
            return

        self.input_area.toggle_send_button(True)
        self._toggle_send_stop(False)
        session = self.session_manager.get_current_session()
        if session:
            session.add_assistant_message(content=response)
            current_title = self._auto_save_current_session()
            self._generate_conversation_title(current_title, session.messages)
        self._maybe_generate_topic_summary()
        # Start the execution plan (ClaudeDecode-style) in background
        # try:
        #     long_term_memory = self._get_long_term_memory_context()
        #     self._execution_agent.plan_and_execute(
        #         messages=session.messages,
        #         llm_config=self._last_llm_config or {},
        #         long_term_memory=long_term_memory,
        #         callback=self._execution_result_callback,
        #     )
        # except Exception as e:
        #     logger.error(f"[Execution] planning/execution failed: {e}")

    def _maybe_generate_topic_summary(self):
        if self._current_history_index is None:
            return
        if not self.history_manager.should_generate_summary(
            self._current_history_index
        ):
            return
        selected_name = self.model_combo.currentText()
        llm_config = self._valid_configs.get(selected_name)
        if not llm_config:
            return
        session = self.session_manager.get_current_session()
        if not session:
            return

        previous_summary = ""
        if self._current_history_index is not None:
            previous_summary = self.history_manager.get_topic_summary(
                self._current_history_index
            )

        long_term_memory = self._get_long_term_memory_context()

        task = TopicSummaryTask(
            messages=session.messages,
            llm_config=llm_config,
            callback=self._on_topic_summary_generated,
            previous_summary=previous_summary if previous_summary else None,
            long_term_memory=long_term_memory,
        )
        self._gen_thread_pool.start(task)

    def _on_topic_summary_generated(self, result, error_msg: str = None):
        if not result or error_msg:
            logger.error(f"[Topic Summary] Failed to generate: {error_msg}")
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
        if len(clean_summary) > 60:
            clean_summary = clean_summary[:60] + "..."

        if self._current_history_index is not None:
            self.history_manager.update_topic_summary(
                self._current_history_index, clean_summary
            )
            self._update_title_display(clean_summary)

            if should_update_memory and memory_content:
                self._add_user_memory(memory_content)

    def _update_title_display(self, title: str):
        """更新标题显示"""
        self.title_edit.setText(title)

    def _update_long_term_memory(self, topic_summary: str, reason: str = ""):
        """更新长期记忆文件 soul.md"""
        try:
            memory_file = self._get_soul_memory_file()
            if not memory_file:
                return

            memory_data = self._load_soul_memory()

            existing_topics = memory_data.get("topics", [])
            topic_entry = {
                "topic": topic_summary,
                "reason": reason,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            topic_exists = any(t.get("topic") == topic_summary for t in existing_topics)
            if not topic_exists:
                existing_topics.append(topic_entry)
                memory_data["topics"] = existing_topics[-20:]

            memory_data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memory_data["total_conversations"] = (
                memory_data.get("total_conversations", 0) + 1
            )

            with open(memory_file, "w", encoding="utf-8") as f:
                json.dump(memory_data, f, ensure_ascii=False, indent=2)

            logger.info(f"[Soul Memory] Updated with: {topic_summary}")
        except Exception as e:
            logger.error(f"[Soul Memory] Failed to update: {e}")

    def _add_user_memory(self, memory_content: str):
        """添加用户偏好记忆"""
        if not memory_content:
            return
        try:
            memory_file = self._get_soul_memory_file()
            if not memory_file:
                return

            memory_data = self._load_soul_memory()
            user_memories = memory_data.get("user_memories", [])

            memory_exists = False
            for mem in user_memories:
                if isinstance(mem, dict):
                    if mem.get("content", "") == memory_content:
                        memory_exists = True
                        break
                elif mem == memory_content:
                    memory_exists = True
                    break

            if not memory_exists:
                user_memories.append(
                    {
                        "content": memory_content,
                        "enabled": True,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
                memory_data["user_memories"] = user_memories[-20:]
                memory_data["last_updated"] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                with open(memory_file, "w", encoding="utf-8") as f:
                    json.dump(memory_data, f, ensure_ascii=False, indent=2)

                logger.info(f"[Soul Memory] Added user memory: {memory_content}")
        except Exception as e:
            logger.error(f"[Soul Memory] Failed to add user memory: {e}")

    def _get_soul_memory_file(self) -> Optional[Path]:
        try:
            canvas_name = (
                getattr(self.homepage, "workflow_name", "default") or "default"
            )
            memory_dir = Path("canvas_files") / "workflows" / canvas_name
            memory_dir.mkdir(parents=True, exist_ok=True)
            return memory_dir / "soul.md"
        except Exception:
            return None

    def _load_soul_memory(self) -> dict:
        memory_file = self._get_soul_memory_file()
        if memory_file and memory_file.exists():
            try:
                with open(memory_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "user_memories" not in data:
                        data["user_memories"] = []
                    return data
            except Exception:
                pass
        return {
            "version": "1.0",
            "user_profile": {
                "name": "",
                "preferences": {},
                "communication_style": "",
                "expertise_level": "",
            },
            "topics": [],
            "conversation_patterns": [],
            "key_insights": [],
            "user_memories": [],
            "total_conversations": 0,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_updated": "",
        }

    def _get_long_term_memory_context(self) -> str:
        """获取长期记忆上下文，始终返回可用的内存段，若无记忆也返回占位文本引导记忆积累。"""
        memory_data = self._load_soul_memory()
        topics = memory_data.get("topics", [])
        user_memories = memory_data.get("user_memories", [])

        lines = []
        lines.append("## 长期记忆摘要")

        if topics:
            recent_topics = topics[-3:]
            lines.append(
                "最近讨论主题: "
                + ", ".join(
                    [
                        t.get("topic", "") if isinstance(t, dict) else str(t)
                        for t in recent_topics
                    ]
                )
            )
        if user_memories:
            mem_lines = []
            for m in user_memories[-5:]:
                if isinstance(m, dict):
                    mem_lines.append(m.get("content", ""))
                else:
                    mem_lines.append(str(m))
            mem_lines = [s for s in mem_lines if s]
            if mem_lines:
                lines.append("用户记忆片段: " + " | ".join(mem_lines))

        if not topics and not user_memories:
            lines.append("暂无长期记忆，系统将逐步积累用户偏好与会话要点。")

        lines.append("请根据以上信息在未来对话中保持一致性与个性化。")
        return "\n".join(lines)

    def _clear_long_term_memory(self):
        from PyQt5.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空所有长期记忆吗？此操作不可恢复。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                memory_file = self._get_soul_memory_file()
                if memory_file and memory_file.exists():
                    memory_file.unlink()
                InfoBar.success("已清空", "长期记忆已清除", parent=self, duration=1500)
            except Exception as e:
                logger.error(f"[Soul Memory] Failed to clear: {e}")

    def _show_soul_memory(self):
        """显示长期记忆管理界面"""
        memory_data = self._load_soul_memory()
        user_memories = memory_data.get("user_memories", [])

        dialog = MemoryManagerDialog(user_memories, self)
        dialog.memoryUpdated.connect(self._on_memory_updated)
        dialog.exec_()

    def _on_memory_updated(self, memories: list):
        """保存更新后的记忆"""
        try:
            memory_file = self._get_soul_memory_file()
            if not memory_file:
                return

            memory_data = self._load_soul_memory()
            memory_data["user_memories"] = memories
            memory_data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with open(memory_file, "w", encoding="utf-8") as f:
                json.dump(memory_data, f, ensure_ascii=False, indent=2)

            InfoBar.success("已保存", "长期记忆已更新", parent=self, duration=1500)
            logger.info(f"[Soul Memory] Updated user memories: {len(memories)} items")
        except Exception as e:
            logger.error(f"[Soul Memory] Failed to save: {e}")
            InfoBar.error("保存失败", str(e), parent=self, duration=1500)

    def _on_title_double_click(self, event):
        """双击标题编辑"""
        from PyQt5.QtWidgets import QInputDialog, QLineEdit

        current_title = self.title_edit.text()
        new_title, ok = QInputDialog.getText(
            self, "编辑标题", "请输入新标题:", QLineEdit.Normal, current_title
        )
        if ok and new_title.strip():
            self._update_title(new_title.strip())

    def _update_title(self, new_title: str):
        """更新会话标题"""
        self.title_edit.setText(new_title)
        if self._current_history_index is not None:
            self.history_manager.update_session_title(
                self._current_history_index, new_title
            )

    def load_skill_document(self, skill_path: str = None) -> str:
        """加载 skill.md 文档"""
        if self._loaded_skill_doc:
            return self._loaded_skill_doc

        search_paths = []
        if skill_path:
            search_paths.append(Path(skill_path))

        try:
            canvas_name = (
                getattr(self.homepage, "workflow_name", "default") or "default"
            )
            workspace_path = (
                Path("canvas_files") / "workflows" / canvas_name / "workspace"
            )
            search_paths.extend(
                [
                    workspace_path / "skill.md",
                    workspace_path / "skills.md",
                    Path.cwd() / "skill.md",
                    Path("canvas_files") / "workflows" / canvas_name / "skill.md",
                ]
            )
        except Exception:
            pass

        for path in search_paths:
            if path and path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                        if len(content) > 100:
                            self._loaded_skill_doc = content
                            logger.info(f"[Skill] Loaded skill document from {path}")
                            return content
                except Exception as e:
                    logger.warning(f"[Skill] Failed to load {path}: {e}")

        return ""

    def _get_skill_context(self) -> str:
        """获取技能文档上下文"""
        if not self._skill_enabled:
            return ""

        skill_doc = self.load_skill_document()
        if not skill_doc:
            return ""

        long_term_memory = self._get_long_term_memory_context()

        context = skill_doc
        if long_term_memory:
            context += f"\n\n{long_term_memory}"

        return context

    def execute_skill(self, method: str, params: dict, callback=None):
        """执行技能方法"""
        self.skillExecutionRequested.emit(method, params)

        if hasattr(self.homepage, "execute_skill"):
            try:
                result = self.homepage.execute_skill(method, params)
                if callback:
                    callback(result)
                return result
            except Exception as e:
                logger.error(f"[Skill] Execution failed: {e}")
                if callback:
                    callback({"error": str(e)})
                return {"error": str(e)}

        if callback:
            callback({"error": "Skill execution not available"})
        return {"error": "Skill execution not available"}

    def request_user_intervention(self, options: List[dict], callback):
        """请求用户干预选择"""
        from PyQt5.QtWidgets import (
            QDialog,
            QVBoxLayout,
            QRadioButton,
            QPushButton,
            QButtonGroup,
        )

        dialog = QDialog(self)
        dialog.setWindowTitle("请选择")
        dialog.setMinimumWidth(300)
        layout = QVBoxLayout(dialog)

        label = QLabel("请选择以下选项之一：")
        layout.addWidget(label)

        group = QButtonGroup(dialog)
        for i, option in enumerate(options):
            radio = QRadioButton(option.get("label", f"选项 {i + 1}"))
            radio.setData(option)
            group.addButton(radio)
            layout.addWidget(radio)

        if group.buttons():
            group.buttons()[0].setChecked(True)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("确定")
        cancel_btn = QPushButton("取消")
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        def on_ok():
            selected = group.checkedButton()
            if selected:
                result = selected.data()
                dialog.accept()
                if callback:
                    callback(result)

        ok_btn.clicked.connect(on_ok)
        cancel_btn.clicked.connect(lambda: dialog.reject())

        dialog.exec_()

    def enable_skills(self, enabled: bool):
        """启用/禁用技能"""
        self._skill_enabled = enabled

    def set_skill_document(self, content: str):
        """设置技能文档内容"""
        self._loaded_skill_doc = content

    def _auto_save_current_session(self):
        """根据当前状态决定保存方式"""
        session = self.session_manager.get_current_session()
        if not session or not session.messages:
            return

        if self._current_history_index is not None:
            # 正在续聊某个历史会话 → 更新它
            self.history_manager.update_session(
                self._current_history_index, session.messages
            )
        else:
            # 全新会话 → 新增一条历史记录（首次保存）
            self.history_manager.save_session(session.messages)
            # 保存后，自动绑定到新历史索引（避免重复保存）
            self._current_history_index = 0  # 因为 save_session 是 insert(0, ...)

        return self.history_manager.get_current_title(self._current_history_index)

    def _toggle_send_stop(self, is_sending: bool):
        if is_sending:
            self.model_combo.setDisabled(True)
            self.history_btn.setDisabled(True)
        else:
            self.model_combo.setDisabled(False)
            self.history_btn.setDisabled(False)

    def _on_stop_clicked(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker = None  # 可选：等待线程真正结束（避免 race condition）
        self._worker = None
        self._is_streaming = False
        self._toggle_send_stop(False)
        self.input_area.toggle_send_button(True)
        InfoBar.warning(
            title="已中止",
            content="问答请求已被手动中止。",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self,
        )

    def _on_content_received(self, content_piece: str, assistant_card: MessageCard):
        logger.info(
            f"[ContentReceived] Received content piece, length: {len(content_piece)}"
        )
        self._update_assistant_message(assistant_card, content_piece)
        # 1) 处理插件调用（技能执行）若检测到 plugin_call 指令
        self._process_plugin_calls(content_piece, assistant_card)
        # 2) 处理简单的工具调用（如 shell 命令）
        self._process_tool_calls(content_piece, assistant_card)
        # 3) 处理内置工具调用 - 已通过 function calling 处理，不再重复解析
        # (function calling 是主要工具调用方式，builtin_tool_call 文本格式已废弃)

    def _on_tool_call_received(self, tool_call: dict, assistant_card: MessageCard):
        """处理原生 function calling 格式的工具调用"""
        logger.info(f"[ToolCallReceived] Received tool call: {tool_call}")

        func = tool_call.get("function", {})
        tool_name = func.get("name")
        arguments = func.get("arguments", "{}")

        if not tool_name:
            logger.warning("[ToolCallReceived] Tool name is empty, skipping")
            return

        tool_call_id = tool_call.get("id")
        if not tool_call_id:
            logger.warning("[ToolCallReceived] Tool call id is empty, skipping")
            return

        # 标记为已处理，防止重复
        if tool_call_id in self._processed_tool_ids:
            logger.warning(
                f"[ToolCallReceived] Tool call {tool_call_id} already processed, skipping"
            )
            return
        self._processed_tool_ids.add(tool_call_id)

        # arguments 可能是字符串，需要解析
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except:
                arguments = {}

        logger.info(
            f"[ToolCallReceived] Executing tool: {tool_name} with args: {arguments}"
        )

        result = self._execute_builtin_tool(tool_name, arguments)

        # 将工具调用和结果添加到消息历史
        session = self.session_manager.get_current_session()
        if session:
            # 添加助手的消息（包含工具调用）
            session.messages.append(
                {
                    "role": "assistant",
                    "content": self._worker.full_response if self._worker else "",
                    "tool_calls": [
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(arguments)
                                if isinstance(arguments, dict)
                                else str(arguments),
                            },
                        }
                    ],
                }
            )
            # 添加工具结果
            tool_result_content = str(result)
            session.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": tool_result_content,
                }
            )

        # 显示工具结果
        self._display_tool_result(result, tool_name, arguments)

        # 继续调用 LLM 处理工具结果（多轮迭代）
        self._is_continuing = True
        self._continue_with_tool_result(assistant_card)

    def _continue_with_tool_result(self, assistant_card: MessageCard):
        """在工具调用后继续对话"""
        logger.info("[Continue] Continuing conversation after tool call...")

        session = self.session_manager.get_current_session()
        if not session:
            logger.warning("[Continue] No session found")
            return

        # 获取当前模型配置
        selected_name = self.model_combo.currentText()
        llm_config = self._valid_configs.get(selected_name)
        if not llm_config:
            logger.error("[Continue] No LLM config found")
            return

        # 构建消息列表（包含工具调用历史）
        messages = self._build_continuation_messages(session.messages)

        # 创建新的 worker 继续对话
        self._worker = OpenAIChatWorker(
            messages=messages,
            llm_config=llm_config,
            tools=self._get_available_builtin_tools(),
        )

        # 连接信号
        self._worker.content_received.connect(
            lambda c: self._on_content_received(c, assistant_card)
        )
        self._worker.tool_call_received.connect(
            lambda tc: self._on_tool_call_received(tc, assistant_card)
        )
        self._worker.error_occurred.connect(lambda e: self._on_error(e, assistant_card))
        self._worker.finished_with_content.connect(
            lambda r: self._on_worker_finished(r, assistant_card)
        )

        logger.info("[Continue] Starting continued chat...")
        self._worker.start()

    def _build_continuation_messages(self, session_messages: List[Dict]) -> List[Dict]:
        """构建继续对话的消息列表（包含工具调用历史）"""
        messages = []

        # 添加系统提示
        full_system_prompt = (self._system_prompt + "\n").strip()

        long_term_memory = self._get_long_term_memory_context()
        if long_term_memory:
            full_system_prompt += f"\n\n{long_term_memory}"

        messages.append({"role": "system", "content": full_system_prompt})

        # 添加所有历史消息
        for msg in session_messages:
            role = msg.get("role")
            if role == "system":
                continue

            # 处理工具调用消息
            if "tool_calls" in msg:
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.get("content", ""),
                        "tool_calls": msg.get("tool_calls", []),
                    }
                )
            elif role == "tool":
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.get("tool_call_id"),
                        "content": msg.get("content", ""),
                    }
                )
            else:
                content = msg.get("content")
                if isinstance(content, list):
                    content = "\n".join(
                        [
                            item.get("text", "")
                            for item in content
                            if item.get("type") == "text"
                        ]
                    )
                messages.append({"role": role, "content": content})

        logger.info(f"[Continue] Built {len(messages)} messages for continuation")
        return messages

    def _on_execution_result(self, content: str):
        if content is None:
            return
        card = self._append_assistant_message()
        card.update_content(str(content))
        card.finish_streaming()
        self._scroll_to_bottom()

    def _execution_result_callback(self, content: str):
        if content is None:
            return
        self.executionResultProduced.emit(str(content))

    def _execution_result_callback(self, content: str):
        """Callback forwarded from the execution engine to display results."""
        if content is None:
            return
        self.executionResultProduced.emit(str(content))

    def _process_plugin_calls(self, content_piece: str, assistant_card: MessageCard):
        """Detect and execute plugin_call blocks in assistant content."""
        try:
            pattern = re.compile(r"```plugin_call\s*\n(.*?)\n```", re.S)
            match = pattern.search(content_piece)
            if not match:
                return
            payload_str = match.group(1).strip()
            payload = json.loads(payload_str)
            method = payload.get("method")
            params = payload.get("params", {}) or {}
            if method:
                self.execute_skill(
                    method,
                    params,
                    callback=lambda res: self._on_skill_result(res, assistant_card),
                )
        except Exception as e:
            logger.error(f"[PluginCall] Failed to process: {e}")

    def _on_skill_result(self, result, assistant_card: MessageCard):
        content = ""
        if isinstance(result, dict) and "error" in result:
            content = f"[Skill Error] {result.get('error')}"
        else:
            content = f"[Skill Result] {result}"
        new_card = self._append_assistant_message()
        new_card.update_content(str(content))
        new_card.finish_streaming()
        self._scroll_to_bottom()

    def _process_tool_calls(self, content_piece: str, assistant_card: MessageCard):
        """Detect and execute simple tool calls (e.g., shell commands) emitted by the model."""
        try:
            pattern = re.compile(r"```tool_call\s*\n(.*?)\n```", re.S)
            match = pattern.search(content_piece)
            if not match:
                return
            payload_str = match.group(1).strip()
            payload = json.loads(payload_str)
            tool_type = payload.get("type")
            if tool_type == "shell":
                cmd = payload.get("cmd", "")
                if not cmd:
                    return
                import subprocess

                try:
                    res = subprocess.run(
                        cmd, shell=True, capture_output=True, text=True, timeout=60
                    )
                    output = res.stdout.strip()
                    error_out = res.stderr.strip()
                    combined = "\n".join([output, error_out]).strip()
                    tool_card = self._append_assistant_message()
                    tool_card.update_content(
                        "Shell command result:\n" + (combined or "")
                    )
                    tool_card.finish_streaming()
                    self._scroll_to_bottom()
                except Exception as e:
                    err_card = self._append_assistant_message()
                    err_card.update_content(f"[Shell execution error] {e}")
                    err_card.finish_streaming()
                    self._scroll_to_bottom()
        except Exception as e:
            logger.error(f"[ToolCall] Failed to process: {e}")

    def _process_builtin_tool_calls(
        self, content_piece: str, assistant_card: MessageCard
    ):
        """Detect and execute builtin tool calls from model output."""
        logger.info(
            f"[BuiltinToolCall] Checking for tool calls, content length: {len(content_piece)}"
        )

        if not self._builtin_tools:
            logger.warning("[BuiltinToolCall] Builtin tools not initialized")
            return

        try:
            pattern = re.compile(r"```builtin_tool_call\s*\n(.*?)\n```", re.S)
            match = pattern.search(content_piece)
            logger.info(f"[BuiltinToolCall] Pattern match result: {match is not None}")

            if not match:
                # 也尝试其他可能的格式
                alt_pattern = re.compile(
                    r'```json\s*\n(\{.*?"tool".*?\})\s*\n```', re.S
                )
                alt_match = alt_pattern.search(content_piece)
                if alt_match:
                    logger.info(f"[BuiltinToolCall] Found alternative format tool call")
                    match = alt_match
                else:
                    logger.info(f"[BuiltinToolCall] No tool call found in content")
                    return

            payload_str = match.group(1).strip()
            logger.info(f"[BuiltinToolCall] Raw payload: {payload_str[:200]}")

            payload = json.loads(payload_str)
            tool_name = payload.get("name") or payload.get("tool")
            tool_args = payload.get("args", {}) or payload.get("arguments", {})

            logger.info(f"[BuiltinToolCall] Tool: {tool_name}, Args: {tool_args}")

            if not tool_name:
                logger.warning("[BuiltinToolCall] No tool name found")
                return

            result = self._execute_builtin_tool(tool_name, tool_args)
            logger.info(f"[BuiltinToolCall] Result: {result}")
            self._display_tool_result(result, tool_name)

        except json.JSONDecodeError as e:
            logger.error(f"[BuiltinToolCall] JSON parse error: {e}")
        except Exception as e:
            logger.error(f"[BuiltinToolCall] Failed to process: {e}")

    def _execute_builtin_tool(self, tool_name: str, args: dict) -> ToolResult:
        """Execute a builtin tool and return the result."""
        logger.info(f"[ExecuteBuiltinTool] tool_name={tool_name}, args={args}")

        if not self._builtin_tools:
            logger.warning("[ExecuteBuiltinTool] Builtin tools not initialized")
            return ToolResult(False, error="Builtin tools not initialized")

        # 记录详细的参数提取过程
        logger.info(
            f"[ExecuteBuiltinTool] args keys: {list(args.keys()) if args else []}"
        )

        tool_map = {
            "read": lambda: self._builtin_tools.read_file(
                args.get("filePath"), args.get("offset", 1), args.get("limit", 2000)
            ),
            "write": lambda: self._builtin_tools.write_file(
                args.get("filePath"), args.get("content", "")
            ),
            "edit": lambda: self._builtin_tools.edit_file(
                args.get("filePath"),
                args.get("oldString", ""),
                args.get("newString", ""),
                args.get("replaceAll", False),
            ),
            "grep": lambda: self._builtin_tools.grep_files(
                args.get("pattern"), args.get("path"), args.get("include")
            ),
            "glob": lambda: self._builtin_tools.glob_files(
                args.get("pattern"), args.get("path")
            ),
            "list": lambda: self._builtin_tools.list_directory(args.get("path")),
            "patch": lambda: self._builtin_tools.apply_patch(
                args.get("filePath"), args.get("patch_content", "")
            ),
            "bash": lambda: self._builtin_tools.execute_bash(
                args.get("command", ""), args.get("timeout", 120)
            ),
            "webfetch": lambda: self._builtin_tools.fetch_web(
                args.get("url", ""), args.get("format", "markdown")
            ),
            "websearch": lambda: self._builtin_tools.search_web(
                args.get("query", ""), args.get("num_results", 10)
            ),
            "todowrite": lambda: self._builtin_tools.todo_write(args.get("todos", [])),
            "todoread": lambda: self._builtin_tools.todo_read(),
            "skill": lambda: self._builtin_tools.load_skill(args.get("name", "")),
            "question": lambda: self._builtin_tools.ask_question(
                args.get("question", ""), args.get("options")
            ),
        }

        executor = tool_map.get(tool_name)
        if executor:
            try:
                return executor()
            except Exception as e:
                return ToolResult(False, error=f"Execution error: {str(e)}")

        return ToolResult(False, error=f"Unknown tool: {tool_name}")

    def _display_tool_result(
        self, result: ToolResult, tool_name: str, tool_args: dict = None
    ):
        """Display tool execution result in chat."""
        from app.widgets.side_dock_area.plugins.llm_chatter.widgets.message_card import (
            _render_tool_block,
        )

        content = str(result)
        tool_html = _render_tool_block(
            tool_name, tool_args or {}, content, result.success
        )

        # 获取当前卡片（应该是最新的助手消息卡片）
        tool_call_card = None
        for i in range(self.chat_layout.count() - 1, -1, -1):
            item = self.chat_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, MessageCard):
                    tool_call_card = widget
                    break

        if tool_call_card:
            # 追加到当前卡片内容中
            new_content = tool_html
            tool_call_card.update_content(new_content)
            tool_call_card.finish_streaming()
        else:
            # 如果没有找到当前卡片，创建新的
            tool_card = self._append_assistant_message()
            tool_card.update_content(tool_html)
            tool_card.finish_streaming()

        self._scroll_to_bottom()

    # 对话标题总结
    def _generate_conversation_title(self, current_title: str, messages: List[Dict]):
        """异步请求大模型生成对话标题"""
        if len(messages) < 2:
            return

        selected_name = self.model_combo.currentText()
        llm_config = self._valid_configs.get(selected_name)
        if not llm_config:
            return

        # 创建任务
        task = TitleGenerationTask(
            current_title=current_title,
            messages_for_summary=messages,
            llm_config=llm_config,
            callback=self._on_title_generated,  # 用于回调
        )
        self._gen_thread_pool.start(task)

    def _on_title_generated(self, raw_output: str = None, error_msg: str = None):
        """从模型输出中提取 ```title ... ``` 中的标题"""
        if error_msg:
            logger.error(f"[Title Gen] Error: {error_msg}")
            return
        if not raw_output:
            return

        match = re.search(r"```title\s*(.+?)\s*```", raw_output, re.DOTALL)
        if match:
            title = match.group(1).strip()
            title = title.strip("\"''' \n\t")
            if 1 <= len(title) <= 15:
                if self._current_history_index is not None:
                    self.history_manager.update_session_title(
                        self._current_history_index, title
                    )
                self.title_edit.setText(title)
                return

        logger.error(f"[Title Gen] 未能从以下输出中提取标题:\n{raw_output}")

    def _get_available_mcp_tools(self) -> List[Dict]:
        """获取工具定义，如果没有 MCP 服务器则返回空列表"""
        try:
            exports_dir = Path(r"D:\work\CanvasMind\canvas_files\projects")
            server = GlobalMcpServer(exports_dir)
            tools = server.handle_initialize(None)
            return tools if isinstance(tools, list) else []
        except Exception as e:
            logger.warning(f"获取 MCP 工具失败: {e}")
            return []

    def _get_available_builtin_tools(self) -> List[Dict]:
        """获取内置工具定义"""
        return get_builtin_tools_schema()

    def _toggle_search_mode(self):
        self._is_searching = not self._is_searching
        self.search_input.setVisible(self._is_searching)
        if not self._is_searching:
            self.search_input.clear()
            self._search_results.clear()
            self._current_search_index = -1

    def _on_search_text_changed(self, text: str):
        if not text:
            self._search_results.clear()
            self._current_search_index = -1
            return
        self._search_results.clear()
        pattern = text.lower()
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, MessageCard):
                    content = widget.viewer.get_plain_text().lower()
                    if pattern in content:
                        self._search_results.append(i)
        if self._search_results:
            self._current_search_index = 0
            self._highlight_search_result()

    def _highlight_search_result(self):
        if not self._search_results or self._current_search_index < 0:
            return
        idx = self._search_results[self._current_search_index]
        item = self.chat_layout.itemAt(idx)
        if item and item.widget():
            widget = item.widget()
            self.chat_scroll_area.verticalScrollBar().setValue(widget.y())

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
