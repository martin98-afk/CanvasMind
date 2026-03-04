# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QGridLayout,
    QScrollArea,
    QCheckBox,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from qfluentwidgets import CardWidget, PrimaryPushButton


class QuestionFloatingWidget(CardWidget):
    """Question 悬浮框组件 - 让用户选择答案"""

    answered = pyqtSignal(str)  # 用户选择答案后发射信号（多选时用逗号分隔）
    cancelled = pyqtSignal()  # 用户取消选择

    def __init__(self, parent=None):
        super().__init__(parent)
        self._question = ""
        self._options = []
        self._multiple = False
        self._setup_ui()

    def _setup_ui(self):
        self.setSizePolicy(1, 0)
        self.setMaximumHeight(350)
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
        self.question_label.setStyleSheet("color: #e0e0e0;")
        self.question_label.setWordWrap(True)
        self.question_label.setMaximumHeight(60)

        # 滚动区域（选项太多时滚动）
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background: #2a2a2a;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #505050;
                border-radius: 3px;
                min-height: 30px;
            }
        """)

        # 选项容器（使用 Grid 布局实现多行多列）
        self.options_container = QWidget()
        self.options_layout = QGridLayout(self.options_container)
        self.options_layout.setSpacing(8)
        self.options_layout.setContentsMargins(0, 0, 0, 0)

        scroll.setWidget(self.options_container)

        # 底部按钮区域
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
        main_layout.addWidget(scroll, 1)
        main_layout.addLayout(self.button_area)

    def _on_cancel(self):
        self.setVisible(False)
        self.cancelled.emit()

    def _on_confirm(self):
        """确认选择（多选模式）"""
        selected = []
        for i in range(self.options_layout.count()):
            widget = self.options_layout.itemAt(i).widget()
            if isinstance(widget, QCheckBox) and widget.isChecked():
                selected.append(widget.text())

        result = ", ".join(selected)
        self.setVisible(False)
        self.answered.emit(result)

    def _on_select(self, option):
        """单选模式"""
        self.setVisible(False)
        if isinstance(option, dict):
            option = option.get("label", str(option))
        self.answered.emit(str(option))

    def _on_checkbox_toggled(self, checked):
        """复选框状态改变"""
        if self._multiple:
            # 更新确认按钮显示
            selected_count = sum(
                1
                for i in range(self.options_layout.count())
                if isinstance(self.options_layout.itemAt(i).widget(), QCheckBox)
                and self.options_layout.itemAt(i).widget().isChecked()
            )
            self.confirm_btn.setVisible(selected_count > 0)
            if selected_count > 0:
                self.confirm_btn.setText(f"确认 ({selected_count})")

    def show_question(self, question: str, options: list, multiple: bool = False):
        """显示问题让用户选择"""
        self._question = question
        self._options = options
        self._multiple = multiple

        self.question_label.setText(question)
        self.setVisible(True)
        self.confirm_btn.setVisible(False)
        self.confirm_btn.setText("确认")

        # 清除旧控件
        while self.options_layout.count():
            item = self.options_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not options:
            return

        # 计算列数（根据选项数量动态调整）
        total = len(options)
        if total <= 3:
            cols = total
        elif total <= 6:
            cols = 3
        else:
            cols = 2

        if multiple:
            # 多选模式：使用复选框
            for i, option in enumerate(options):
                text = (
                    option.get("label", option)
                    if isinstance(option, dict)
                    else str(option)
                )
                checkbox = QCheckBox(text, self)
                checkbox.setCursor(Qt.PointingHandCursor)
                checkbox.setStyleSheet("""
                    QCheckBox {
                        color: #ffffff;
                        spacing: 8px;
                        padding: 8px;
                        background-color: #3a3a3a;
                        border: 1px solid #505050;
                        border-radius: 4px;
                    }
                    QCheckBox:hover {
                        background-color: #4a4a4a;
                        border-color: #606060;
                    }
                    QCheckBox::indicator {
                        width: 16px;
                        height: 16px;
                        border-radius: 3px;
                        border: 1px solid #606060;
                        background-color: #2a2a2a;
                    }
                    QCheckBox::indicator:checked {
                        background-color: #0078d4;
                        border-color: #0078d4;
                    }
                """)
                checkbox.setMinimumHeight(40)
                checkbox.stateChanged.connect(self._on_checkbox_toggled)

                row = i // cols
                col = i % cols
                self.options_layout.addWidget(checkbox, row, col)
        else:
            # 单选模式：使用按钮
            for i, option in enumerate(options):
                btn_text = (
                    option.get("label", option)
                    if isinstance(option, dict)
                    else str(option)
                )
                btn = QPushButton(btn_text, self)
                btn.setCursor(Qt.PointingHandCursor)

                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #3a3a3a;
                        color: #ffffff;
                        border: 1px solid #505050;
                        border-radius: 6px;
                        padding: 10px 12px;
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

                btn.setMinimumHeight(40)
                btn.setSizePolicy(1, 0)

                btn.clicked.connect(lambda checked, opt=option: self._on_select(opt))

                row = i // cols
                col = i % cols
                self.options_layout.addWidget(btn, row, col)

        # 调整容器大小
        rows = (total + cols - 1) // cols
        self.options_container.setMinimumHeight(rows * 50)

    def clear(self):
        """隐藏控件"""
        self._question = ""
        self._options = []
        self._multiple = False
        self.setVisible(False)
