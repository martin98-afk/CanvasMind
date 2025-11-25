# -*- coding: utf-8 -*-
from datetime import datetime
from typing import Optional, Dict, Any, List

from PyQt5.QtCore import Qt, QObject, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QListWidgetItem, QListWidget, QAbstractItemView, QLabel, \
    QApplication
from qfluentwidgets import (
    TextEdit, PrimaryPushButton, setFont, ComboBox, CheckBox, FluentIcon, ToolButton, BodyLabel, ListWidget
)

from app.utils.utils import get_icon
from app.widgets.side_dock_area.plugins.llm_chatter.chat_session import SessionManager
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

    def __init__(self, canvas_page):
        super().__init__(canvas_page)
        self.canvas_page = canvas_page
        self._worker: Optional[OpenAIChatWorker] = None
        self._is_streaming = False
        self.session_manager.create_new_session()  # 初始化第一个会话
        self._assistant_card_content_buffer: Dict[MessageCard, str] = {}

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ========== 顶部会话管理栏 ==========
        session_bar_layout = QHBoxLayout()
        session_bar_layout.setContentsMargins(0, 0, 0, 0)
        session_bar_layout.setSpacing(4)

        # 左侧：标题和会话选择
        left_layout = QHBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        # 标题 (模仿通义灵码)
        title_label = QLabel("智能会话", self)
        setFont(title_label, 12, QFont.Bold)
        title_label.setStyleSheet("color: #ffffff;")
        left_layout.addWidget(title_label)

        # 分隔线
        separator = QLabel("|", self)
        separator.setStyleSheet("color: #666666;")
        left_layout.addWidget(separator)

        # 会话下拉框
        self.session_combo = ComboBox(self)
        self.refresh_session_combo()
        self.session_combo.currentIndexChanged.connect(self._on_session_changed)

        # 新建会话按钮
        self.new_session_btn = ToolButton(FluentIcon.ADD, self)
        self.new_session_btn.setToolTip("新建对话")
        self.new_session_btn.clicked.connect(self._create_new_session)

        left_layout.addWidget(self.session_combo)
        left_layout.addWidget(self.new_session_btn)

        # 右侧：用户信息和设置
        right_layout = QHBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # 用户信息 (示例)
        user_label = QLabel("用户", self)
        user_label.setStyleSheet("color: #ffffff;")
        user_label.setPixmap(get_icon("用户").pixmap(16, 16))  # 假设你有一个用户图标
        user_label.setAlignment(Qt.AlignVCenter)
        right_layout.addWidget(user_label)

        # 更多选项按钮 (如设置、帮助等)
        more_btn = ToolButton(FluentIcon.SETTING, self)
        more_btn.setToolTip("设置")
        right_layout.addWidget(more_btn)

        session_bar_layout.addLayout(left_layout)
        session_bar_layout.addStretch()
        session_bar_layout.addLayout(right_layout)

        layout.addLayout(session_bar_layout)

        # ========== 聊天内容区域 (使用 QListWidget) ==========
        self.chat_list = ListWidget(self)
        self.chat_list.setResizeMode(ListWidget.Adjust)  # ✅ 必须！
        self.chat_list.setSpacing(8)
        self.chat_list.setFrameShape(QListWidget.NoFrame)
        self.chat_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.chat_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chat_list.setSelectionMode(QAbstractItemView.NoSelection)
        # 启用自动滚动到末尾
        self.chat_list.verticalScrollBar().rangeChanged.connect(
            lambda: self.chat_list.scrollToBottom()
        )

        layout.addWidget(self.chat_list, 1)

        # ========== 输入区域 ==========
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(4)

        # 输入框
        self.input_area = TextEdit(self)
        self.input_area.setPlaceholderText("继续提问或 \"/\"新开会话")
        self.input_area.setMaximumHeight(150)
        setFont(self.input_area, 12)
        self.input_area.installEventFilter(self)

        # 发送按钮
        self.send_btn = PrimaryPushButton("发送", self)
        self.send_btn.clicked.connect(self._on_send_clicked)

        input_layout.addWidget(self.input_area, 1)
        input_layout.addWidget(self.send_btn)

        layout.addLayout(input_layout)

        # ========== 底部状态栏 (可选) ==========
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(4)

        # 模型选择
        model_layout = QHBoxLayout()
        model_layout.addWidget(BodyLabel("模型：", self))
        self.model_combo = ComboBox(self)
        self._load_model_configs()
        setFont(self.model_combo, 12)
        model_layout.addWidget(self.model_combo, 1)

        # 上下文选项
        context_layout = QHBoxLayout()
        self.code_context_cb = CheckBox("注入当前代码", self)
        self.vars_context_cb = CheckBox("注入全局变量", self)
        self.code_context_cb.setChecked(True)
        context_layout.addWidget(self.code_context_cb)
        context_layout.addWidget(self.vars_context_cb)
        context_layout.addStretch()

        status_layout.addLayout(model_layout)
        status_layout.addLayout(context_layout)

        layout.addLayout(status_layout)

        # ========== 连接信号 ==========
        self.session_combo.currentIndexChanged.connect(self._on_session_changed)
        self.input_area.installEventFilter(self)

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

        for msg in session.messages:
            # 创建卡片
            card = MessageCard(
                role=msg["role"],
                content=msg["content"],
                timestamp=datetime.now().strftime('%H:%M')  # 实际应用中应存储真实时间戳
            )
            # 连接卡片的信号
            card.deleteRequested.connect(lambda: self._delete_message(card))
            card.copyRequested.connect(self._copy_text)
            if msg["role"] == "assistant":
                card.regenerateRequested.connect(lambda: self._regenerate_message(card))

            # 添加到列表
            item = QListWidgetItem()
            item.setSizeHint(card.sizeHint())
            self.chat_list.addItem(item)
            self.chat_list.setItemWidget(item, card)

        # 确保滚动到底部
        QTimer.singleShot(0, self.chat_list.scrollToBottom)

    def _append_user_message(self, content: str):
        """添加一条用户消息到列表"""
        card = MessageCard(role="user", content=content)
        card.deleteRequested.connect(lambda: self._delete_message(card))
        card.copyRequested.connect(self._copy_text)

        item = QListWidgetItem()
        item.setSizeHint(card.sizeHint())
        self.chat_list.addItem(item)
        self.chat_list.setItemWidget(item, card)

        # 滚动到底部
        QTimer.singleShot(0, self.chat_list.scrollToBottom)

    def _append_assistant_message(self, content: str) -> MessageCard:
        """添加一条助手消息，并返回其卡片对象，以便后续流式更新"""
        card = MessageCard(role="assistant", content=content)
        card.deleteRequested.connect(lambda: self._delete_message(card))
        card.copyRequested.connect(self._copy_text)
        card.regenerateRequested.connect(lambda: self._regenerate_message(card))

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
        item = self.chat_list.itemAt(card.pos())  # 这个方法在某些复杂布局下可能不准确
        # 更可靠的获取方式：
        for i in range(self.chat_list.count()):
            if self.chat_list.itemWidget(self.chat_list.item(i)) is card:
                item = self.chat_list.item(i)
                break
        else:
            # 如果没找到，说明卡片可能已被删除或不在列表中
            return

        # 更新列表项的大小提示，以适应内容变化
        item.setSizeHint(card.sizeHint())

    def _delete_message(self, card: MessageCard):
        """删除指定的消息卡片"""
        row = self.chat_list.indexFromItemWidget(card).row()
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

    def _regenerate_message(self, card: MessageCard):
        """重新生成这条助手消息"""
        row = self.chat_list.indexFromItemWidget(card).row()
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

        # 记录原始输入
        session.add_user_message(content=user_text)
        # 显示用户消息
        self._append_user_message(user_text)

        self.input_area.clear()
        # 创建一个占位的助手消息卡片，用于流式更新
        assistant_card = self._append_assistant_message("思考中...")

        # 获取模型配置
        selected_name = self.model_combo.currentText()
        llm_config = self._valid_configs.get(selected_name)
        if not llm_config:
            self._update_assistant_message(assistant_card, "[错误] 模型配置无效")
            return

        # 构建完整 messages
        messages = []

        system_prompt = llm_config.get("系统提示", "").strip()
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # 添加历史（但用原始 user 输入，非增强版，避免污染历史）
        for msg in session.messages[:-1]:  # 最后一条是刚加的 user 消息
            messages.append(msg)

        # 增强输入
        enhanced_input = self._get_enhanced_input(user_text)
        messages.append({"role": "user", "content": enhanced_input})

        # 启动 Worker
        self._worker = OpenAIChatWorker(messages=messages, llm_config=llm_config)
        self._worker.content_received.connect(lambda c: self._on_content_received(c, assistant_card))
        self._worker.error_occurred.connect(lambda e: self._on_error(e, assistant_card))
        self._worker.finished.connect(lambda: self._on_worker_finished(assistant_card))
        self._worker.start()

    def _get_enhanced_input(self, user_input: str) -> str:
        """根据勾选项增强用户输入"""
        enhanced = user_input

        # 注入当前代码（假设 canvas_page 有 active_editor 或类似）
        if self.code_context_cb.isChecked():
            try:
                # 尝试从 canvas_page 获取当前编辑器选中文本或全文
                editor = getattr(self.canvas_page, 'current_editor', None)
                if editor and hasattr(editor, 'textCursor'):
                    cursor = editor.textCursor()
                    if cursor.hasSelection():
                        code = cursor.selectedText()
                        enhanced = f"[当前选中代码]\n{code}\n\n---\n{user_input}"
                    else:
                        # 或者获取全文（谨慎，可能太长）
                        # full_code = editor.toPlainText()
                        # enhanced = f"[当前文件代码]\n{full_code[:2000]}...\n\n---\n{user_input}"
                        pass
            except Exception:
                pass

        # 注入全局变量
        if self.vars_context_cb.isChecked():
            try:
                custom_vars = self.canvas_page.global_variables.custom
                var_reprs = []
                for name, var_obj in custom_vars.items():
                    if hasattr(var_obj, 'value'):
                        var_reprs.append(f"{name} = {repr(var_obj.value)[:100]}")
                if var_reprs:
                    var_text = "\n".join(var_reprs)
                    enhanced = f"[全局变量]\n{var_text}\n\n---\n{enhanced}"
            except Exception:
                pass

        return enhanced

    def _on_content_received(self, content_piece: str, assistant_card: MessageCard):
        """流式接收内容片段，累积并更新指定卡片"""
        # 获取或初始化该卡片的累积内容
        current_buffer = self._assistant_card_content_buffer.get(assistant_card, "")
        # 将新片段追加到累积内容中
        new_buffer = current_buffer + content_piece
        # 更新字典中的缓冲区
        self._assistant_card_content_buffer[assistant_card] = new_buffer
        # 更新卡片显示
        self._update_assistant_message(assistant_card, new_buffer)

    def _on_error(self, error_msg: str, assistant_card: MessageCard):
        """处理错误，更新指定卡片"""
        self._update_assistant_message(assistant_card, f"[错误] {error_msg}")

    def _on_worker_finished(self, assistant_card: MessageCard):
        """任务完成，保存最终结果到会话历史"""
        if self._worker and self._worker.full_response:
            session = self.session_manager.get_current_session()
            if session:
                # 替换最后一条消息 (即我们刚刚创建的助手消息)
                session.messages[-1] = {"role": "assistant", "content": self._worker.full_response}
                # 更新卡片显示 (使用 Worker 提供的完整内容，更可靠)
                self._update_assistant_message(assistant_card, self._worker.full_response)

        # 清理该卡片的累积缓冲区
        if assistant_card in self._assistant_card_content_buffer:
            del self._assistant_card_content_buffer[assistant_card]