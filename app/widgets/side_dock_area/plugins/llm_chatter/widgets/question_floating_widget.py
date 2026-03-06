# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QCheckBox,
    QSizePolicy,
    QTextEdit,
    QGridLayout,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from qfluentwidgets import CardWidget, PrimaryPushButton


class QuestionFloatingWidget(CardWidget):
    """Question 悬浮框组件 - 让用户选择答案或输入文本"""

    answered = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._question = ""
        self._options = []
        self._multiple = False
        self._text_input_mode = False
        self._option_widgets = []
        self._setup_ui()

    def _setup_ui(self):
        self.setSizePolicy(1, 0)
        self.setMaximumHeight(350)
        self.setMinimumHeight(100)
        self.setStyleSheet("""
            CardWidget {
                background-color: rgba(30, 30, 30, 240);
                border: 1px solid #404040;
                border-radius: 8px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)

        title = QLabel("❓ 询问", self)
        title.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        title.setStyleSheet("color: #ffffff;")

        header.addWidget(title)
        header.addStretch()

        close_btn = QPushButton("✕", self)
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #757575;
                border: none;
                font-size: 12px;
            }
            QPushButton:hover {
                color: #ffffff;
                background-color: #404040;
                border-radius: 3px;
            }
        """)
        close_btn.clicked.connect(self._on_cancel)
        header.addWidget(close_btn)

        self.question_label = QLabel("", self)
        self.question_label.setFont(QFont("Microsoft YaHei", 10))
        self.question_label.setStyleSheet("color: #e0e0e0;")
        self.question_label.setWordWrap(True)
        self.question_label.setMinimumHeight(24)
        self.question_label.setMaximumHeight(60)

        self.text_input = QTextEdit(self)
        self.text_input.setPlaceholderText("请输入您的回答...")
        self.text_input.setFont(QFont("Microsoft YaHei", 10))
        self.text_input.setStyleSheet("""
            QTextEdit {
                background-color: #2a2a2a;
                color: #ffffff;
                border: 1px solid #505050;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        self.text_input.setMaximumHeight(80)
        self.text_input.setVisible(False)

        self.options_container = QWidget()
        self.options_layout = QGridLayout(self.options_container)
        self.options_layout.setSpacing(8)
        self.options_layout.setContentsMargins(0, 0, 0, 0)

        self.button_area = QHBoxLayout()
        self.button_area.addStretch()

        self.confirm_btn = PrimaryPushButton("确认", self)
        self.confirm_btn.setVisible(False)
        self.confirm_btn.setStyleSheet("""
            PrimaryPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 11px;
            }
            PrimaryPushButton:hover {
                background-color: #1084d8;
            }
        """)
        self.confirm_btn.clicked.connect(self._on_confirm)
        self.button_area.addWidget(self.confirm_btn)

        main_layout.addLayout(header)
        main_layout.addWidget(self.question_label)
        main_layout.addWidget(self.text_input)
        main_layout.addWidget(self.options_container, 1)
        main_layout.addLayout(self.button_area)

    def _on_cancel(self):
        self.setVisible(False)
        self.cancelled.emit()

    def _on_confirm(self):
        if self._text_input_mode:
            text = self.text_input.toPlainText().strip()
            if text:
                self.setVisible(False)
                self.answered.emit(text)
            return

        selected = []
        for widget in self._option_widgets:
            if isinstance(widget, QCheckBox) and widget.isChecked():
                selected.append(widget.text())
        result = ", ".join(selected)
        self.setVisible(False)
        self.answered.emit(result)

    def _on_select(self, option):
        self.setVisible(False)
        if isinstance(option, dict):
            option = option.get("label", str(option))
        self.answered.emit(str(option))

    def _on_checkbox_toggled(self, checked):
        if self._multiple:
            selected_count = sum(
                1
                for w in self._option_widgets
                if isinstance(w, QCheckBox) and w.isChecked()
            )
            self.confirm_btn.setVisible(selected_count > 0)
            if selected_count > 0:
                self.confirm_btn.setText(f"确认 ({selected_count})")

    def show_question(self, question: str, options: list, multiple: bool = False):
        self._question = question
        self._options = options
        self._multiple = multiple
        self._option_widgets = []

        self.question_label.setText(question)
        self.setVisible(True)
        self.confirm_btn.setVisible(False)
        self.confirm_btn.setText("确认")
        self.text_input.clear()

        while self.options_layout.count():
            item = self.options_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        if not options or len(options) == 0:
            self._text_input_mode = True
            self.text_input.setVisible(True)
            self.options_container.setVisible(False)
            self.confirm_btn.setVisible(True)
            self.confirm_btn.setText("提交")
            return

        self._text_input_mode = False
        self.text_input.setVisible(False)
        self.options_container.setVisible(True)

        cols = 2 if len(options) > 2 else len(options)
        if cols < 1:
            cols = 1

        for i, option in enumerate(options):
            row = i // cols
            col = i % cols
            if multiple:
                widget = self._create_checkbox(option)
            else:
                widget = self._create_button(option)
            self.options_layout.addWidget(widget, row, col)
            self._option_widgets.append(widget)

    def _create_checkbox(self, option):
        text = option.get("label", option) if isinstance(option, dict) else str(option)
        checkbox = QCheckBox(text, self)
        checkbox.setCursor(Qt.PointingHandCursor)
        checkbox.setStyleSheet("""
            QCheckBox {
                color: #ffffff;
                spacing: 6px;
                padding: 8px 10px;
                background-color: #3a3a3a;
                border: 1px solid #505050;
                border-radius: 4px;
            }
            QCheckBox:hover {
                background-color: #4a4a4a;
                border-color: #606060;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid #606060;
                background-color: #2a2a2a;
            }
            QCheckBox::indicator:checked {
                background-color: #0078d4;
                border-color: #0078d4;
            }
        """)
        checkbox.setMinimumHeight(36)
        checkbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        checkbox.setWordWrap(True)
        checkbox.stateChanged.connect(self._on_checkbox_toggled)
        return checkbox

    def _create_button(self, option):
        btn_text = (
            option.get("label", option) if isinstance(option, dict) else str(option)
        )
        btn = QPushButton(btn_text, self)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: #ffffff;
                border: 1px solid #505050;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 11px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #606060;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
            }
        """)
        btn.setMinimumHeight(36)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.clicked.connect(lambda checked, opt=option: self._on_select(opt))
        return btn

    def clear(self):
        self._question = ""
        self._options = []
        self._multiple = False
        self._text_input_mode = False
        self.text_input.clear()
        self.setVisible(False)
        self.cancelled.emit()

    def _on_confirm(self):
        if self._text_input_mode:
            text = self.text_input.toPlainText().strip()
            if text:
                self.setVisible(False)
                self.answered.emit(text)
            return

        selected = []
        for widget in self._option_widgets:
            if isinstance(widget, QCheckBox) and widget.isChecked():
                selected.append(widget.text())
        result = ", ".join(selected)
        self.setVisible(False)
        self.answered.emit(result)

    def _on_select(self, option):
        self.setVisible(False)
        if isinstance(option, dict):
            option = option.get("label", str(option))
        self.answered.emit(str(option))

    def _on_checkbox_toggled(self, checked):
        if self._multiple:
            selected_count = sum(
                1
                for w in self._option_widgets
                if isinstance(w, QCheckBox) and w.isChecked()
            )
            self.confirm_btn.setVisible(selected_count > 0)
            if selected_count > 0:
                self.confirm_btn.setText(f"确认 ({selected_count})")

    def show_question(self, question: str, options: list, multiple: bool = False):
        self._question = question
        self._options = options
        self._multiple = multiple
        self._option_widgets = []

        self.question_label.setText(question)
        self.setVisible(True)
        self.confirm_btn.setVisible(False)
        self.confirm_btn.setText("确认")
        self.text_input.clear()

        while self.options_layout.count():
            item = self.options_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        if not options or len(options) == 0:
            self._text_input_mode = True
            self.text_input.setVisible(True)
            self.options_container.setVisible(False)
            self.confirm_btn.setVisible(True)
            self.confirm_btn.setText("提交")
            return

        self._text_input_mode = False
        self.text_input.setVisible(False)
        self.options_container.setVisible(True)

        for option in options:
            if multiple:
                widget = self._create_checkbox(option)
            else:
                widget = self._create_button(option)
            self.options_layout.addWidget(widget)
            self._option_widgets.append(widget)

    def _create_checkbox(self, option):
        text = option.get("label", option) if isinstance(option, dict) else str(option)
        checkbox = QCheckBox(text, self)
        checkbox.setCursor(Qt.PointingHandCursor)
        checkbox.setStyleSheet("""
            QCheckBox {
                color: #ffffff;
                spacing: 6px;
                padding: 8px 10px;
                background-color: #3a3a3a;
                border: 1px solid #505050;
                border-radius: 4px;
            }
            QCheckBox:hover {
                background-color: #4a4a4a;
                border-color: #606060;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid #606060;
                background-color: #2a2a2a;
            }
            QCheckBox::indicator:checked {
                background-color: #0078d4;
                border-color: #0078d4;
            }
        """)
        checkbox.setMinimumHeight(36)
        checkbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        checkbox.setWordWrap(True)
        checkbox.stateChanged.connect(self._on_checkbox_toggled)
        return checkbox

    def _create_button(self, option):
        btn_text = (
            option.get("label", option) if isinstance(option, dict) else str(option)
        )
        btn = QPushButton(btn_text, self)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: #ffffff;
                border: 1px solid #505050;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 11px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #606060;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
            }
        """)
        btn.setMinimumHeight(36)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.clicked.connect(lambda checked, opt=option: self._on_select(opt))
        return btn

    def clear(self):
        self._question = ""
        self._options = []
        self._multiple = False
        self._text_input_mode = False
        self.text_input.clear()
        self.setVisible(False)
        self.cancelled.emit()

    def _on_confirm(self):
        if self._text_input_mode:
            text = self.text_input.toPlainText().strip()
            if text:
                self.setVisible(False)
                self.answered.emit(text)
            return

        selected = []
        for i in range(self.options_layout.count()):
            widget = self.options_layout.itemAt(i).widget()
            if widget and isinstance(widget, QCheckBox) and widget.isChecked():
                selected.append(widget.text())
        result = ", ".join(selected)
        self.setVisible(False)
        self.answered.emit(result)

    def _on_select(self, option):
        self.setVisible(False)
        if isinstance(option, dict):
            option = option.get("label", str(option))
        self.answered.emit(str(option))

    def _on_checkbox_toggled(self, checked):
        if self._multiple:
            selected_count = 0
            for i in range(self.options_layout.count()):
                widget = self.options_layout.itemAt(i).widget()
                if widget and isinstance(widget, QCheckBox) and widget.isChecked():
                    selected_count += 1
            self.confirm_btn.setVisible(selected_count > 0)
            if selected_count > 0:
                self.confirm_btn.setText(f"确认 ({selected_count})")

    def show_question(self, question: str, options: list, multiple: bool = False):
        self._question = question
        self._options = options
        self._multiple = multiple

        self.question_label.setText(question)
        self.setVisible(True)
        self.confirm_btn.setVisible(False)
        self.confirm_btn.setText("确认")
        self.text_input.clear()

        while self.options_layout.count():
            item = self.options_layout.takeAt(0)
            if item:
                if item.widget():
                    item.widget().deleteLater()

        if not options or len(options) == 0:
            self._text_input_mode = True
            self.text_input.setVisible(True)
            self.options_container.setVisible(False)
            self.confirm_btn.setVisible(True)
            self.confirm_btn.setText("提交")
            return

        self._text_input_mode = False
        self.text_input.setVisible(False)
        self.options_container.setVisible(True)

        if multiple:
            for option in options:
                widget = self._create_checkbox(option)
                self.options_layout.addWidget(widget)
        else:
            for option in options:
                widget = self._create_button(option)
                self.options_layout.addWidget(widget)

    def _create_checkbox(self, option):
        text = option.get("label", option) if isinstance(option, dict) else str(option)
        checkbox = QCheckBox(text, self)
        checkbox.setCursor(Qt.PointingHandCursor)
        checkbox.setStyleSheet("""
            QCheckBox {
                color: #ffffff;
                spacing: 6px;
                padding: 8px 10px;
                background-color: #3a3a3a;
                border: 1px solid #505050;
                border-radius: 4px;
            }
            QCheckBox:hover {
                background-color: #4a4a4a;
                border-color: #606060;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid #606060;
                background-color: #2a2a2a;
            }
            QCheckBox::indicator:checked {
                background-color: #0078d4;
                border-color: #0078d4;
            }
        """)
        checkbox.setMinimumHeight(36)
        checkbox.setMaximumWidth(300)
        checkbox.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        checkbox.setWordWrap(True)
        checkbox.stateChanged.connect(self._on_checkbox_toggled)
        return checkbox

    def _create_button(self, option):
        btn_text = (
            option.get("label", option) if isinstance(option, dict) else str(option)
        )
        btn = QPushButton(btn_text, self)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: #ffffff;
                border: 1px solid #505050;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 11px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #606060;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
            }
        """)
        btn.setMinimumHeight(36)
        btn.setMaximumWidth(300)
        btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        btn.clicked.connect(lambda checked, opt=option: self._on_select(opt))
        return btn

    def clear(self):
        self._question = ""
        self._options = []
        self._multiple = False
        self._text_input_mode = False
        self.text_input.clear()
        self.setVisible(False)
