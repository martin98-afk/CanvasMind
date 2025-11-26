# -*- coding: utf-8 -*-
import json
from datetime import datetime
from typing import Optional, Dict, Any, Callable, List, Tuple

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QApplication, QWidget
from qfluentwidgets import (
    TextEdit, setFont, ComboBox, FluentIcon, ToolButton, TransparentPushButton,
    SingleDirectionScrollArea, InfoBar, InfoBarPosition
)

from app.utils.utils import get_icon
from app.widgets.side_dock_area.plugins.llm_chatter.chat_session import SessionManager
from app.widgets.side_dock_area.plugins.llm_chatter.context_selector import ContextSelector
from app.widgets.side_dock_area.plugins.llm_chatter.message_card import MessageCard
from app.widgets.side_dock_area.plugins.llm_chatter.worker import OpenAIChatWorker
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class OpenAIChatToolWindow(ToolWindow):
    name = "大模型对话"
    icon = get_icon("大模型")
    singleton = True
    default_position = DockPosition.TOP
    session_manager = SessionManager()
    _valid_configs: Dict[str, Dict[str, Any]] = {}
    context_items: List[Tuple[str, str, Callable[[], Dict[str, Any]]]] = None

    def __init__(self, canvas_page):
        super().__init__(canvas_page)
        self.canvas_page = canvas_page
        self._worker: Optional[OpenAIChatWorker] = None
        self._is_streaming = False
        self.session_manager.create_new_session()
        self._selected_context_items = set()
        self.canvas_page.global_variables_changed.connect(self._load_model_configs)

    def setup_ui(self):
        self.context_items = [
            ("@graph", "当前画布", self.canvas_page.extract_graph_info),
            ("@vars", "全局变量", self.canvas_page.global_variables.to_dict),
            ("@comps", "组件信息", self.canvas_page.get_component_info)
        ]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)

        # ========== 顶部会话管理栏 ==========
        session_bar_layout = QHBoxLayout()
        session_bar_layout.setContentsMargins(0, 0, 0, 5)
        session_bar_layout.setSpacing(4)

        left_layout = QHBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        model_layout = QHBoxLayout()
        model_label = QLabel("模型：", self)
        setFont(model_label, 12, QFont.Bold)
        model_label.setStyleSheet("color: #ffffff;")
        model_layout.addWidget(model_label)
        self.model_combo = ComboBox(self)
        self._load_model_configs()
        setFont(self.model_combo, 12)
        model_layout.addWidget(self.model_combo, 1)
        left_layout.addLayout(model_layout)

        separator = QLabel("|", self)
        separator.setStyleSheet("color: #666666;")
        left_layout.addWidget(separator)

        title_label = QLabel("智能会话", self)
        setFont(title_label, 12, QFont.Bold)
        title_label.setStyleSheet("color: #ffffff;")
        left_layout.addWidget(title_label)

        separator = QLabel("|", self)
        separator.setStyleSheet("color: #666666;")
        left_layout.addWidget(separator)

        self.session_combo = ComboBox(self)
        self.refresh_session_combo()
        self.session_combo.currentIndexChanged.connect(self._on_session_changed)

        self.new_session_btn = ToolButton(FluentIcon.ADD, self)
        self.new_session_btn.setToolTip("新建对话")
        self.new_session_btn.clicked.connect(self._create_new_session)

        left_layout.addWidget(self.session_combo)
        left_layout.addWidget(self.new_session_btn)

        right_layout = QHBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        user_label = QLabel("用户", self)
        user_label.setStyleSheet("color: #ffffff;")
        user_label.setPixmap(get_icon("用户").pixmap(16, 16))
        user_label.setAlignment(Qt.AlignVCenter)
        right_layout.addWidget(user_label)

        more_btn = ToolButton(FluentIcon.SETTING, self)
        more_btn.setToolTip("设置")
        right_layout.addWidget(more_btn)

        session_bar_layout.addLayout(left_layout)
        session_bar_layout.addStretch()
        session_bar_layout.addLayout(right_layout)
        layout.addLayout(session_bar_layout)

        # ========== 聊天内容区域（使用 SingleDirectionScrollArea）==========
        self.chat_scroll_area = SingleDirectionScrollArea(self)
        # 透明背景
        self.chat_scroll_area.setStyleSheet("background-color: transparent; border: none;")
        self.chat_scroll_area.setWidgetResizable(True)
        self.chat_scroll_area.setViewportMargins(0, 0, 0, 0)

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_layout.setSpacing(4)
        self.chat_layout.setAlignment(Qt.AlignBottom)  # 关键：防止垂直拉伸
        self.chat_scroll_area.setWidget(self.chat_container)

        layout.addWidget(self.chat_scroll_area, 1)

        # ========== 中间状态栏（使用 ContextSelector）==========
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(4)

        self.context_selector = ContextSelector(self.context_items, self)
        status_layout.addWidget(self.context_selector)
        status_layout.addStretch()

        self.send_btn = TransparentPushButton(icon=FluentIcon.SEND, text="发送", parent=self)
        self.send_btn.clicked.connect(self._on_send_clicked)
        status_layout.addWidget(self.send_btn)
        layout.addLayout(status_layout)

        # ========== 输入区域 ==========
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(4)
        self.input_area = TextEdit(self)
        self.input_area.setPlaceholderText("继续提问或 \"/\"新开会话")
        self.input_area.setMaximumHeight(100)
        setFont(self.input_area, 15)
        self.input_area.installEventFilter(self)
        input_layout.addWidget(self.input_area, 1)
        layout.addLayout(input_layout)

        # ========== 连接信号 ==========
        self.session_combo.currentIndexChanged.connect(self._on_session_changed)

    def _load_model_configs(self):
        self._valid_configs.clear()
        self.model_combo.clear()
        try:
            custom_vars = self.canvas_page.global_variables.custom
            for config_name, var_obj in custom_vars.items():
                if hasattr(var_obj, 'value') and isinstance(var_obj.value, dict):
                    val = var_obj.value
                    if {"API_URL", "API_KEY", "模型名称"}.issubset(val.keys()):
                        self._valid_configs[config_name] = val
            if self._valid_configs:
                self.model_combo.addItems(list(self._valid_configs.keys()))
                self.model_combo.setDisabled(False)
            else:
                self.model_combo.addItem("无有效配置")
                self.model_combo.setDisabled(True)
        except Exception as e:
            self.model_combo.addItem(f"加载失败: {e}")
            self.model_combo.setDisabled(True)

    def _create_new_session(self):
        self.session_manager.create_new_session()
        self.refresh_session_combo()
        self._display_current_session()

    def refresh_session_combo(self):
        self.session_combo.clear()
        self.session_combo.addItems(self.session_manager.get_session_names())
        self.session_combo.setCurrentIndex(self.session_manager.current_index)

    def _on_session_changed(self, index: int):
        if index >= 0:
            self.session_manager.switch_to_session(index)
            self._display_current_session()

    def _display_current_session(self):
        """清空布局并重新加载当前会话的所有消息"""
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        session = self.session_manager.get_current_session()
        if not session:
            return

        for msg in session.messages:
            card = MessageCard(
                parent=self,
                role=msg["role"],
                timestamp=msg.get("timestamp", datetime.now().strftime('%H:%M'))
            )
            card.update_content(msg["content"])
            card.deleteRequested.connect(lambda c=card: self._delete_message(c))
            card.copyRequested.connect(self._copy_text)
            if msg["role"] == "assistant":
                card.regenerateRequested.connect(lambda c=card: self._regenerate_message(c))

            self.chat_layout.addWidget(card)

        self._scroll_to_bottom()

    def _append_user_message(self, content: str):
        card = MessageCard(parent=self, role="user")
        card.update_content(content)
        card.deleteRequested.connect(lambda: self._delete_message(card))
        card.copyRequested.connect(self._copy_text)
        self.chat_layout.addWidget(card)
        self._scroll_to_bottom()

    def _append_assistant_message(self) -> MessageCard:
        card = MessageCard(parent=self, role="assistant")
        card.deleteRequested.connect(lambda: self._delete_message(card))
        card.copyRequested.connect(self._copy_text)
        card.regenerateRequested.connect(lambda: self._regenerate_message(card))
        self.chat_layout.addWidget(card)
        self._scroll_to_bottom()
        return card

    def _update_assistant_message(self, card: MessageCard, new_content: str):
        card.update_content(new_content)
        if self._is_streaming:
            self._scroll_to_bottom()

    def _delete_message(self, card_or_index):
        if isinstance(card_or_index, MessageCard):
            card = card_or_index
            # 从布局中移除
            for i in range(self.chat_layout.count()):
                if self.chat_layout.itemAt(i).widget() is card:
                    self._remove_message_at_index(i)
                    return
        else:
            self._remove_message_at_index(card_or_index)

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

        prev_widget = self.chat_layout.itemAt(card_index - 1).widget()
        if not isinstance(prev_widget, MessageCard) or prev_widget.role != "user":
            return

        user_input = prev_widget.content_widget.get_plain_text()

        # 删除当前助手消息
        self._delete_message(card)

        # 重新发送
        self._on_send_clicked(user_input)

    def _copy_text(self, text: str):
        clipboard = QApplication.clipboard()
        clipboard.setText(text)

    def _scroll_to_bottom(self):
        QTimer.singleShot(10, lambda: self.chat_scroll_area.verticalScrollBar().setValue(
            self.chat_scroll_area.verticalScrollBar().maximum()
        ))

    def _get_enhanced_input(self, user_input: str) -> str:
        selected = self.context_selector.get_selected_keys()
        context_info_list = []
        for context_key, context_name, context_func in self.context_items:
            if context_key in selected:
                context_info = context_func()
                if isinstance(context_info, (dict, list, tuple, set)):
                    context_info = json.dumps(context_info, indent=2, ensure_ascii=False)
                context_info_list.append(f"[{context_name}信息]:\n{context_info}\n---\n")
        return "\n".join(context_info_list) + user_input

    def _on_send_clicked(self, user_text: str = ""):
        session = self.session_manager.get_current_session()
        if not user_text:
            user_text = self.input_area.toPlainText().strip()
            if not user_text:
                return
            session.add_user_message(content=user_text)
            self.input_area.clear()
            self._append_user_message(user_text)

        assistant_card = self._append_assistant_message()
        selected_name = self.model_combo.currentText()
        llm_config = self._valid_configs.get(selected_name)
        if not llm_config:
            self._update_assistant_message(assistant_card, "[错误] 模型配置无效")
            return

        messages = []
        system_prompt = llm_config.get("系统提示", "").strip()
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        for msg in session.messages[:-1]:
            messages.append(msg)

        enhanced_input = self._get_enhanced_input(user_text)
        messages.append({"role": "user", "content": enhanced_input})

        self._is_streaming = True
        self._worker = OpenAIChatWorker(messages=messages, llm_config=llm_config)
        self._worker.content_received.connect(lambda c: self._on_content_received(c, assistant_card))
        self._worker.error_occurred.connect(lambda e: self._on_error(e, assistant_card))
        self._worker.finished_with_content.connect(self._on_worker_finished)
        self._worker.start()

        self._toggle_send_stop(True)

    def _on_error(self, error: str, card: MessageCard):
        self._is_streaming = False
        self._toggle_send_stop(False)
        self._update_assistant_message(card, error)

    def _on_worker_finished(self, response: str):
        self._is_streaming = False
        self._toggle_send_stop(False)
        session = self.session_manager.get_current_session()
        if session:
            session.add_assistant_message(content=response)

    def _toggle_send_stop(self, is_sending: bool):
        if is_sending:
            self.send_btn.setText("停止")
            self.send_btn.setIcon(FluentIcon.PAUSE)
            try:
                self.send_btn.clicked.disconnect()
            except TypeError:
                pass
            self.send_btn.clicked.connect(self._on_stop_clicked)
            self.input_area.setDisabled(True)
            self.model_combo.setDisabled(True)
        else:
            self.send_btn.setText("发送")
            self.send_btn.setIcon(FluentIcon.SEND)
            try:
                self.send_btn.clicked.disconnect()
            except TypeError:
                pass
            self.send_btn.clicked.connect(self._on_send_clicked)
            self.input_area.setDisabled(False)
            self.model_combo.setDisabled(False)

    def _on_stop_clicked(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker = None
            self._is_streaming = False
            self._toggle_send_stop(False)
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