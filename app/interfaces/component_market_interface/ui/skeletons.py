# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, pyqtProperty
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtGui import QPainter, QLinearGradient, QColor


class SkeletonWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._shimmer_pos = -1.0
        self.setMinimumHeight(180)
        self.setContentsMargins(16, 16, 16, 16)

        self._anim = QPropertyAnimation(self, b"shimmerPos")
        self._anim.setDuration(1500)
        self._anim.setStartValue(-1.0)
        self._anim.setEndValue(2.0)
        self._anim.setLoopCount(-1)
        self._anim.start()

    def getShimmerPos(self):
        return self._shimmer_pos

    def setShimmerPos(self, value):
        self._shimmer_pos = value
        self.update()

    shimmerPos = pyqtProperty(float, getShimmerPos, setShimmerPos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        base_color = QColor(45, 45, 45)
        shimmer_color = QColor(70, 70, 70)

        painter.fillRect(self.rect(), base_color)

        if self._shimmer_pos < 0 or self._shimmer_pos > 1:
            return

        shimmer_rect = self.rect().adjusted(
            int(self.width() * self._shimmer_pos) - 50, 0, 0, 0
        )
        gradient = QLinearGradient(shimmer_rect.topLeft(), shimmer_rect.topRight())
        gradient.setColorAt(0, base_color)
        gradient.setColorAt(0.5, shimmer_color)
        gradient.setColorAt(1, base_color)
        painter.fillRect(shimmer_rect, gradient)


class SkeletonCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(320)
        self.setFixedHeight(200)
        self.setContentsMargins(0, 0, 0, 0)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(12)

        self.icon_skel = SkeletonWidget()
        self.icon_skel.setFixedSize(40, 40)
        self.icon_skel.setStyleSheet("border-radius: 8px;")
        header.addWidget(self.icon_skel)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        title_skel = SkeletonWidget()
        title_skel.setFixedHeight(16)
        title_skel.setStyleSheet("border-radius: 4px;")
        title_box.addWidget(title_skel)

        uuid_skel = SkeletonWidget()
        uuid_skel.setFixedHeight(10)
        uuid_skel.setStyleSheet("border-radius: 4px;")
        title_box.addWidget(uuid_skel)

        header.addLayout(title_box)
        header.addStretch()

        badge_skel = SkeletonWidget()
        badge_skel.setFixedSize(50, 20)
        badge_skel.setStyleSheet("border-radius: 4px;")
        header.addWidget(badge_skel)

        checkbox_skel = SkeletonWidget()
        checkbox_skel.setFixedSize(18, 18)
        checkbox_skel.setStyleSheet("border-radius: 4px;")
        header.addWidget(checkbox_skel)

        layout.addLayout(header)

        desc_skel = SkeletonWidget()
        desc_skel.setFixedHeight(40)
        desc_skel.setStyleSheet("border-radius: 4px;")
        layout.addWidget(desc_skel)

        meta_skel = SkeletonWidget()
        meta_skel.setFixedHeight(14)
        meta_skel.setStyleSheet("border-radius: 4px;")
        layout.addWidget(meta_skel)

        footer = QHBoxLayout()
        footer.setSpacing(8)

        for _ in range(2):
            tag_skel = SkeletonWidget()
            tag_skel.setFixedSize(60, 24)
            tag_skel.setStyleSheet("border-radius: 4px;")
            footer.addWidget(tag_skel)

        footer.addStretch()

        btn_skel = SkeletonWidget()
        btn_skel.setFixedSize(80, 32)
        btn_skel.setStyleSheet("border-radius: 6px;")
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
