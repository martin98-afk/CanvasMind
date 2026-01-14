# -*- coding: utf-8 -*-
import os

from PyQt5 import QtGui
from PyQt5 import QtWidgets
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import QUrl
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent, QAbstractVideoSurface, QVideoFrame, QAbstractVideoBuffer
from Qt import QtWidgets, QtCore
from qfluentwidgets.multimedia import SimpleMediaPlayBar


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


class CachedVideoSurface(QAbstractVideoSurface):
    """负责在第一遍播放时捕获并预缩放图片"""
    frameCaptured = QtCore.Signal(QtGui.QImage)

    def supportedPixelFormats(self, handleType):
        return [QVideoFrame.Format_RGB32, QVideoFrame.Format_ARGB32]

    def present(self, frame):
        if frame.isValid():
            clone_frame = QVideoFrame(frame)
            if clone_frame.map(QAbstractVideoBuffer.ReadOnly):
                try:
                    # 立即转换并拷贝，防止缓冲区被回收
                    image = clone_frame.image().copy()
                    if not image.isNull():
                        self.frameCaptured.emit(image)
                finally:
                    clone_frame.unmap()
            return True
        return False


class VideoPlayWidget(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_path = None
        self._fixed_size = QSize(280, 158)

        # --- 性能核心变量 ---
        self._frame_cache = []  # 存储 QPixmap 缓存
        self._is_caching = False  # 是否正在缓存第一轮
        self._current_frame_idx = 0
        self._fps_limit = 12  # 预览帧率，不需要太高
        self._max_cache_frames = 100  # 最大缓存帧数（防止长视频撑爆内存）

        self.setFixedSize(self._fixed_size)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("VideoPlayWidget")
        self.setStyleSheet("#VideoPlayWidget { background: #000; border-radius: 8px; }")

        # UI 布局
        self.img_label = QtWidgets.QLabel(self)
        self.img_label.setFixedSize(self._fixed_size)
        self.img_label.setScaledContents(True)

        # 播放器组件（仅用于第一轮采集）
        self.media_player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        self.surface = CachedVideoSurface()
        self.media_player.setVideoOutput(self.surface)
        self.media_player.setMuted(True)

        # 定时器：缓存完成后负责播放
        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self._update_next_frame)

        # 信号连接
        self.surface.frameCaptured.connect(self._on_frame_captured)
        self.media_player.mediaStatusChanged.connect(self._on_media_status_changed)

    def set_value(self, file_path):
        if self._file_path == file_path: return
        self._file_path = file_path

        # 清理旧缓存
        self.playback_timer.stop()
        self.media_player.stop()
        self._frame_cache.clear()
        self._current_frame_idx = 0

        if file_path and os.path.exists(file_path):
            self._is_caching = True
            self.media_player.setMedia(QMediaContent(QUrl.fromLocalFile(file_path)))
            self.media_player.play()

    def _on_frame_captured(self, image):
        """采集并预缩放"""
        if not self._is_caching: return

        # 性能关键点：在采集时就完成高质量缩放，存入内存的是小图
        pixmap = QtGui.QPixmap.fromImage(image).scaled(
            self._fixed_size,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation
        )

        self._frame_cache.append(pixmap)

        # 实时显示第一遍
        self.img_label.setPixmap(pixmap)

        # 保护：防止超长视频导致内存溢出
        if len(self._frame_cache) >= self._max_cache_frames:
            self._finish_caching()

    def _on_media_status_changed(self, status):
        # 当视频播放到末尾，说明缓存一轮完成
        if status == QMediaPlayer.EndOfMedia:
            self._finish_caching()

    def _finish_caching(self):
        """切换模式：关闭解码器，开启软件播放"""
        if not self._is_caching: return
        self._is_caching = False
        self.media_player.stop()

        if self._frame_cache:
            # 根据采集到的帧数和视频长度，估算定时器间隔 (默认 1000/12 fps)
            interval = int(1000 / self._fps_limit)
            self.playback_timer.start(interval)

    def _update_next_frame(self):
        """纯软件切换，不涉及解码，极低 CPU 占用"""
        if not self._frame_cache: return

        self._current_frame_idx = (self._current_frame_idx + 1) % len(self._frame_cache)
        self.img_label.setPixmap(self._frame_cache[self._current_frame_idx])

    # --- 视口优化：不可见时不播放 ---
    def paintEvent(self, event):
        # 如果节点被遮挡或不在视口，可以考虑在此处暂停 timer
        super().paintEvent(event)

    def showEvent(self, event):
        if not self._is_caching and self._frame_cache:
            self.playback_timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.playback_timer.stop()
        self.media_player.pause()
        super().hideEvent(event)

    def mousePressEvent(self, event):
        # 点击弹出播放窗口逻辑...
        pass