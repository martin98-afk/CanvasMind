# -*- coding: utf-8 -*-
from datetime import datetime
from typing import Optional, Dict, Any

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QApplication, QWidget
from qfluentwidgets import (
    setFont, ComboBox, FluentIcon, SingleDirectionScrollArea, InfoBar, InfoBarPosition, CardWidget, CaptionLabel,
    TransparentToolButton,
    TransparentToggleToolButton
)

from app.utils.config import Settings
from app.utils.utils import get_icon
from app.widgets.side_dock_area.plugins.llm_chatter.chat_session import SessionManager
from app.widgets.side_dock_area.plugins.llm_chatter.context_selector import ContextSelector
from app.widgets.side_dock_area.plugins.llm_chatter.history_manager import HistoryManager
from app.widgets.side_dock_area.plugins.llm_chatter.llm_config_popup import LLMConfigPopup
from app.widgets.side_dock_area.plugins.llm_chatter.message_card import MessageCard, create_welcome_card
from app.widgets.side_dock_area.plugins.llm_chatter.bottom_input_area import SendableTextEdit
from app.widgets.side_dock_area.plugins.llm_chatter.worker import OpenAIChatWorker
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
    _settings_popup = None  # 懒加载
    _system_prompt = ""
    _is_welcome = False
    insertResponse = pyqtSignal(str)
    createResponse = pyqtSignal(str)
    contextActionRequested = pyqtSignal(str, str)

    def __init__(self, homepage):
        super().__init__(homepage)
        self.homepage = homepage
        self._worker: Optional[OpenAIChatWorker] = None
        self._is_streaming = False
        self.session_manager.create_new_session()
        if hasattr(self.homepage, "global_variables_changed"):
            self.homepage.global_variables_changed.connect(self._load_model_configs)
        self._initialize_history_manager()
        self._create_new_session()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)

        # ========== 顶部会话管理栏 ==========
        session_bar_layout = QHBoxLayout()
        session_bar_layout.setContentsMargins(0, 0, 0, 0)
        session_bar_layout.setSpacing(4)

        # 左侧：模型 + 分隔符 + 标题
        left_layout = QHBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        model_label = QLabel("模型：", self)
        setFont(model_label, 12, QFont.Bold)
        model_label.setStyleSheet("color: #ffffff;")
        left_layout.addWidget(model_label)

        self.model_combo = ComboBox(self)
        self._load_model_configs()
        setFont(self.model_combo, 12)
        left_layout.addWidget(self.model_combo)
        left_layout.addStretch()
        # 右侧保持不变
        right_layout = QHBoxLayout()
        # --- 新增：+ 新建对话 和 历史对话按钮 ---
        self.new_session_btn = TransparentToolButton(FluentIcon.ADD, self)
        self.new_session_btn.setToolTip("新建对话")
        self.new_session_btn.clicked.connect(self._create_new_session)
        self.history_btn = TransparentToggleToolButton(FluentIcon.HISTORY, self)
        self.history_btn.setToolTip("历史对话")
        self.history_btn.toggled.connect(self._toggle_history_mode)
        self.settings_btn = TransparentToolButton(FluentIcon.SETTING, self)
        self.settings_btn.setToolTip("模型设置")
        self.settings_btn.clicked.connect(self._open_settings_popup)
        right_layout.addWidget(self.new_session_btn)
        right_layout.addWidget(self.history_btn)
        right_layout.addWidget(self.settings_btn)

        session_bar_layout.addLayout(left_layout)
        session_bar_layout.addStretch()
        session_bar_layout.addLayout(right_layout)
        layout.addLayout(session_bar_layout)

        # ========== 聊天内容区域（使用 SingleDirectionScrollArea）==========
        self.chat_scroll_area = SingleDirectionScrollArea(self)
        self.chat_scroll_area.setMinimumWidth(400)
        # 透明背景
        self.chat_scroll_area.setStyleSheet("background-color: transparent; border: none;")
        self.chat_scroll_area.setWidgetResizable(True)
        self.chat_scroll_area.setViewportMargins(0, 0, 10, 0)

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(3, 3, 3, 3)
        self.chat_layout.setSpacing(5)
        self.chat_layout.setAlignment(Qt.AlignBottom)  # 关键：防止垂直拉伸
        self.chat_scroll_area.setWidget(self.chat_container)

        layout.addWidget(self.chat_scroll_area, 1)

        # ========== 中间状态栏（使用 ContextSelector）==========
        self.context_selector = ContextSelector(self)
        layout.addWidget(self.context_selector)

        # ========== 输入区域 ==========
        self.input_area = SendableTextEdit(self)  # ← 使用自定义 TextEdit
        self.input_area.setMaximumHeight(80)
        setFont(self.input_area, 15)
        self.input_area.sendMessageRequested.connect(self._on_send_clicked)
        self.input_area.stopMessageRequested.connect(self._on_stop_clicked)
        layout.addWidget(self.input_area)

    def set_system_prompt(self, prompt):
        self._system_prompt = prompt

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
        if current_name != "系统默认配置":
            # 更新现有配置
            self.homepage.global_variables.custom[current_name].value = new_config
            self.homepage._on_global_variables_changed("custom", current_name, "update")
            self._load_model_configs()
            idx = self.model_combo.findText(current_name)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
            InfoBar.success("已更新", "配置已保存并应用。", parent=self, duration=1500)
        else:
            setting = Settings.get_instance()
            # 更新 cfg 默认配置并持久化
            setting.set(setting.llm_model, new_config["模型名称"])
            setting.set(setting.llm_api_key, new_config["API_KEY"])
            setting.set(setting.llm_api_base, new_config["API_URL"])
            setting.set(setting.llm_max_tokens, new_config["最大Token"])
            setting.set(setting.llm_temperature, new_config["温度"])
            setting.set(setting.llm_enable_thinking, new_config["是否思考"])
            setting.save_config()
            self._load_model_configs()
            InfoBar.success("系统默认配置已更新", "已保存到系统配置。", parent=self, duration=1500)

    def _load_model_configs(self):
        current_text = self.model_combo.currentText() if self.model_combo.count() > 0 else ""

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
            custom_vars = getattr(self.homepage, 'global_variables', None)
            if custom_vars and hasattr(custom_vars, 'custom'):
                for config_name, var_obj in custom_vars.custom.items():
                    if hasattr(var_obj, 'value') and isinstance(var_obj.value, dict):
                        val = var_obj.value
                        if {"API_URL", "API_KEY", "模型名称"}.issubset(val.keys()):
                            # 避免自定义配置名与“系统默认配置”冲突
                            if config_name != "系统默认配置":
                                self._valid_configs[config_name] = val
                                all_model_names.append(config_name)
        except Exception as e:
            # 建议至少打印错误
            print(f"[ERROR] 加载自定义模型配置失败: {e}")

        # ✅ 关键：一次性添加所有模型名
        self.model_combo.addItems(all_model_names)
        self.model_combo.setDisabled(len(all_model_names) == 0)

        # 恢复之前选中的项
        if current_text in self._valid_configs:
            idx = self.model_combo.findText(current_text)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
        elif self.model_combo.count() > 0:
            self.model_combo.setCurrentIndex(0)

    def _create_new_session(self):
        session = self.session_manager.create_new_session()
        self._current_history_index = None
        self.history_btn.setChecked(False)
        self._clear_chat_area()
        # 创建欢迎卡片并标记
        welcome_card = create_welcome_card(self)
        welcome_card._is_welcome = True  # ← 关键标记
        welcome_card.contextActionRequested.connect(self.handle_recommended_question)
        QTimer.singleShot(300, lambda: self.chat_layout.addWidget(welcome_card))

    def _display_current_session(self):
        """清空布局并重新加载当前会话的所有消息"""
        self._clear_chat_area()

        session = self.session_manager.get_current_session()
        if not session:
            return
        for msg in session.messages:
            if msg["role"] == "user":
                self._append_user_message(msg["content"])
            elif msg["role"] == "assistant":
                card = self._append_assistant_message()
                card.update_content(msg["content"])
            else:
                continue

        QTimer.singleShot(10, self._scroll_to_bottom)

    # 历史对话管理
    def _initialize_history_manager(self):
        canvas_name = getattr(self.homepage, 'workflow_name', 'default')
        if not canvas_name:
            canvas_name = 'default'
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
            title = session['title']
            last_time = session['last_time']

            # 计算原始索引：因为 reversed，原始索引 = total - 1 - display_idx
            original_index = len(history_list) - 1 - display_idx

            is_current = (self._current_history_index is not None and
                          self._current_history_index == original_index)

            card = self._create_history_card(title, last_time, original_index, is_current=is_current)
            self.chat_layout.addWidget(card)

        self._scroll_to_bottom()

    def _create_history_card(self, title: str, last_time: str, index: int, is_current: bool = False) -> QWidget:
        card = CardWidget(self)

        # 默认样式
        base_style = "background-color: #2d2d2d; border-radius: 6px; padding: 8px;"
        if is_current:
            # 橙色高亮（可按你偏好调整）
            card.setStyleSheet("background-color: #ff6f00; border-radius: 6px; padding: 8px; color: white;")
        else:
            card.setStyleSheet(base_style)

        card.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 4)

        title_label = CaptionLabel(title[:200], card)
        title_label.setWordWrap(True)
        time_label = CaptionLabel(last_time, card)
        if is_current:
            title_label.setStyleSheet("color: white; font-weight: bold;")
            time_label.setStyleSheet("color: rgba(255,255,255,0.8);")
        else:
            time_label.setStyleSheet("color: #aaa;")

        delete_btn = TransparentToolButton(FluentIcon.DELETE, card)
        delete_btn.setFixedSize(24, 24)
        delete_btn.clicked.connect(lambda _, i=index: self._delete_history_session(i))

        layout.addWidget(title_label, 1, Qt.AlignLeft)
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

    def _append_user_message(self, content: str):
        card = MessageCard(
            parent=self, role="user",
            tag_params={key: value for key, value in self.context_selector.context.items()}
        )
        card.update_content(content)
        card.finish_streaming()
        card.deleteRequested.connect(lambda: self._delete_message(card))
        card.actionRequested.connect(self._on_code_action)
        self.chat_layout.addWidget(card)
        self._scroll_to_bottom()
        return card

    def _append_assistant_message(self) -> MessageCard:
        card = MessageCard(parent=self, role="assistant")
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
        if card_index <= 0:
            return

        # 重构当时的用户输入
        user_input = session.messages[card_index - 1]["content"]
        params = session.messages[card_index - 1]["params"]
        if params:
            user_input = "\n".join([value[1] for value in params.values()]) + "\n\n" + user_input + "\n\n回复内容:\n"
        # 删除当前助手消息
        self._delete_message(card)
        # 重新发送
        self._on_send_clicked(user_input)

    def _on_code_action(self, code: str, action: str="copy"):
        """统一处理代码块操作：插入、新建、复制等"""
        if action == "insert":
            self.insertResponse.emit(code)  # 如果需要向上转发
        elif action == "create":
            self.createResponse.emit(code)
        elif action == "copy":
            clipboard = QApplication.clipboard()
            clipboard.setText(code)

    def _scroll_to_bottom(self):
        QTimer.singleShot(10, lambda: self.chat_scroll_area.verticalScrollBar().setValue(
            self.chat_scroll_area.verticalScrollBar().maximum()
        ))

    def handle_recommended_question(self, content: str, action: str):
        if action == "ask":
            session = self.session_manager.get_current_session()
            session.add_user_message(
                content=content,
                params={key: value for key, value in self.context_selector.context.items()}
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
        # === 防止重复发送：自动中止当前请求 ===
        if self._is_streaming:
            self._on_stop_clicked()  # 安全中止当前 worker
        self.input_area.toggle_send_button(False)
        # === 安全移除欢迎卡片（动态查找）===
        welcome_card = None
        for i in range(self.chat_layout.count()):
            widget = self.chat_layout.itemAt(i).widget()
            if isinstance(widget, MessageCard) and getattr(widget, '_is_welcome', False):
                welcome_card = widget
                break
        if welcome_card is not None:
            self.chat_layout.removeWidget(welcome_card)
            welcome_card.deleteLater()

        # === 原有发送逻辑继续 ===
        session = self.session_manager.get_current_session()
        if not user_text:
            user_text = self.input_area.toPlainText().strip()
            if not user_text:
                return
            session.add_user_message(
                content=user_text,
                params={key: value for key, value in self.context_selector.context.items()}
            )
            self.input_area.clear()
            self._append_user_message(user_text)

        selected_name = self.model_combo.currentText()
        llm_config = self._valid_configs.get(selected_name)
        assistant_card = self._append_assistant_message()
        if not llm_config:
            self._update_assistant_message(assistant_card, "[错误] 模型配置无效")
            return

        # 构建系统消息
        messages = []
        system_prompt = (self._system_prompt + llm_config.get("系统提示", "").strip()).strip()
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # 添加历史消息（注意：历史消息必须是纯文本，不能含 image_url）
        for msg in session.messages[:-1]:
            # 历史消息只保留文本，丢弃图片（或你也可设计历史支持图片，但需更复杂处理）
            if isinstance(msg["content"], list):
                # 如果历史中已有多模态，只取 text 部分（简化处理）
                text_parts = [item["text"] for item in msg["content"] if item["type"] == "text"]
                content = "\n".join(text_parts)
            else:
                content = msg["content"]
            messages.append({"role": msg["role"], "content": content})

        # 当前用户消息：多模态
        model_name = llm_config.get("模型名称", "")
        supports_vision = any(
            m in model_name.lower() for m in ["4o", "4-turbo", "gpt-4-v", "vision", "vl", "glm-4v", "qwen-vl"])

        if supports_vision:
            context_items = self.context_selector.get_multimodal_context_items()
            user_content_list = []
            for item in context_items:
                user_content_list.append(item)
            user_content_list.append({"type": "text", "text": user_text})
            # 使用多模态格式
            messages.append({"role": "user", "content": user_content_list})
        else:
            # 回退到纯文本
            context_text = self.context_selector.get_text_context()
            messages.append({"role": "user", "content": context_text + user_text})

        self._is_streaming = True
        self._worker = OpenAIChatWorker(messages=messages, llm_config=llm_config)
        self._worker.content_received.connect(lambda c: self._on_content_received(c, assistant_card))
        self._worker.error_occurred.connect(lambda e: self._on_error(e, assistant_card))
        self._worker.finished_with_content.connect(lambda r: self._on_worker_finished(r, assistant_card))
        self._worker.start()

        self._toggle_send_stop(True)

    def _on_error(self, error: str, card: MessageCard):
        card.update_content(error)
        self._is_streaming = False
        self._toggle_send_stop(False)
        self.input_area.toggle_send_button(True)

    def _on_worker_finished(self, response: str, card: MessageCard):
        self._is_streaming = False
        card.finish_streaming()
        self.input_area.toggle_send_button(True)
        self._toggle_send_stop(False)
        session = self.session_manager.get_current_session()
        if session:
            session.add_assistant_message(content=response)
            # ✅ 自动保存当前会话到历史
            self._auto_save_current_session()

    def _auto_save_current_session(self):
        """根据当前状态决定保存方式"""
        session = self.session_manager.get_current_session()
        if not session or not session.messages:
            return

        if self._current_history_index is not None:
            # 正在续聊某个历史会话 → 更新它
            self.history_manager.update_session(self._current_history_index, session.messages)
        else:
            # 全新会话 → 新增一条历史记录（首次保存）
            self.history_manager.save_session(session.messages)
            # 保存后，自动绑定到新历史索引（避免重复保存）
            self._current_history_index = 0  # 因为 save_session 是 insert(0, ...)

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
            title='已中止',
            content="问答请求已被手动中止。",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2000,
            parent=self
        )

    def _on_content_received(self, content_piece: str, assistant_card: MessageCard):
        self._update_assistant_message(assistant_card, content_piece)