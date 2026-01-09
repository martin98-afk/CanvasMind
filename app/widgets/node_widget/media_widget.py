# -*- coding: utf-8 -*-
import os

from PyQt5.QtCore import QSize, QUrl
from Qt import QtWidgets, QtCore
from qfluentwidgets import PushButton, FluentIcon
from qfluentwidgets.multimedia import SimpleMediaPlayBar

from app.widgets.basic_widget.video_player_window import VideoPlayerWindow


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
        self.playBar.setFixedSize(220, 180)
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

        self.updateGeometry()
        # 关键：通知 NodeGraphQt 节点尺寸已变化，需要重绘
        self.sizeHintChanged.emit()
        self.valueChanged.emit(file_path)

    def play(self):
        self.playBar.play()

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
        self.parent = parent
        self._file_path = None
        # 用于保存弹出窗口的引用，防止被垃圾回收
        self._player_window = None

        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)

        # 改成一个美观的按钮
        self.play_btn = PushButton(FluentIcon.PLAY, "点击播放视频", self)
        self.play_btn.clicked.connect(self.play)
        self.play_btn.hide()
        self.main_layout.addWidget(self.play_btn)

        # 初始状态
        self.play_btn.setEnabled(False)

    def play(self):
        if not self._file_path:
            return

        # 实例化或显示窗口
        if not self._player_window:
            self._player_window = VideoPlayerWindow()

        self._player_window.play_file(self._file_path)

    def set_value(self, file_path):
        self._file_path = file_path
        if file_path and os.path.exists(file_path):
            self.play_btn.show()
            self.play_btn.setEnabled(True)
            self.play_btn.setText(f"播放: {os.path.basename(file_path)}")
        else:
            self.play_btn.setEnabled(False)
            self.play_btn.setText("无视频文件")

        self.valueChanged.emit(file_path)

    def get_value(self):
        return self._file_path

    def sizeHint(self):
        # 节点内只需要一个按钮的大小
        return QSize(100, 45)

    def stop(self):
        if self._player_window:
            self._player_window.close()