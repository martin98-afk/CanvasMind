# -*- coding: utf-8 -*-
import json
from datetime import datetime
from typing import Optional, Dict, Any, Callable, List, Tuple

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QListWidgetItem, QListWidget, QAbstractItemView, QLabel, \
    QApplication, QWidget
from qfluentwidgets import (
    TextEdit, setFont, ComboBox, FluentIcon, ToolButton, BodyLabel, ListWidget,
    InfoBar, InfoBarPosition, TransparentPushButton
)

from app.utils.utils import get_icon
from app.widgets.side_dock_area.plugins.llm_chatter.chat_session import SessionManager
from app.widgets.side_dock_area.plugins.llm_chatter.context_selector import ContextSelector
from app.widgets.side_dock_area.plugins.llm_chatter.message_card import MessageCard
from app.widgets.side_dock_area.plugins.llm_chatter.worker import OpenAIChatWorker
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


# ------------------ 主插件窗口 ------------------
class OpenAIChatToolWindow(ToolWindow):
    name = "大模型对话"
    icon = get_icon("大模型")
    singleton = True
    default_position = DockPosition.TOP
    session_manager = SessionManager()
    _valid_configs: Dict[str, Dict[str, Any]] = {}
    context_items: List[Tuple[str, str, Callable[[], Dict[str, Any]]]] = None  # 上下文项列表

    def __init__(self, canvas_page):
        super().__init__(canvas_page)
        self.canvas_page = canvas_page
        self._worker: Optional[OpenAIChatWorker] = None
        self._is_streaming = False
        self.session_manager.create_new_session()  # 初始化第一个会话
        # 新增：用于存储当前选中的上下文项
        self._selected_context_items = set()

    def setup_ui(self):
        self.context_items = [
            ("@graph", "当前画布", self.canvas_page.extract_graph_info),
            ("@vars", "全局变量", self.canvas_page.global_variables.to_dict),
            ("@comps", "组件信息", self.canvas_page.get_component_info)
        ]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)

        # ========== 顶部会话管理栏 ========== （保持不变）
        session_bar_layout = QHBoxLayout()
        session_bar_layout.setContentsMargins(0, 0, 0, 0)
        session_bar_layout.setSpacing(4)

        left_layout = QHBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        model_layout = QHBoxLayout()
        model_layout.addWidget(BodyLabel("模型：", self))
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

        # ========== 聊天内容区域 ========== （保持不变）
        chat_list_container = QWidget(self)
        chat_list_layout = QVBoxLayout(chat_list_container)
        chat_list_layout.setContentsMargins(10, 10, 10, 10)
        self.chat_list = ListWidget(self)
        self.chat_list.setResizeMode(ListWidget.Adjust)
        self.chat_list.setFrameShape(QListWidget.NoFrame)
        self.chat_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.chat_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chat_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.chat_list.verticalScrollBar().rangeChanged.connect(lambda: self.chat_list.scrollToBottom())
        chat_list_layout.addWidget(self.chat_list)
        layout.addWidget(chat_list_container, 1)

        # ========== 中间状态栏（使用 ContextSelector）==========
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(4)

        # 替换为独立的上下文选择器
        self.context_selector = ContextSelector(self.context_items, self)
        status_layout.addWidget(self.context_selector)
        status_layout.addStretch()

        # 发送/停止按钮
        self.send_btn = TransparentPushButton(icon=FluentIcon.SEND, text="发送", parent=self)
        self.send_btn.clicked.connect(self._on_send_clicked)
        status_layout.addWidget(self.send_btn)
        layout.addLayout(status_layout)

        # ========== 输入区域 ========== （保持不变）
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(4)
        self.input_area = TextEdit(self)
        self.input_area.setPlaceholderText("继续提问或 \"/\"新开会话")
        self.input_area.setMaximumHeight(150)
        setFont(self.input_area, 12)
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

    def _clear_current_session(self):
        session = self.session_manager.get_current_session()
        if session:
            session.messages.clear()
            self._display_current_session()

    def _on_session_changed(self, index: int):
        self.session_manager.switch_to_session(index)
        self._display_current_session()

    def _display_current_session(self):
        """清空列表并重新加载当前会话的所有消息"""
        self.chat_list.clear()
        session = self.session_manager.get_current_session()
        if not session:
            return

        for i, msg in enumerate(session.messages):
            # 创建卡片
            card = MessageCard(
                parent=self,
                role=msg["role"],
                content=msg["content"],
                timestamp=datetime.now().strftime('%H:%M')  # 实际应用中应存储真实时间戳
            )
            # 连接卡片的信号
            card.deleteRequested.connect(lambda: self._delete_message(i))
            card.copyRequested.connect(self._copy_text)
            if msg["role"] == "assistant":
                card.regenerateRequested.connect(lambda: self._regenerate_message(i))

            # 添加到列表
            item = QListWidgetItem()
            item.setSizeHint(card.sizeHint())
            self.chat_list.addItem(item)
            self.chat_list.setItemWidget(item, card)

        # 确保滚动到底部
        QTimer.singleShot(0, self.chat_list.scrollToBottom)

    def _append_user_message(self, content: str):
        """添加一条用户消息到列表"""
        card = MessageCard(parent=self, role="user", content=content)
        card.deleteRequested.connect(lambda: self._delete_message(self.chat_list.count() - 1))
        card.copyRequested.connect(self._copy_text)

        item = QListWidgetItem()
        item.setSizeHint(card.sizeHint())
        self.chat_list.addItem(item)
        self.chat_list.setItemWidget(item, card)

        # 滚动到底部
        QTimer.singleShot(0, self.chat_list.scrollToBottom)

    def _append_assistant_message(self, content: str = "") -> MessageCard:
        """添加一条助手消息，并返回其卡片对象，以便后续流式更新"""
        card = MessageCard(parent=self, role="assistant", content=content)
        card.deleteRequested.connect(lambda: self._delete_message(self.chat_list.count() - 1))
        card.copyRequested.connect(self._copy_text)
        card.regenerateRequested.connect(lambda: self._regenerate_message(self.chat_list.count() - 1))

        item = QListWidgetItem()
        item.setSizeHint(card.sizeHint())
        self.chat_list.addItem(item)
        self.chat_list.setItemWidget(item, card)

        # 滚动到底部
        QTimer.singleShot(0, self.chat_list.scrollToBottom)

        return card

    def _update_assistant_message(self, card: MessageCard, new_content: str):
        """更新指定助手消息卡片的内容"""
        card.update_content(new_content)
        # 找到卡片对应的列表项
        for i in range(self.chat_list.count()):
            if self.chat_list.itemWidget(self.chat_list.item(i)) is card:
                item = self.chat_list.item(i)
                break
        else:
            # 如果没找到，说明卡片可能已被删除或不在列表中
            return

        # 更新列表项的大小提示，以适应内容变化
        item.setSizeHint(card.sizeHint())

    def _delete_message(self, row: int):
        """删除指定的消息卡片"""
        self.chat_list.takeItem(row)

        # 同时从会话历史中移除
        session = self.session_manager.get_current_session()
        if session and 0 <= row < len(session.messages):
            session.messages.pop(row)
            # 重新显示整个会话，以保证索引一致
            self._display_current_session()

    def _copy_text(self, text: str):
        """复制文本到剪贴板"""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)

    def _regenerate_message(self, row: int):
        """重新生成这条助手消息"""
        session = self.session_manager.get_current_session()
        if not session or row < 0 or row >= len(session.messages):
            return

        # 找到对应的用户消息 (通常是前一条)
        user_msg_index = row - 1
        if user_msg_index < 0 or session.messages[user_msg_index]["role"] != "user":
            return

        user_input = session.messages[user_msg_index]["content"]
        # 删除旧的助手消息
        session.messages.pop(row)
        # 从列表中移除卡片
        self.chat_list.takeItem(row)

        # 重新发送请求
        self._send_message_with_enhanced_input(user_input)

    def _on_send_clicked(self):
        user_text = self.input_area.toPlainText().strip()
        if not user_text:
            return

        session = self.session_manager.get_current_session()
        if not session:
            return

        session.add_user_message(content=user_text)
        self._append_user_message(user_text)
        self.input_area.clear()
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

        # ✅ 关键修改：从 context_selector 获取选中项
        enhanced_input = self._get_enhanced_input(user_text)
        messages.append({"role": "user", "content": enhanced_input})

        self._worker = OpenAIChatWorker(messages=messages, llm_config=llm_config)
        self._worker.content_received.connect(lambda c: self._on_content_received(c, assistant_card))
        self._worker.error_occurred.connect(lambda e: self._on_error(e, assistant_card))
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

        self._toggle_send_stop(True)

    def _get_enhanced_input(self, user_input: str) -> str:
        """使用 context_selector 获取选中项"""
        selected = self.context_selector.get_selected_keys()
        context_info_list = []
        for context_key, context_name, context_func in self.context_items:
            if context_key in selected:
                context_info = context_func()
                # 对context_info进行格式化处理
                if isinstance(context_info, (dict, list, tuple, set)):
                    context_info = json.dumps(context_info, indent=2, ensure_ascii=False)

                context_info_list.append(f"[{context_name}信息]:\n{context_info}\n---\n")
        enhanced = "\n".join(context_info_list) + user_input

        return enhanced

    def _on_worker_finished(self):
        """工作线程结束时调用"""
        self._toggle_send_stop(False)

    def _toggle_send_stop(self, is_sending: bool):
        """根据是否正在发送来切换按钮文本和状态"""
        if is_sending:
            self.send_btn.setText("停止")
            self.send_btn.setIcon(FluentIcon.PAUSE)
            self.send_btn.clicked.disconnect(self._on_send_clicked)
            self.send_btn.clicked.connect(self._on_stop_clicked)
            # 禁用输入框和模型选择，防止干扰
            self.input_area.setDisabled(True)
            self.model_combo.setDisabled(True)
        else:
            self.send_btn.setText("发送")
            self.send_btn.setIcon(FluentIcon.SEND)
            self.send_btn.clicked.disconnect(self._on_stop_clicked)
            self.send_btn.clicked.connect(self._on_send_clicked)
            self.input_area.setDisabled(False)
            self.model_combo.setDisabled(False)

    def _on_stop_clicked(self):
        """停止按钮被点击时调用"""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()  # 强制终止线程
            # 清理资源
            self._worker = None
            # 切换回发送状态
            self._toggle_send_stop(False)
            # 给用户一个提示
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
        """流式接收内容片段，累积并更新指定卡片"""
        # 将新片段追加到累积内容中
        new_buffer = content_piece
        # 更新卡片显示
        self._update_assistant_message(assistant_card, new_buffer)

    def _on_error(self, error_msg: str, assistant_card: MessageCard):
        """处理错误，更新指定卡片"""
        self._update_assistant_message(assistant_card, f"[错误] {error_msg}")
