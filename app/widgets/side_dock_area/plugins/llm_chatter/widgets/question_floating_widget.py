# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from qfluentwidgets import CardWidget


class QuestionFloatingWidget(CardWidget):
    """Question 悬浮框组件 - 让用户选择答案"""

    answered = pyqtSignal(str)  # 用户选择答案后发射信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self._question = ""
        self._options = []
        self._setup_ui()

    def _setup_ui(self):
        self.setSizePolicy(1, 0)
        self.setStyleSheet("""
            CardWidget {
                background-color: rgba(30, 30, 30, 240);
                border: 1px solid #404040;
                border-radius: 6px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(6)

        # 标题栏
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

        # 问题内容
        self.question_label = QLabel("", self)
        self.question_label.setFont(QFont("Microsoft YaHei", 10))
        self.question_label.setStyleSheet("color: #ffffff;")
        self.question_label.setWordWrap(True)

        # 选项按钮容器
        self.options_widget = QWidget()
        self.options_layout = QHBoxLayout(self.options_widget)
        self.options_layout.setSpacing(8)
        self.options_layout.setContentsMargins(0, 0, 0, 0)

        main_layout.addLayout(header)
        main_layout.addWidget(self.question_label)
        main_layout.addWidget(self.options_widget, 1)

    def _on_cancel(self):
        self.setVisible(False)

    def _on_select(self, option):
        self.setVisible(False)
        if isinstance(option, dict):
            option = option.get("label", str(option))
        self.answered.emit(str(option))

    def show_question(self, question: str, options: list):
        """显示问题让用户选择"""
        self._question = question
        self._options = options

        self.question_label.setText(question)
        self.setVisible(True)

        # 清除旧按钮
        while self.options_layout.count():
            item = self.options_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 添加新按钮
        for option in options:
            btn_text = (
                option.get("label", option) if isinstance(option, dict) else str(option)
            )
            btn = QPushButton(btn_text, self)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #404040;
                    color: #ffffff;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-size: 10px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #505050;
                }
            """)
            btn.clicked.connect(lambda checked, opt=option: self._on_select(opt))
            self.options_layout.addWidget(btn)

        self.options_layout.addStretch()

    def clear(self):
        """隐藏控件"""
        self._question = ""
        self._options = []
        self.setVisible(False)
