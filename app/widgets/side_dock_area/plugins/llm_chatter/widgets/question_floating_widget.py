# -*- coding: utf-8 -*-
from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from functools import partial

from qfluentwidgets import CardWidget, PrimaryPushButton
from app.utils.utils import get_unified_font


class WrappedOptionButton(QPushButton):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._selected = False
        self._setup_ui(text)

    def _setup_ui(self, text: str):
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setText("")
        self.setMinimumHeight(44)
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        self.label = QLabel(text, self)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.label.setFont(get_unified_font(10))
        self.label.setStyleSheet("color: #f4f7fb; background: transparent;")
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        layout.addWidget(self.label)

        self.hint_label = QLabel("点击选择", self)
        self.hint_label.setFont(get_unified_font(9))
        self.hint_label.setStyleSheet("color: #7dd3fc; background: transparent;")
        self.hint_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.hint_label, 0, Qt.AlignRight | Qt.AlignVCenter)

        self._apply_state_style()

    def text(self):
        return self.label.text()

    def _apply_state_style(self):
        border = "#607089"
        background = "rgba(255, 255, 255, 0.05)"
        text_color = "#f4f7fb"
        hint_color = "#7dd3fc"
        if self._selected:
            border = "#38bdf8"
            background = "rgba(14, 165, 233, 0.20)"
            text_color = "#ffffff"
        self.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {background};
                border: 1px solid #607089;
                border-radius: 8px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: rgba(125, 211, 252, 0.12);
                border: 1px solid #7dd3fc;
            }}
            QPushButton:pressed {{
                background-color: rgba(14, 165, 233, 0.20);
                border: 1px solid #38bdf8;
            }}
            """
        )
        self.label.setStyleSheet(f"color: {text_color}; background: transparent;")
        self.hint_label.setStyleSheet(
            f"color: {hint_color}; background: transparent; font-size: 9pt;"
        )

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_state_style()


class WrappedCheckOption(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._hovered = False
        self._setup_ui(text)

    def _setup_ui(self, text: str):
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        self.checkbox = QCheckBox("", self)
        self.checkbox.setCursor(Qt.PointingHandCursor)
        self.checkbox.setStyleSheet(
            """
            QCheckBox {
                background: transparent;
                border: none;
                padding: 0;
                margin: 0;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #72839c;
                background-color: #141922;
            }
            QCheckBox::indicator:checked {
                background-color: #0ea5e9;
                border-color: #0ea5e9;
            }
            """
        )

        self.label = QLabel(text, self)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.label.setFont(get_unified_font(10))
        self.label.setStyleSheet("color: #f4f7fb; background: transparent;")
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        layout.addWidget(self.checkbox, 0, Qt.AlignTop)
        layout.addWidget(self.label, 1)

        self.checkbox.toggled.connect(self.toggled.emit)
        self.checkbox.toggled.connect(lambda _checked: self._apply_state_style())
        self._apply_state_style()

    def text(self):
        return self.label.text()

    def isChecked(self):
        return self.checkbox.isChecked()

    def setChecked(self, checked: bool):
        self.checkbox.setChecked(checked)

    def _apply_state_style(self):
        border = "#425067"
        background = "rgba(255, 255, 255, 0.04)"
        if self._hovered:
            border = "#5a6c88"
            background = "rgba(125, 211, 252, 0.08)"
        if self.checkbox.isChecked():
            border = "#38bdf8"
            background = "rgba(14, 165, 233, 0.12)"
        self.setStyleSheet(
            f"""
            WrappedCheckOption {{
                background-color: {background};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            """
        )

    def enterEvent(self, event):
        self._hovered = True
        self._apply_state_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._apply_state_style()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.checkbox.toggle()
        super().mousePressEvent(event)


class QuestionFloatingWidget(CardWidget):
    """悬浮提问卡片，支持单选、多选和切换为文本输入。"""

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
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.setMaximumHeight(420)
        self.setMinimumHeight(128)
        self.setStyleSheet(
            """
            CardWidget {
                background-color: rgba(33, 33, 38, 248);
                border: 1px solid #3b4758;
                border-radius: 8px;
            }
            """
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 14)
        main_layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)

        self.icon_label = QLabel("?", self)
        self.icon_label.setFont(get_unified_font(14, True))
        self.icon_label.setStyleSheet("color: #7dd3fc;")

        self.title_label = QLabel("等待你的选择", self)
        self.title_label.setFont(get_unified_font(11, True))
        self.title_label.setStyleSheet("color: #e6edf7;")

        self.mode_hint_label = QLabel("", self)
        self.mode_hint_label.setFont(get_unified_font(9))
        self.mode_hint_label.setStyleSheet(
            """
            color: #7dd3fc;
            background-color: rgba(125, 211, 252, 0.12);
            border: 1px solid rgba(125, 211, 252, 0.24);
            border-radius: 10px;
            padding: 2px 8px;
            """
        )
        self.mode_hint_label.setVisible(False)

        header.addWidget(self.icon_label)
        header.addWidget(self.title_label)
        header.addWidget(self.mode_hint_label)
        header.addStretch()

        self.close_btn = QPushButton("x", self)
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                color: #8b95a7;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #f4f7fb;
                background-color: rgba(255, 255, 255, 0.08);
            }
            """
        )
        self.close_btn.clicked.connect(self._on_cancel)
        header.addWidget(self.close_btn)

        self.question_label = QLabel("", self)
        self.question_label.setFont(get_unified_font(10))
        self.question_label.setStyleSheet("color: #c8d1dd;")
        self.question_label.setWordWrap(True)
        self.question_label.setMinimumHeight(28)

        self.options_container = QWidget(self)
        self.options_layout = QGridLayout(self.options_container)
        self.options_layout.setContentsMargins(0, 0, 0, 0)
        self.options_layout.setHorizontalSpacing(10)
        self.options_layout.setVerticalSpacing(10)

        self.custom_entry_bar = QHBoxLayout()
        self.custom_entry_bar.setSpacing(8)

        self.custom_hint_label = QLabel("没有合适的选项？", self)
        self.custom_hint_label.setFont(get_unified_font(9))
        self.custom_hint_label.setStyleSheet("color: #8b95a7;")

        self.toggle_text_mode_btn = QPushButton("改为输入", self)
        self.toggle_text_mode_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_text_mode_btn.setStyleSheet(
            """
            QPushButton {
                color: #7dd3fc;
                background-color: rgba(125, 211, 252, 0.08);
                border: 1px solid rgba(125, 211, 252, 0.22);
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(125, 211, 252, 0.16);
                border-color: rgba(125, 211, 252, 0.36);
            }
            """
        )
        self.toggle_text_mode_btn.clicked.connect(self._toggle_text_mode)

        self.custom_entry_bar.addWidget(self.custom_hint_label)
        self.custom_entry_bar.addStretch()
        self.custom_entry_bar.addWidget(self.toggle_text_mode_btn)

        self.text_input = QTextEdit(self)
        self.text_input.setPlaceholderText("输入你想补充的内容")
        self.text_input.setFont(get_unified_font(10))
        self.text_input.setMaximumHeight(104)
        self.text_input.setVisible(False)
        self.text_input.textChanged.connect(self._update_submit_state)
        self.text_input.setStyleSheet(
            """
            QTextEdit {
                background-color: rgba(18, 23, 31, 0.96);
                color: #f4f7fb;
                border: 1px solid #41516a;
                border-radius: 8px;
                padding: 10px 12px;
                selection-background-color: #2563eb;
            }
            QTextEdit:focus {
                border-color: #7dd3fc;
            }
            """
        )

        self.footer_layout = QHBoxLayout()
        self.footer_layout.setSpacing(8)

        self.selection_hint_label = QLabel("", self)
        self.selection_hint_label.setFont(get_unified_font(9))
        self.selection_hint_label.setStyleSheet("color: #8b95a7;")

        self.confirm_btn = PrimaryPushButton("提交", self)
        self.confirm_btn.setCursor(Qt.PointingHandCursor)
        self.confirm_btn.clicked.connect(self._on_confirm)
        self.confirm_btn.setStyleSheet(
            """
            PrimaryPushButton {
                background-color: #0f766e;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 7px 18px;
                font-size: 11px;
                font-weight: bold;
            }
            PrimaryPushButton:hover {
                background-color: #0d9488;
            }
            PrimaryPushButton:disabled {
                background-color: #3f4b5f;
                color: #93a0b4;
            }
            """
        )

        self.footer_layout.addWidget(self.selection_hint_label)
        self.footer_layout.addStretch()
        self.footer_layout.addWidget(self.confirm_btn)

        main_layout.addLayout(header)
        main_layout.addWidget(self.question_label)
        main_layout.addWidget(self.options_container)
        main_layout.addLayout(self.custom_entry_bar)
        main_layout.addWidget(self.text_input)
        main_layout.addLayout(self.footer_layout)

        self._update_mode_ui()

    def _clear_options(self):
        self._option_widgets = []
        while self.options_layout.count():
            item = self.options_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _option_label(self, option):
        if isinstance(option, dict):
            return option.get("label", str(option))
        return str(option)

    def _selected_options(self):
        return [
            widget.text()
            for widget in self._option_widgets
            if isinstance(widget, WrappedCheckOption) and widget.isChecked()
        ]

    def _has_text_input(self):
        return bool(self.text_input.toPlainText().strip())

    def _build_answer(self):
        text = self.text_input.toPlainText().strip()

        if self._multiple:
            selected = self._selected_options()
            if selected and text:
                return f"已选：{'、'.join(selected)}；补充：{text}"
            if selected:
                return "、".join(selected)
            return text

        return text

    def _update_mode_ui(self):
        has_options = bool(self._options)
        text_visible = self._text_input_mode or not has_options

        self.options_container.setVisible(has_options)
        self.custom_hint_label.setVisible(has_options)
        self.toggle_text_mode_btn.setVisible(has_options)
        self.text_input.setVisible(text_visible)

        if not has_options:
            self.mode_hint_label.setVisible(True)
            self.mode_hint_label.setText("文本输入")
            self.selection_hint_label.setText("直接输入回答")
            self.toggle_text_mode_btn.setText("改为输入")
        elif self._multiple:
            self.mode_hint_label.setVisible(True)
            self.mode_hint_label.setText("多选")
            if text_visible:
                self.selection_hint_label.setText("可多选，也可补充说明")
                self.toggle_text_mode_btn.setText("收起输入")
            else:
                self.selection_hint_label.setText("可多选，必要时再补充说明")
                self.toggle_text_mode_btn.setText("改为输入")
        else:
            self.mode_hint_label.setVisible(True)
            self.mode_hint_label.setText("单选")
            if text_visible:
                self.selection_hint_label.setText("文本输入会替代选项选择")
                self.toggle_text_mode_btn.setText("返回选项")
            else:
                self.selection_hint_label.setText("点击选项可直接提交")
                self.toggle_text_mode_btn.setText("改为输入")

        self._update_submit_state()

    def _update_submit_state(self):
        if not self._options:
            self.confirm_btn.setVisible(True)
            self.confirm_btn.setEnabled(self._has_text_input())
            self.confirm_btn.setText("提交")
            return

        if self._multiple:
            selected_count = len(self._selected_options())
            has_text = self._has_text_input()
            self.confirm_btn.setVisible(True)
            self.confirm_btn.setEnabled(selected_count > 0 or has_text)
            if selected_count > 0:
                self.confirm_btn.setText(f"提交 ({selected_count})")
            else:
                self.confirm_btn.setText("提交")
            return

        if self._text_input_mode:
            self.confirm_btn.setVisible(True)
            self.confirm_btn.setEnabled(self._has_text_input())
            self.confirm_btn.setText("提交")
        else:
            self.confirm_btn.setVisible(False)

    def _toggle_text_mode(self):
        if not self._options:
            return

        self._text_input_mode = not self._text_input_mode
        if self._text_input_mode:
            self.text_input.setFocus()
        else:
            self.text_input.clear()
        self._update_mode_ui()

    def _on_cancel(self):
        self.setVisible(False)
        self.cancelled.emit()

    def _on_confirm(self):
        answer = self._build_answer()
        if not answer:
            return
        self.setVisible(False)
        self.answered.emit(answer)

    def _on_select(self, option):
        answer = self._option_label(option)
        if self._text_input_mode:
            return
        sender = self.sender()
        if isinstance(sender, WrappedOptionButton):
            sender.set_selected(True)
        self._emit_single_answer(str(answer))

    def _emit_single_answer(self, answer: str):
        self.setVisible(False)
        self.answered.emit(answer)

    def _on_checkbox_toggled(self, _checked):
        self._update_submit_state()

    def _create_checkbox(self, option):
        checkbox = WrappedCheckOption(self._option_label(option), self)
        checkbox.toggled.connect(self._on_checkbox_toggled)
        return checkbox

    def _create_button(self, option):
        btn = WrappedOptionButton(self._option_label(option), self)
        btn.clicked.connect(partial(self._on_select, option))
        return btn

    def show_question(self, question: str, options: list, multiple: bool = False):
        self._question = question or ""
        self._options = options if isinstance(options, list) else []
        self._multiple = bool(multiple)
        self._text_input_mode = not self._options

        self.question_label.setText(self._question)
        self.text_input.clear()
        self._clear_options()

        if self._options:
            columns = 2 if len(self._options) > 2 else max(1, len(self._options))
            for index, option in enumerate(self._options):
                row = index // columns
                col = index % columns
                widget = (
                    self._create_checkbox(option)
                    if self._multiple
                    else self._create_button(option)
                )
                self.options_layout.addWidget(widget, row, col)
                self._option_widgets.append(widget)

        self._update_mode_ui()
        self.setVisible(True)
        self.raise_()

    def clear(self):
        self._question = ""
        self._options = []
        self._multiple = False
        self._text_input_mode = False
        self.text_input.clear()
        self._clear_options()
        self.setVisible(False)
