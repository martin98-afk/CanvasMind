# -*- coding: utf-8 -*-
import os

from PyQt5 import QtGui
from PyQt5 import QtWidgets
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import QUrl
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent, QAbstractVideoSurface, QVideoFrame, QAbstractVideoBuffer
from Qt import QtWidgets, QtCore
from qfluentwidgets import IconWidget, FluentIcon
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
                    image = clone_frame.image().copy()
                    if not image.isNull():
                        self.frameCaptured.emit(image)
                finally:
                    clone_frame.unmap()
            return True
        return False


class VideoPlayWidget(QtWidgets.QFrame):
    valueChanged = QtCore.Signal(object)
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_path = None
        self._player_window = None
        self._fixed_size = QSize(280, 158)

        # --- 性能变量 ---
        self._frame_cache = []
        self._is_caching = False
        self._current_frame_idx = 0
        self._fps_limit = 12
        self._max_cache_frames = 150  # 限制缓存长度防止内存溢出

        self.setFixedSize(self._fixed_size)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("VideoPlayWidget")
        # 确保圆角和溢出隐藏
        self.setStyleSheet("""
            #VideoPlayWidget { 
                background: #000; 
                border-radius: 8px; 
                border: 1px solid #333;
            }
            #VideoPlayWidget:hover { border: 1px solid #00A6FF; }
        """)

        # --- UI 层级构建 ---
        # 1. 底层：视频帧显示层
        self.img_label = QtWidgets.QLabel(self)
        self.img_label.setFixedSize(self._fixed_size)
        self.img_label.setScaledContents(True)
        self.img_label.setAttribute(Qt.WA_TransparentForMouseEvents)  # 关键：不拦截鼠标

        # 2. 中层：半透明遮罩层 (默认隐藏)
        self.overlay = QtWidgets.QFrame(self)
        self.overlay.setFixedSize(self._fixed_size)
        self.overlay.setStyleSheet("background: rgba(0, 0, 0, 100); border-radius: 8px;")
        self.overlay.hide()
        self.overlay.setAttribute(Qt.WA_TransparentForMouseEvents)  # 关键：不拦截鼠标

        # 3. 顶层：播放图标 (默认隐藏)
        self.play_icon = IconWidget(FluentIcon.PLAY, self)
        self.play_icon.setFixedSize(50, 50)
        self.play_icon.setStyleSheet("qproperty-color: white; background: transparent;")
        self.play_icon.move((self._fixed_size.width() - 50) // 2, (self._fixed_size.height() - 50) // 2)
        self.play_icon.hide()
        self.play_icon.setAttribute(Qt.WA_TransparentForMouseEvents)  # 关键：不拦截鼠标

        # --- 后台组件 ---
        self.media_player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        self.surface = CachedVideoSurface()
        self.media_player.setVideoOutput(self.surface)
        self.media_player.setMuted(True)

        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self._update_next_frame)

        self.surface.frameCaptured.connect(self._on_frame_captured)
        self.media_player.mediaStatusChanged.connect(self._on_media_status_changed)

    # --- 交互逻辑 ---
    def enterEvent(self, event):
        """鼠标移入：显示图标和遮罩"""
        self.overlay.show()
        self.play_icon.show()
        # 如果缓存好了，鼠标移入时才开始动（ComfyUI 常用性能优化）
        if self._frame_cache:
            self.playback_timer.start(int(1000 / self._fps_limit))
        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标移出：隐藏图标和遮罩"""
        self.overlay.hide()
        self.play_icon.hide()
        # 鼠标移出停止播放预览，省电省资源
        self.playback_timer.stop()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        """点击弹出播放窗口"""
        if event.button() == Qt.LeftButton:
            self.open_player_window()
        super().mousePressEvent(event)

    def open_player_window(self):
        if not self._file_path: return
        if not self._player_window:
            self._player_window = VideoPlayerWindow()
        self._player_window.play_file(self._file_path)

    # --- 核心缓存逻辑 ---
    def set_value(self, file_path):
        if self._file_path == file_path: return
        self._file_path = file_path

        self.playback_timer.stop()
        self.media_player.stop()
        self._frame_cache.clear()
        self._current_frame_idx = 0
        self.img_label.clear()

        if file_path and os.path.exists(file_path):
            self._is_caching = True
            # 加载新视频时显示加载图标或第一帧
            self.media_player.setMedia(QMediaContent(QUrl.fromLocalFile(file_path)))
            self.media_player.play()

        self.valueChanged.emit(file_path)

    def _on_frame_captured(self, image):
        if not self._is_caching: return

        # 高质量预缩放（决定预览清晰度）
        pixmap = QtGui.QPixmap.fromImage(image).scaled(
            self._fixed_size * 1.5,  # 稍微多一点像素保证缩放清晰
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation
        )

        self._frame_cache.append(pixmap)
        # 第一遍缓存时实时显示
        if len(self._frame_cache) % 2 == 0:  # 降低缓存时的刷新频率，减少卡顿
            self.img_label.setPixmap(pixmap)

        if len(self._frame_cache) >= self._max_cache_frames:
            self._finish_caching()

    def _on_media_status_changed(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self._finish_caching()

    def _finish_caching(self):
        self._is_caching = False
        self.media_player.stop()
        # 缓存完成后，如果鼠标正好在上面，就开始播放
        if self.underMouse():
            self.playback_timer.start(int(1000 / self._fps_limit))

    def _update_next_frame(self):
        if not self._frame_cache: return
        self._current_frame_idx = (self._current_frame_idx + 1) % len(self._frame_cache)
        self.img_label.setPixmap(self._frame_cache[self._current_frame_idx])

    def sizeHint(self):
        return self._fixed_size

    def closeEvent(self, event):
        self.playback_timer.stop()
        self.media_player.stop()
        super().closeEvent(event)