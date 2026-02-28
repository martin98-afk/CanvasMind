# 大模型输入框
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeyEvent, QKeySequence
from PyQt5.QtWidgets import QShortcut
from qfluentwidgets import FluentIcon
from qfluentwidgets import TextEdit, TransparentToolButton
from qtpy import QtCore


class SendableTextEdit(TextEdit):
    sendMessageRequested = pyqtSignal()
    stopMessageRequested = pyqtSignal()
    clearRequested = pyqtSignal()
    newSessionRequested = pyqtSignal()
    historyUpRequested = pyqtSignal()
    historyDownRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(
            "enter 发送信息, shift+enter 换行 | Ctrl+L 清空 | Ctrl+N 新对话"
        )
        self.setAcceptRichText(False)
        self.setLineWrapMode(TextEdit.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 创建内嵌发送按钮
        self.send_btn = TransparentToolButton(FluentIcon.SEND, self)
        self.send_btn.setFixedSize(28, 28)
        self.send_btn.setToolTip("发送（Enter）")
        self.send_btn.clicked.connect(self._on_send_click)
        self._position_send_button()
        self.send_btn.setDisabled(True)
        # 监听文本变化，控制按钮显隐
        self.textChanged.connect(self._on_text_changed)
        self._position_send_button()

        self._setup_keyboard_shortcuts()

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
        if has_text:
            self.send_btn.setDisabled(False)
        else:
            self.send_btn.setDisabled(True)

    def toggle_send_button(self, enable: bool):
        """启用/禁用发送按钮"""
        if enable:
            self.send_btn.setIcon(FluentIcon.SEND)
            self.send_btn.setToolTip("发送（Enter）")
            self.send_btn.clicked.disconnect()
            self.send_btn.clicked.connect(self._on_send_click)
        else:
            self.send_btn.setIcon(FluentIcon.PAUSE)
            self.send_btn.setToolTip("停止")
            QtCore.QTimer.singleShot(100, lambda: self.send_btn.setDisabled(False))
            self.send_btn.clicked.disconnect()
            self.send_btn.clicked.connect(self._on_stop_click)

    def _on_send_click(self):
        """发送按钮点击事件"""
        self.toggle_send_button(False)
        self.sendMessageRequested.emit()

    def _on_stop_click(self):
        """停止按钮点击事件"""
        self.toggle_send_button(True)
        self.stopMessageRequested.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_send_button()

    def _position_send_button(self):
        """将按钮定位到输入框右下角内侧"""
        if self.send_btn:
            btn_size = self.send_btn.size()
            # 距离右边界 6px，距离下边界 6px
            x = self.width() - btn_size.width() - 3
            y = self.height() - btn_size.height() - 3
            self.send_btn.move(max(0, x), max(0, y))

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
