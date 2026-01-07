# -*- coding: utf-8 -*-
import os
from PyQt5.QtCore import QUrl, QSize, Qt
from Qt import QtWidgets, QtCore

# 确保正确导入
try:
    from qfluentwidgets.multimedia import VideoWidget, SimpleMediaPlayBar
except ImportError:
    from qfluentwidgets import VideoWidget, SimpleMediaPlayBar


class AudioPlayWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(object)
    sizeHintChanged = QtCore.Signal()
    EXTS = ['.mp3', '.wav', '.flac', '.m4a', '.ogg']

    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_path = None

        # 1. 关键修复：设置主布局并去掉外边距，防止在节点内偏移
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(2)

        # 2. 关键修复：将父对象设为 self，而不是外部传入的 parent
        # 播放控制条 (音频播放时使用)
        self.playBar = SimpleMediaPlayBar()
        self.playBar.setFixedSize(220, 200)
        # 将控件添加到布局
        self.main_layout.addWidget(self.playBar)

        # 初始状态
        self.playBar.hide()

    def set_value(self, file_path):
        """传入本地文件路径"""
        if self._file_path == file_path:
            return

        # 停止当前的播放（非常重要，防止切换时背景声音还在响）
        self.stop()

        self._file_path = file_path

        if not file_path or not os.path.exists(file_path):
            self.playBar.hide()
            self.updateGeometry()
            self.sizeHintChanged.emit()
            return

        ext = os.path.splitext(file_path)[1].lower()
        audio_exts = self.EXTS

        url = QUrl.fromLocalFile(file_path)

        if ext in audio_exts:
            # 音频模式：隐藏 VideoWidget，只显示控制条
            self.playBar.show()
            # 根据 qfluentwidgets 版本，通常访问内部播放器如下：
            self.playBar.player.setSource(url)
            self.playBar.play() # 可选：是否自动播放

        self.updateGeometry()
        # 关键：通知 NodeGraphQt 节点尺寸已变化，需要重绘
        self.sizeHintChanged.emit()
        self.valueChanged.emit(file_path)

    def stop(self):
        """停止所有播放器"""
        try:
            if hasattr(self.playBar, 'stop'):
                self.playBar.stop()
        except:
            pass

    def get_value(self):
        return self._file_path

    def sizeHint(self):
        # 根据当前显示的控件返回对应的尺寸
        if self._file_path:
            return QSize(100, 50)
        return QSize(200, 50)

    def closeEvent(self, event):
        self.stop()
        super().closeEvent(event)


class VideoPlayWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(object)
    sizeHintChanged = QtCore.Signal()
    EXTS = ['.mp4', '.avi', '.mkv', '.mov', '.wmv']

    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_path = None

        # 1. 关键修复：设置主布局并去掉外边距，防止在节点内偏移
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(2)
        # 2. 关键修复：将父对象设为 self，而不是外部传入的 parent
        # 视频渲染组件
        self.videoWidget = VideoWidget(self)
        # 将控件添加到布局
        self.main_layout.addWidget(self.videoWidget)
        # 初始状态
        self.videoWidget.hide()

    def set_value(self, file_path):
        """传入本地文件路径"""
        if self._file_path == file_path:
            return

        # 停止当前的播放（非常重要，防止切换时背景声音还在响）
        self.stop()

        self._file_path = file_path

        if not file_path or not os.path.exists(file_path):
            self.videoWidget.hide()
            self.updateGeometry()
            self.sizeHintChanged.emit()
            return

        ext = os.path.splitext(file_path)[1].lower()
        url = QUrl.fromLocalFile(file_path)

        if ext in self.EXTS:
            # 视频模式：显示 VideoWidget
            # 注意：qfluentwidgets 的 VideoWidget 自带了控制条
            self.videoWidget.show()
            self.videoWidget.setVideo(url)
            self.videoWidget.play() # 可选：是否自动播放

        self.updateGeometry()
        # 关键：通知 NodeGraphQt 节点尺寸已变化，需要重绘
        self.sizeHintChanged.emit()
        self.valueChanged.emit(file_path)

    def stop(self):
        """停止所有播放器"""
        try:
            if hasattr(self.videoWidget, 'stop'):
                self.videoWidget.stop()
        except:
            pass

    def get_value(self):
        return self._file_path

    def sizeHint(self):
        # 根据当前显示的控件返回对应的尺寸
        if self._file_path:
            return self.videoWidget.size()  # 视频宽度 300，总高度 240
        return QSize(200, 50)

    def closeEvent(self, event):
        self.stop()
        super().closeEvent(event)