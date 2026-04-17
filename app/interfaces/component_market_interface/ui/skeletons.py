# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtGui import QColor, QPainter, QLinearGradient


class SkeletonWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(16)
        self._highlight_color = QColor(60, 60, 60)
        self._base_color = QColor(35, 35, 35)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), self._base_color)


class SkeletonCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(320)
        self.setFixedHeight(200)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(12)

        self.icon_skel = SkeletonWidget()
        self.icon_skel.setFixedSize(40, 40)
        header.addWidget(self.icon_skel)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        title_skel = SkeletonWidget()
        title_skel.setFixedHeight(16)
        title_box.addWidget(title_skel)

        uuid_skel = SkeletonWidget()
        uuid_skel.setFixedHeight(10)
        title_box.addWidget(uuid_skel)

        header.addLayout(title_box)
        header.addStretch()

        badge_skel = SkeletonWidget()
        badge_skel.setFixedSize(50, 20)
        header.addWidget(badge_skel)

        checkbox_skel = SkeletonWidget()
        checkbox_skel.setFixedSize(18, 18)
        header.addWidget(checkbox_skel)

        layout.addLayout(header)

        desc_skel = SkeletonWidget()
        desc_skel.setFixedHeight(40)
        layout.addWidget(desc_skel)

        meta_skel = SkeletonWidget()
        meta_skel.setFixedHeight(14)
        layout.addWidget(meta_skel)

        footer = QHBoxLayout()
        footer.setSpacing(8)

        for _ in range(2):
            tag_skel = SkeletonWidget()
            tag_skel.setFixedSize(60, 24)
            footer.addWidget(tag_skel)

        footer.addStretch()

        btn_skel = SkeletonWidget()
        btn_skel.setFixedSize(80, 32)
        footer.addWidget(btn_skel)

        layout.addLayout(footer)


class SkeletonGrid(QWidget):
    def __init__(self, count=8, parent=None):
        super().__init__(parent)
        self._count = count
        self._setup_ui()

    def _setup_ui(self):
        from PyQt5.QtWidgets import QGridLayout

        layout = QGridLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 0, 0)

        self._skeletons = []
        for i in range(self._count):
            skel = SkeletonCard()
            self._skeletons.append(skel)
            layout.addWidget(skel, i // 2, i % 2)

    def set_visible(self, visible):
        for skel in self._skeletons:
            skel.setVisible(visible)
