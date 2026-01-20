# -*- coding: utf-8 -*-

from PyQt5.QtCore import Qt, QRectF, pyqtSignal
from PyQt5.QtGui import QPainter, QPainterPath, QLinearGradient, QColor, QBrush, QPixmap
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QLabel)
from qfluentwidgets import (
    FluentIcon, PrimaryPushButton, PushButton
)


class WelcomeBannerWidget(QWidget):
    """ 欢迎横幅 """
    newCanvasSignal = pyqtSignal()
    openCanvasSignal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(300)
        self.bannerPixmap = QPixmap(':/icons/banner.png')
        self.setStyleSheet("background-color: transparent;")

        self.vLayout = QVBoxLayout(self)
        self.vLayout.setContentsMargins(48, 48, 48, 36)
        self.vLayout.setSpacing(12)

        # 标题 - 极大字号
        self.titleLabel = QLabel(self.tr("CanvasMind"))
        self.titleLabel.setStyleSheet("""
            color: #FFFFFF;
            font-family: "Microsoft YaHei UI";
            font-size: 42px;
            font-weight: bold;
        """)

        # 副标题
        self.subtitleLabel = QLabel(self.tr("现代化的低代码可视化编程平台"))
        self.subtitleLabel.setStyleSheet("""
            color: rgba(255, 255, 255, 0.8);
            font-family: "Microsoft YaHei UI";
            font-size: 16px;
        """)

        # 按钮栏
        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.setSpacing(16)

        self.newButton = PrimaryPushButton(FluentIcon.ADD, self.tr("新建画布"))
        self.newButton.setFixedWidth(160)
        self.newButton.setFixedHeight(40)
        self.newButton.clicked.connect(self.newCanvasSignal.emit)

        self.openButton = PushButton(self.tr("打开画布"))
        self.openButton.setFixedWidth(160)
        self.openButton.setFixedHeight(40)
        self.openButton.clicked.connect(self._on_open_clicked)
        # 强制按钮深色样式适配
        self.openButton.setStyleSheet(
            "PushButton { color: white; background-color: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); } "
            "PushButton:hover { background-color: rgba(255,255,255,0.2); }"
        )

        self.buttonLayout.addWidget(self.newButton)
        self.buttonLayout.addWidget(self.openButton)
        self.buttonLayout.addStretch(1)

        self.vLayout.addWidget(self.titleLabel)
        self.vLayout.addWidget(self.subtitleLabel)
        self.vLayout.addSpacing(20)
        self.vLayout.addLayout(self.buttonLayout)
        self.vLayout.addStretch(1)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.SmoothPixmapTransform | QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        w, h = self.width(), self.height()
        rect = QRectF(0, 0, w, h)
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)

        painter.save()
        painter.setClipPath(path)

        if not self.bannerPixmap.isNull():
            scaledPixmap = self.bannerPixmap.scaled(
                self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            pix_x = (w - scaledPixmap.width()) / 2
            pix_y = (h - scaledPixmap.height()) / 2
            painter.drawPixmap(int(pix_x), int(pix_y), scaledPixmap)

        # 高级深色渐变蒙版
        gradient = QLinearGradient(0, 0, w, 0)
        gradient.setColorAt(0.0, QColor(18, 18, 18, 255))
        gradient.setColorAt(0.5, QColor(18, 18, 18, 220))
        gradient.setColorAt(1.0, QColor(18, 18, 18, 50))
        painter.fillPath(path, QBrush(gradient))
        painter.restore()

    def _on_open_clicked(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, self.tr("打开工作流文件"), "./", "CanvasMind Files (*.workflow.json);;All Files (*)"
        )
        if file_path:
            self.openCanvasSignal.emit(file_path)