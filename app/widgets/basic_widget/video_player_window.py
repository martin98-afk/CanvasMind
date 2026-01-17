# -*- coding: utf-8 -*-
import os
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import QUrl, Qt

try:
    from qfluentwidgets.multimedia import VideoWidget
except ImportError:
    # 兼容性处理
    from PyQt5.QtMultimediaWidgets import QVideoWidget as VideoWidget


class VideoPlayerWindow(QtWidgets.QWidget):
    """
    单例模式的视频播放窗口。
    通过复用同一个窗口实例，消除 90% 的初始化加载延迟。
    """
    _instance = None  # 用于存储单例实例

    @classmethod
    def get_instance(cls):
        """获取全局唯一的播放器实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        # 只有第一次创建时会运行这里，后续都是直接调用 play_file
        self.setWindowTitle("视频预览")
        self.resize(900, 600)  # 稍微大一点

        # 1. 关键优化：设置为由窗口管理器托管，但关闭时只是隐藏
        # 不要设置 WA_DeleteOnClose，否则关掉后再打开又要重新初始化，很慢
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setWindowFlags(Qt.Window)

        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)  # 去掉边距，沉浸式

        # 2. 初始化播放器控件
        self.videoWidget = VideoWidget(self)
        self.layout.addWidget(self.videoWidget)

        # 3. 样式优化（黑色背景防闪烁）
        self.setStyleSheet("background-color: black;")

    def play_file(self, file_path):
        """极致流畅的播放入口"""
        if not os.path.exists(file_path):
            return

        url = QUrl.fromLocalFile(file_path)

        # 1. 先显示窗口（利用人的视觉暂留，觉得响应很快）
        # 这里的 show 不会阻塞，因为窗口实例早就创建好了
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()  # 提到最前
        self.activateWindow()

        # 2. 播放逻辑优化
        # 如果当前正在播放其他视频，先暂停
        self.videoWidget.pause()

        # 设置新源并立即播放
        self.videoWidget.setVideo(url)
        self.videoWidget.play()

    def closeEvent(self, event):
        """重写关闭事件：不销毁，只暂停并隐藏"""
        self.videoWidget.pause()  # 暂停即可，不需要 stop (stop会释放某些资源，下次加载慢)
        self.hide()
        event.ignore()  # 忽略系统的关闭信号，防止窗口被销毁