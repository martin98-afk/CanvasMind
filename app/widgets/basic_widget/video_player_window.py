# -*- coding: utf-8 -*-
import os

from PyQt5 import QtWidgets
from PyQt5.QtCore import QUrl, Qt

# 确保正确导入
try:
    from qfluentwidgets.multimedia import VideoWidget, SimpleMediaPlayBar
    from qfluentwidgets import PushButton, FluentIcon as FIF
except ImportError:
    from qfluentwidgets import VideoWidget, SimpleMediaPlayBar, PushButton


# 1. 弹出式的视频播放窗口
class VideoPlayerWindow(QtWidgets.QWidget):
    """独立的视频播放窗口，避开 GraphicsView 的渲染限制"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("视频预览")
        self.resize(800, 500)

        # 设置窗口置顶或独立显示
        self.setWindowFlags(Qt.Window)

        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)

        # 使用 qfluentwidgets 的 VideoWidget
        self.videoWidget = VideoWidget(self)
        self.layout.addWidget(self.videoWidget)

    def play_file(self, file_path):
        if os.path.exists(file_path):
            self.show()
            self.activateWindow()  # 唤醒窗口到最前
            self.videoWidget.setVideo(QUrl.fromLocalFile(file_path))
            self.videoWidget.play()

    def closeEvent(self, event):
        self.videoWidget.stop()
        super().closeEvent(event)
