# -*- coding: utf-8 -*-
import os

from PyQt5 import QtGui
from PyQt5.QtCore import QSize, Qt, QTimer
from PyQt5.QtCore import QUrl
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent, QAbstractVideoSurface, QVideoFrame, QAbstractVideoBuffer
from Qt import QtWidgets, QtCore
from qfluentwidgets import FluentIcon, IconWidget, PushButton
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


class ThumbnailSurface(QAbstractVideoSurface):
    frameCaptured = QtCore.Signal(QtGui.QImage)

    def supportedPixelFormats(self, handleType):
        return [QVideoFrame.Format_RGB32, QVideoFrame.Format_ARGB32, QVideoFrame.Format_BGR32]

    def present(self, frame):
        if frame.isValid():
            clone_frame = QVideoFrame(frame)
            if clone_frame.map(QAbstractVideoBuffer.ReadOnly):
                try:
                    image = clone_frame.image()
                    if image.isNull():
                        image = QtGui.QImage(clone_frame.bits(), clone_frame.width(),
                                             clone_frame.height(), clone_frame.bytesPerLine(),
                                             QVideoFrame.imageFormatFromPixelFormat(clone_frame.pixelFormat()))
                    if not image.isNull():
                        self.frameCaptured.emit(image.copy())
                finally:
                    clone_frame.unmap()
            return True
        return False


# --- 主控件优化版 ---
class VideoPlayWidget(QtWidgets.QFrame):
    valueChanged = QtCore.Signal(object)
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_path = None
        self._player_window = None

        # 1. 【核心：锁定大小】
        self._fixed_size = QSize(280, 158)
        self.setFixedSize(self._fixed_size)
        self.setCursor(Qt.PointingHandCursor)

        self.setObjectName("VideoPlayWidget")
        self.setStyleSheet("""
            #VideoPlayWidget { 
                background-color: #1A1A1A; 
                border: 1px solid #333; 
                border-radius: 8px; 
            }
            #VideoPlayWidget:hover { border: 1px solid #00A6FF; }
        """)

        # 2. 布局逻辑
        self.main_layout = QtWidgets.QStackedLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # --- A界面：预览展示区 ---
        self.preview_container = QtWidgets.QWidget()
        self.preview_container.setFixedSize(self._fixed_size)

        # 图片层
        self.img_label = QtWidgets.QLabel(self.preview_container)
        self.img_label.setFixedSize(self._fixed_size)
        self.img_label.setScaledContents(True)
        self.img_label.setStyleSheet("background: #000; border-radius: 6px;")

        # 蒙版层
        self.overlay = QtWidgets.QFrame(self.preview_container)
        self.overlay.setFixedSize(self._fixed_size)
        self.overlay.setStyleSheet("background: rgba(0, 0, 0, 120); border-radius: 6px;")

        # 播放图标层
        self.play_icon = IconWidget(FluentIcon.PLAY, self.preview_container)
        self.play_icon.setFixedSize(50, 50)
        self.play_icon.setStyleSheet("qproperty-color: white; background: transparent;")

        # 【核心：鼠标穿透】 让预览区的所有东西都不拦截点击，把点击交给最外层的 VideoPlayWidget
        self.preview_container.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.img_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.play_icon.setAttribute(Qt.WA_TransparentForMouseEvents)

        # 居中图标
        ix = (self._fixed_size.width() - 50) // 2
        iy = (self._fixed_size.height() - 50) // 2
        self.play_icon.move(ix, iy)

        self.main_layout.addWidget(self.preview_container)  # Index 0

        # --- B界面：降级按钮区 ---
        self.button_page = QtWidgets.QWidget()
        self.btn_layout = QtWidgets.QVBoxLayout(self.button_page)
        self.fallback_btn = PushButton(FluentIcon.PLAY, "播放视频", self)
        self.btn_layout.addWidget(self.fallback_btn)

        self.main_layout.addWidget(self.button_page)  # Index 1

        # 3. 后台逻辑
        self.thumbnail_player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        self.surface = ThumbnailSurface()
        self.thumbnail_player.setVideoOutput(self.surface)

        self.surface.frameCaptured.connect(self._on_frame_captured)
        self.fallback_btn.clicked.connect(self.play)

        self.fallback_timer = QTimer(self)
        self.fallback_timer.setSingleShot(True)
        self.fallback_timer.timeout.connect(lambda: self.main_layout.setCurrentIndex(1))

    # --- 【核心修复：统一点击处理】 ---
    def mousePressEvent(self, event):
        # 如果当前显示的是预览图（Index 0），点击整个组件都会触发播放
        if self.main_layout.currentIndex() == 0:
            if event.button() == Qt.LeftButton:
                self.play()
        super().mousePressEvent(event)

    def set_value(self, file_path):
        self._file_path = file_path
        if not file_path or not os.path.exists(file_path):
            self.hide()
            self._fixed_size = QSize(200, 150)
            self.setFixedSize(self._fixed_size)
            self.sizeHintChanged.emit()
            self.update()
            return

        self._fixed_size = QSize(280, 158)
        self.setFixedSize(self._fixed_size)
        self.show()
        # 始终保持固定大小，防止节点跳变
        self.setFixedSize(self._fixed_size)
        self.main_layout.setCurrentIndex(1)

        self.thumbnail_player.setMedia(QMediaContent(QUrl.fromLocalFile(file_path)))
        self.thumbnail_player.setMuted(True)
        self.thumbnail_player.play()
        self.fallback_timer.start(2500)
        self.sizeHintChanged.emit()
        self.update()

    def _on_frame_captured(self, image):
        self.fallback_timer.stop()
        self.thumbnail_player.stop()

        # 缩放图片到固定大小再显示，防止撑开
        pixmap = QtGui.QPixmap.fromImage(image)
        self.img_label.setPixmap(
            pixmap.scaled(self._fixed_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))

        self.main_layout.setCurrentIndex(0)

    def play(self):
        if not self._file_path: return
        if not self._player_window:
            self._player_window = VideoPlayerWindow()
        self._player_window.play_file(self._file_path)

    def sizeHint(self):
        return self._fixed_size