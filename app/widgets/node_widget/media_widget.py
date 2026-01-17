# -*- coding: utf-8 -*-
import os

import cv2  # 核心依赖：用于后台快速取帧
from PyQt5 import QtWidgets
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QImage, QPixmap
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


# --- 后台加载线程 ---
class VideoLoaderThread(QThread):
    # 信号1: 元数据准备好了 (宽, 高, FPS, 采样步长)
    meta_ready = pyqtSignal(int, int, float, int)
    # 信号2: 第一帧图片
    frame_loaded = pyqtSignal(QPixmap, bool)
    # 信号3: 加载完成
    finished_loading = pyqtSignal(list)

    def __init__(self, file_path, max_width=512, max_frames=250):
        super().__init__()
        self.file_path = file_path
        self.max_width = max_width  # 限制最大宽度，高度自动计算
        self.max_frames = max_frames
        self._is_running = True

    def run(self):
        cap = cv2.VideoCapture(self.file_path)
        if not cap.isOpened(): return

        # 1. 获取原始信息
        raw_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        raw_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)

        if total_frames <= 0: total_frames = 0
        if fps <= 0: fps = 24.0

        # 2. 计算显示尺寸 (保持比例)
        # 逻辑：固定最大宽度，高度按比例缩放
        if raw_w > 0 and raw_h > 0:
            aspect_ratio = raw_h / raw_w
            target_w = self.max_width
            target_h = int(target_w * aspect_ratio)
        else:
            # 异常兜底
            target_w = self.max_width
            target_h = int(target_w * 9 / 16)

        # 计算采样步长
        step = max(1, total_frames // self.max_frames)

        # **关键**：在开始处理图片前，先通知 UI 调整大小
        self.meta_ready.emit(target_w, target_h, fps, step)

        cached_frames = []
        current_frame = 0
        count = 0

        while self._is_running and cap.isOpened():
            cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
            ret, frame = cap.read()
            if not ret: break

            # 转 RGB
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # 转 QImage
            h, w, ch = frame.shape
            bytes_per_line = ch * w
            qimg = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)

            # **缩放**：直接缩放到计算好的 target_w, target_h
            # 使用 IgnoreAspectRatio 因为我们在上面已经精确计算了比例，
            # 这样可以避免 QPixmap 内部再次计算黑边，完全填满控件
            pixmap = QPixmap.fromImage(qimg).scaled(
                target_w, target_h,
                Qt.IgnoreAspectRatio,
                Qt.SmoothTransformation
            )

            cached_frames.append(pixmap)

            if count == 0: self.frame_loaded.emit(pixmap, True)

            count += 1
            current_frame += step
            if count >= self.max_frames: break

        cap.release()

        if self._is_running:
            self.finished_loading.emit(cached_frames)

    def stop(self):
        self._is_running = False
        self.wait()


# --- 视频播放组件 ---
class VideoPlayWidget(QtWidgets.QFrame):
    valueChanged = QtCore.Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_path = None
        self._player_window = None

        # 初始状态：隐藏，大小为0
        self.setFixedSize(0, 0)
        self.hide()

        self._frame_cache = []
        self._current_frame_idx = 0
        self._loader_thread = None
        self._interval = 100

        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("VideoPlayWidget")

        self.setStyleSheet("""
            #VideoPlayWidget { 
                background: #000; 
                border-radius: 8px; 
                border: 1px solid #333;
                overflow: hidden;
            }
            #VideoPlayWidget:hover { border: 1px solid #00A6FF; }
        """)

        # UI 构建
        self.img_label = QtWidgets.QLabel(self)
        self.img_label.setScaledContents(True)  # 这里设为True，让图片完全贴合计算好的尺寸
        self.img_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        # 遮罩层
        self.overlay = QtWidgets.QFrame(self)
        self.overlay.setStyleSheet("background: rgba(0, 0, 0, 60); border-radius: 8px;")
        self.overlay.hide()
        self.overlay.setAttribute(Qt.WA_TransparentForMouseEvents)

        # 播放图标
        self.play_icon = IconWidget(FluentIcon.PLAY, self)
        self.play_icon.setFixedSize(64, 64)
        self.play_icon.hide()
        self.play_icon.setAttribute(Qt.WA_TransparentForMouseEvents)

        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self._update_next_frame)

    def resizeEvent(self, event):
        """当尺寸被后台线程改变时，自动调整内部布局"""
        new_size = event.size()
        self.img_label.resize(new_size)
        self.overlay.resize(new_size)

        # 图标始终居中
        icon_w = self.play_icon.width()
        icon_h = self.play_icon.height()
        self.play_icon.move(
            (new_size.width() - icon_w) // 2,
            (new_size.height() - icon_h) // 2
        )
        super().resizeEvent(event)

    def set_value(self, file_path):
        if self._file_path == file_path: return
        self._file_path = file_path

        # 1. 清理现场
        self.playback_timer.stop()
        if self._loader_thread and self._loader_thread.isRunning():
            self._loader_thread.stop()

        self.img_label.clear()
        self._frame_cache.clear()
        self.overlay.hide()
        self.play_icon.hide()

        # 2. 状态切换
        if file_path is None or not os.path.exists(file_path):
            # None: 彻底消失
            self.setFixedSize(200, 150)
            self.hide()
        else:
            # 有文件：先不要 show，等线程算好尺寸再说
            # 启动线程，设定最大宽度为 512 (可按需修改)
            self._loader_thread = VideoLoaderThread(file_path, max_width=512)

            # 连接信号
            self._loader_thread.meta_ready.connect(self._on_meta_ready)
            self._loader_thread.frame_loaded.connect(self._on_first_frame)
            self._loader_thread.finished_loading.connect(self._on_cache_finished)
            self._loader_thread.start()

        self.valueChanged.emit(file_path)

    def _on_meta_ready(self, width, height, fps, step):
        """线程计算好尺寸后，UI在这里进行调整"""
        # 1. 调整控件尺寸
        self.setFixedSize(width, height)
        self.show()  # 现在可以显示了

        # 2. 计算播放间隔 (保持原视频速度)
        if fps > 0:
            self._interval = int((1000 * step) / fps)
        else:
            self._interval = 100
        self._interval = max(30, self._interval)  # 限制最快33fps

    def _on_first_frame(self, pixmap, is_first):
        if is_first:
            self.img_label.setPixmap(pixmap)
            if not self._frame_cache: self._frame_cache.append(pixmap)

    def _on_cache_finished(self, frames):
        self._frame_cache = frames
        # 加载完立刻循环播放
        if len(self._frame_cache) > 1:
            self.playback_timer.start(self._interval)

    def _update_next_frame(self):
        if not self._frame_cache: return
        self._current_frame_idx = (self._current_frame_idx + 1) % len(self._frame_cache)
        self.img_label.setPixmap(self._frame_cache[self._current_frame_idx])

    # --- 交互 ---
    def enterEvent(self, event):
        if self._file_path:
            self.overlay.show()
            self.play_icon.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.overlay.hide()
        self.play_icon.hide()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._file_path:
            self.open_player_window()
        super().mousePressEvent(event)

    def open_player_window(self):
        if not self._player_window:
            self._player_window = VideoPlayerWindow()
        self._player_window.play_file(self._file_path)

    def closeEvent(self, event):
        self.playback_timer.stop()
        if self._loader_thread:
            self._loader_thread.stop()
        super().closeEvent(event)