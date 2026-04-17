# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGraphicsDropShadowEffect,
)
from PyQt5.QtGui import QColor
from qfluentwidgets import FluentIcon as FIF, PrimaryPushButton, PushButton


class BatchActionToolbar(QWidget):
    action_install = pyqtSignal()
    action_upload = pyqtSignal()
    action_cancel = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_visible = False
        self._selected_count = 0
        self._setup_ui()
        self._setup_animation()

    def _setup_ui(self):
        self.setFixedHeight(56)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._container = QWidget(self)
        self._container.setObjectName("BatchToolbarContainer")
        self._container.setStyleSheet("""
            #BatchToolbarContainer {
                background: #1a1a1a;
                border: 1px solid #30363d;
                border-radius: 12px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self._container)
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 4)
        self._container.setGraphicsEffect(shadow)

        layout = QHBoxLayout(self._container)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(16)

        self._info_label = QLabel("已选择 0 项")
        self._info_label.setStyleSheet(
            "color: #f0f6fc; font-size: 14px; font-weight: 500;"
        )
        layout.addWidget(self._info_label)

        layout.addStretch()

        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #8b949e;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #21262d;
                color: #f0f6fc;
            }
        """)
        self._cancel_btn.clicked.connect(self.hide)
        layout.addWidget(self._cancel_btn)

        self._install_btn = PrimaryPushButton(FIF.DOWNLOAD, "批量安装")
        self._install_btn.setFixedWidth(120)
        self._install_btn.clicked.connect(self.action_install.emit)
        layout.addWidget(self._install_btn)

        self._upload_btn = PushButton(FIF.UPLOAD, "批量上传")
        self._upload_btn.setFixedWidth(120)
        self._upload_btn.clicked.connect(self.action_upload.emit)
        layout.addWidget(self._upload_btn)

        container_layout = QHBoxLayout(self)
        container_layout.setContentsMargins(24, 0, 24, 16)
        container_layout.addWidget(self._container)

    def _setup_animation(self):
        self._slide_anim = QPropertyAnimation(self, b"geometry")
        self._slide_anim.setDuration(250)
        self._slide_anim.setEasingCurve(QEasingCurve.OutCubic)

    def set_mode(self, mode):
        if mode == "market":
            self._install_btn.setVisible(True)
            self._install_btn.setText("批量安装")
            self._install_btn.setIcon(FIF.DOWNLOAD)
            self._upload_btn.setVisible(False)
        elif mode == "installed":
            self._install_btn.setVisible(False)
            self._upload_btn.setVisible(True)
            self._upload_btn.setText("批量上传")
        else:
            self._install_btn.setVisible(False)
            self._upload_btn.setVisible(False)

    def set_selected_count(self, count):
        self._selected_count = count
        self._info_label.setText(f"已选择 {count} 项")
        if count > 0 and not self._is_visible:
            self.show()
        elif count == 0 and self._is_visible:
            self.hide()

    def show(self):
        if self._is_visible:
            return
        self._is_visible = True
        self._animate_in()

    def hide(self):
        if not self._is_visible:
            return
        self._is_visible = False
        self._animate_out()
        self.action_cancel.emit()

    def _animate_in(self):
        from PyQt5.QtWidgets import QApplication

        screen = QApplication.primaryScreen().geometry()
        start_rect = QRect(0, screen.height(), screen.width(), self.height())
        end_rect = QRect(
            0, screen.height() - self.height() - 60, screen.width(), self.height()
        )

        self._slide_anim.setStartValue(start_rect)
        self._slide_anim.setEndValue(end_rect)
        self._slide_anim.start()

    def _animate_out(self):
        from PyQt5.QtWidgets import QApplication

        screen = QApplication.primaryScreen().geometry()
        end_rect = QRect(0, screen.height(), screen.width(), self.height())

        self._slide_anim.setStartValue(self.geometry())
        self._slide_anim.setEndValue(end_rect)
        self._slide_anim.start()

    def setVisible(self, visible):
        if visible:
            self.show()
        else:
            self.hide()
