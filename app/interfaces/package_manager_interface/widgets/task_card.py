# -*- coding: utf-8 -*-

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout
from qfluentwidgets import (
    FluentIcon, SimpleCardWidget,
    TransparentToolButton, IconWidget, CaptionLabel
)
from qfluentwidgets import (StrongBodyLabel)


class TaskCardWidget(SimpleCardWidget):
    """
    任务卡片组件
    Task Card Widget
    """
    cancel_signal = pyqtSignal(str)

    def __init__(self, task_id, title, env_name, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self.setFixedHeight(80)

        # 背景透明，依靠 QListWidget 的样式处理选中态
        self.setStyleSheet("TaskCardWidget { background-color: transparent; border: none; }")

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(16, 10, 16, 10)

        self.icon_widget = IconWidget(FluentIcon.IOT, self)
        self.icon_widget.setFixedSize(32, 32)

        self.info_layout = QVBoxLayout()
        self.info_layout.setSpacing(2)
        self.title_label = StrongBodyLabel(title, self)

        self.sub_label = CaptionLabel(f"{self.tr('环境')}: {env_name}", self)
        self.sub_label.setTextColor(QColor(120, 120, 120), QColor(150, 150, 150))

        self.status_label = CaptionLabel(self.tr("等待中..."), self)
        self.status_label.setTextColor(QColor("#009faa"), QColor("#009faa"))

        self.info_layout.addWidget(self.title_label)
        self.info_layout.addWidget(self.sub_label)
        self.info_layout.addWidget(self.status_label)
        self.info_layout.setAlignment(Qt.AlignVCenter)

        self.cancel_btn = TransparentToolButton(FluentIcon.CLOSE, self)
        self.cancel_btn.setFixedSize(30, 30)
        self.cancel_btn.setToolTip(self.tr("取消任务"))
        self.cancel_btn.clicked.connect(self._on_cancel)

        self.layout.addWidget(self.icon_widget)
        self.layout.addLayout(self.info_layout)
        self.layout.addStretch(1)
        self.layout.addWidget(self.cancel_btn)

    def _on_cancel(self):
        self.cancel_signal.emit(self.task_id)

    def set_status(self, status_text, color_hex, finished=False):
        self.status_label.setText(status_text)
        self.status_label.setStyleSheet(f"color: {color_hex};")

        if finished:
            self.cancel_btn.setEnabled(False)
            if self.tr("失败") in status_text or self.tr("取消") in status_text or "Error" in status_text:
                self.cancel_btn.setIcon(FluentIcon.INFO)
            else:
                self.cancel_btn.setIcon(FluentIcon.COMPLETED)
