# 大模型输入框
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QKeyEvent, QKeySequence, QDragEnterEvent, QDropEvent
from PyQt5.QtWidgets import QShortcut, QTextEdit
from qfluentwidgets import FluentIcon, ComboBox
from qfluentwidgets import TextEdit, TransparentToolButton
from qtpy import QtCore


class SendableTextEdit(QTextEdit):
    sendMessageRequested = pyqtSignal()
    stopMessageRequested = pyqtSignal()
    clearRequested = pyqtSignal()
    newSessionRequested = pyqtSignal()
    historyUpRequested = pyqtSignal()
    historyDownRequested = pyqtSignal()
    agentChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("给 CanvasMind 发送消息，Enter 发送，Shift+Enter 换行")
        self.setAcceptRichText(False)
        self.setLineWrapMode(TextEdit.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setAcceptDrops(True)
        self.setMinimumHeight(96)
        self.setStyleSheet("""
            QTextEdit {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(18, 24, 34, 245),
                    stop:1 rgba(24, 31, 45, 245));
                color: #F2F6FF;
                border: 1px solid #2B3850;
                border-radius: 18px;
                padding: 14px 128px 18px 16px;
                selection-background-color: rgba(103, 197, 255, 0.28);
                font-size: 14px;
            }
            QTextEdit:focus {
                border: 1px solid #4E93FF;
                background: rgba(22, 29, 41, 248);
            }
            QTextEdit QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.05);
                width: 6px;
                margin: 2px 0 2px 0;
                border-radius: 3px;
            }
            QTextEdit QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.15);
                border-radius: 3px;
                min-height: 20px;
            }
            QTextEdit QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.25);
            }
            QTextEdit QScrollBar::add-line:vertical,
            QTextEdit QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QTextEdit QScrollBar::add-page:vertical,
            QTextEdit QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

        self._agent_combo = ComboBox(self)
        self._agent_combo.setFixedSize(126, 28)
        self._agent_combo.setStyleSheet("""
            ComboBox {
                background-color: rgba(255, 255, 255, 0.05);
                color: #EAF2FF;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 3px 10px;
                font-size: 12px;
            }
            ComboBox:hover {
                background-color: rgba(255, 255, 255, 0.08);
                border-color: rgba(103, 197, 255, 0.45);
            }
            ComboBox::drop-down {
                border: none;
                width: 16px;
            }
            ComboBox::down-arrow {
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #9BB0D3;
                margin-right: 2px;
            }
            ComboBox AbstractItemView {
                background-color: #192232;
                color: #EAF2FF;
                selection-background-color: #2B4C78;
                border: 1px solid #2B3850;
                border-radius: 10px;
                padding: 4px;
            }
        """)
        self._agent_combo.currentTextChanged.connect(self._on_agent_changed)

        QTimer.singleShot(0, self._position_elements)

        self.send_btn = TransparentToolButton(FluentIcon.SEND, self)
        self.send_btn.setFixedSize(34, 34)
        self.send_btn.setToolTip("发送（Enter）")
        self.send_btn.clicked.connect(self._on_send_click)
        self.send_btn.setDisabled(True)
        self.send_btn.setStyleSheet("""
            TransparentToolButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #66C6FF, stop:1 #4E93FF);
                border: none;
                border-radius: 17px;
                color: white;
            }
            TransparentToolButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #78D0FF, stop:1 #6AA8FF);
            }
            TransparentToolButton:disabled {
                background: rgba(255, 255, 255, 0.10);
                color: rgba(255, 255, 255, 0.45);
            }
        """)
        self.textChanged.connect(self._on_text_changed)

        self._setup_keyboard_shortcuts()

    def _on_agent_changed(self, text: str):
        self.agentChanged.emit(text)

    def _setup_keyboard_shortcuts(self):
        self._shortcut_clear = QShortcut(QKeySequence("Ctrl+L"), self)
        self._shortcut_clear.activated.connect(self._on_clear_shortcut)

        self._shortcut_new = QShortcut(QKeySequence("Ctrl+N"), self)
        self._shortcut_new.activated.connect(self._on_new_session_shortcut)

    def _on_clear_shortcut(self):
        self.clearRequested.emit()

    def _on_new_session_shortcut(self):
        self.newSessionRequested.emit()

    def _on_text_changed(self):
        has_text = bool(self.toPlainText().strip())
        self.send_btn.setDisabled(not has_text)

    def _rebind_send_btn(self, handler):
        try:
            self.send_btn.clicked.disconnect()
        except TypeError:
            pass
        self.send_btn.clicked.connect(handler)

    def toggle_send_button(self, enable: bool):
        """启用/禁用发送按钮"""
        if enable:
            self.send_btn.setIcon(FluentIcon.SEND)
            self.send_btn.setToolTip("发送（Enter）")
            self._rebind_send_btn(self._on_send_click)
            self._on_text_changed()
        else:
            self.send_btn.setIcon(FluentIcon.PAUSE)
            self.send_btn.setToolTip("停止")
            QtCore.QTimer.singleShot(100, lambda: self.send_btn.setDisabled(False))
            self._rebind_send_btn(self._on_stop_click)

    def _on_send_click(self):
        """发送按钮点击事件"""
        if not self.toPlainText().strip():
            return
        self.toggle_send_button(False)
        self.sendMessageRequested.emit()

    def _on_stop_click(self):
        """停止按钮点击事件"""
        self.toggle_send_button(True)
        self.stopMessageRequested.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_elements()

    def _position_elements(self):
        """定位智能体选择框和发送按钮"""
        if self._agent_combo and self.send_btn:
            btn_size = self.send_btn.size()
            agent_width = self._agent_combo.width()

            send_btn_x = self.width() - btn_size.width() - 12
            send_btn_y = self.height() - btn_size.height() - 10

            combo_x = send_btn_x - agent_width - 8
            combo_y = send_btn_y + (btn_size.height() - self._agent_combo.height()) // 2

            self._agent_combo.move(max(0, combo_x), max(0, combo_y))
            self.send_btn.move(max(0, send_btn_x), max(0, send_btn_y))

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)  # 换行
            else:
                self._on_send_click()
                event.accept()
        elif event.key() == Qt.Key_Up:
            if event.modifiers() & Qt.ControlModifier:
                self.historyUpRequested.emit()
                event.accept()
            else:
                super().keyPressEvent(event)
        elif event.key() == Qt.Key_Down:
            if event.modifiers() & Qt.ControlModifier:
                self.historyDownRequested.emit()
                event.accept()
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent):
        text = event.mimeData().text()
        if text:
            lines = text.split("\n")
            component_path = lines[0] if lines else ""
            extension_path = lines[1] if len(lines) > 1 else ""

            insert_text = f"组件路径: {component_path}"
            if extension_path:
                insert_text += f"\n扩展资源路径: {extension_path}"

            cursor = self.textCursor()
            cursor.insertText(insert_text)
            self.setTextCursor(cursor)
            self._on_text_changed()
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self._ensure_cursor_visible)

    def _ensure_cursor_visible(self):
        cursor = self.textCursor()
        if cursor.position() > 0:
            self.ensureCursorVisible()
