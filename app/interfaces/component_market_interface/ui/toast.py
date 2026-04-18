# -*- coding: utf-8 -*-
from enum import Enum
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QPropertyAnimation, QRect, QSize
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QApplication
from qfluentwidgets import FluentIcon as FIF


class ToastType(Enum):
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    INFO = "info"
    PROGRESS = "progress"


class ToastWidget(QWidget):
    closed = pyqtSignal()

    def __init__(self, message, toast_type=ToastType.INFO, duration=3000, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedHeight(56)
        self._toast_type = toast_type
        self._duration = duration
        self._progress_value = 100

        self._setup_ui(message)
        self._setup_animation()
        self._start_timer()

    def _setup_ui(self, message):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)

        colors = {
            ToastType.SUCCESS: ("#22c55e", "#dcfce7"),
            ToastType.WARNING: ("#f59e0b", "#fef3c7"),
            ToastType.ERROR: ("#ef4444", "#fee2e2"),
            ToastType.INFO: ("#3b82f6", "#dbeafe"),
            ToastType.PROGRESS: ("#3b82f6", "#dbeafe"),
        }
        border_color, bg_color = colors.get(self._toast_type, colors[ToastType.INFO])

        self._icon_label = QLabel()
        icons = {
            ToastType.SUCCESS: FIF.ACCEPT,
            ToastType.WARNING: FIF.WARNING,
            ToastType.ERROR: FIF.CANCEL,
            ToastType.INFO: FIF.INFO,
            ToastType.PROGRESS: FIF.SYNC,
        }
        self._icon_label.setText(
            f'<img src="{icons.get(self._toast_type, FIF.INFO).path}" width="20" height="20"/>'
        )
        self._icon_label.setFixedWidth(24)
        layout.addWidget(self._icon_label)

        self._message_label = QLabel(message)
        self._message_label.setStyleSheet(
            f"color: {border_color}; font-size: 14px; font-weight: 500;"
        )
        layout.addWidget(self._message_label, 1)

        if self._toast_type == ToastType.PROGRESS:
            self._progress_label = QLabel("0%")
            self._progress_label.setStyleSheet(
                "color: #6b7280; font-size: 12px; min-width: 40px;"
            )
            layout.addWidget(self._progress_label)

        self._close_btn = QPushButton("×")
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setStyleSheet(
            f"background: transparent; color: {border_color}; border: none; font-size: 18px; font-weight: bold;"
            f"QPushButton:hover {{ background: rgba(0,0,0,0.05); border-radius: 4px; }}"
        )
        self._close_btn.clicked.connect(self._animate_out)
        layout.addWidget(self._close_btn)

        self._container = QWidget(self)
        self._container.setStyleSheet(
            f"background: {bg_color}; border: 1px solid {border_color}; "
            f"border-radius: 8px; margin: 4px;"
        )
        self._container.setLayout(layout)

    def _setup_animation(self):
        screen = QApplication.primaryScreen().geometry()
        self._start_pos = screen.bottomCenter() + QPoint(0, 100)
        self._end_pos = screen.bottomCenter() + QPoint(0, -self.height() - 20)

        self._anim = QPropertyAnimation(self, b"pos")
        self._anim.setDuration(300)
        self._anim.setEasingCurve(1)
        self._anim.valueChanged.connect(self._update_geometry)

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(200)

    def _update_geometry(self):
        pass

    def _start_timer(self):
        if self._toast_type == ToastType.PROGRESS:
            return
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate_out)
        self._timer.setSingleShot(True)
        self._timer.start(self._duration)

    def _animate_out(self):
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(self._end_pos)
        self._anim.start()
        self._fade_anim.setStartValue(1)
        self._fade_anim.setEndValue(0)
        self._fade_anim.start()
        QTimer.singleShot(300, self.close)
        QTimer.singleShot(300, self.closed)

    def show(self):
        screen = QApplication.primaryScreen().geometry()
        x = screen.width() // 2 - self.width() // 2
        y = screen.height() - self.height() - 40
        self.move(x, y)
        super().show()
        self._anim.setStartValue(self.pos() + QPoint(0, 50))
        self._anim.setEndValue(self.pos())
        self._anim.start()

    def set_progress(self, value, message=""):
        if self._toast_type == ToastType.PROGRESS and hasattr(self, "_progress_label"):
            self._progress_label.setText(f"{value}%")
            if message:
                self._message_label.setText(message)


class ToastManager:
    _instance = None

    def __init__(self):
        self._toasts = []

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = ToastManager()
        return cls._instance

    def show(self, message, toast_type=ToastType.INFO, duration=3000):
        toast = ToastWidget(message, toast_type, duration)
        toast.closed.connect(lambda: self._remove(toast))
        toast.show()
        self._toasts.append(toast)
        return toast

    def success(self, message, duration=2000):
        return self.show(message, ToastType.SUCCESS, duration)

    def warning(self, message, duration=3000):
        return self.show(message, ToastType.WARNING, duration)

    def error(self, message, duration=4000):
        return self.show(message, ToastType.ERROR, duration)

    def info(self, message, duration=3000):
        return self.show(message, ToastType.INFO, duration)

    def progress(self, message="处理中..."):
        return self.show(message, ToastType.PROGRESS, 0)

    def _remove(self, toast):
        if toast in self._toasts:
            self._toasts.remove(toast)


toast = ToastManager.instance
