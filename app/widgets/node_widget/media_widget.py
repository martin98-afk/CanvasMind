# -*- coding: utf-8 -*-
import os

import cv2
from PyQt5 import QtGui
from PyQt5 import QtWidgets
from PyQt5.QtCore import QRect
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QSize
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QPainter, QColor, QImage
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QFrame, QSlider
from PyQt5.QtWidgets import QWidget, QComboBox
from Qt import QtWidgets, QtCore
from qfluentwidgets import BodyLabel
from qfluentwidgets.multimedia import SimpleMediaPlayBar

from app.widgets.basic_widget.combo_widget import CustomComboBox
from app.widgets.basic_widget.range_slider import RangeSlider


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


# --- 1. 后台加载线程 (逻辑保持不变，依然是极致性能的核心) ---
class VideoLoaderThread(QThread):
    # (width, height, fps, step, duration)
    meta_ready = pyqtSignal(int, int, float, int, float)
    frame_ready = pyqtSignal(bytes)

    def __init__(self, file_path, max_width=512, max_frames=120, range_pct=(0.0, 1.0)):
        super().__init__()
        self.file_path = file_path
        self.max_width = max_width
        self.max_frames = max_frames
        self.range_pct = range_pct
        self._is_running = True

    def run(self):
        cap = cv2.VideoCapture(self.file_path)
        if not cap.isOpened(): return

        raw_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        raw_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0: fps = 24.0

        duration = total_frames / fps

        start_frame = int(total_frames * self.range_pct[0])
        end_frame = int(total_frames * self.range_pct[1])
        slice_count = max(1, end_frame - start_frame)

        # 分辨率计算
        aspect_ratio = raw_h / raw_w if raw_w > 0 else 0.5625
        target_w = self.max_width
        target_h = int(target_w * aspect_ratio)

        step = max(1, slice_count // self.max_frames)
        # 将总时长 duration 发回给 UI
        self.meta_ready.emit(target_w, target_h, fps, step, duration)

        current_f = start_frame
        count = 0
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 75]

        while self._is_running:
            cap.set(cv2.CAP_PROP_POS_FRAMES, current_f)
            ret, frame = cap.read()
            if not ret: break
            try:
                frame = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
                _, encoded_img = cv2.imencode('.jpg', frame, encode_param)
                self.frame_ready.emit(encoded_img.tobytes())
            except:
                pass
            count += 1
            current_f += step
            if count >= self.max_frames or current_f >= end_frame: break
        cap.release()

    def stop(self):
        self._is_running = False
        self.wait()


# --- 5. 配置面板 ---
class ComfyConfigPanel(QtWidgets.QFrame):
    reloadRequested = pyqtSignal(int, int, tuple)
    speedChanged = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #222; border-bottom: 1px solid #333;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # 第一行：分辨率 + 采样数量
        row1 = QHBoxLayout()
        self.combo_res = CustomComboBox()
        self.combo_res.addItems(["低", "中", "高", "原生"])
        self.combo_res.setCurrentIndex(1)
        self.slider_speed = ComfySlider("播放速度", 0.5, 3.0, 1.0, is_float=True, suffix="x")

        row1.addWidget(BodyLabel("分辨率:"))
        row1.addWidget(self.combo_res)
        row1.addWidget(self.slider_speed)

        # 第二行：视频剪辑范围
        row2 = QHBoxLayout()
        self.range_slider = RangeSlider()
        row2.addWidget(BodyLabel("剪辑:"))
        row2.addWidget(self.range_slider, 1)

        # 第三行：播放速度
        row3 = QHBoxLayout()
        self.slider_frames = ComfySlider("采样数", 20, 200, 100, suffix="帧")
        row3.addWidget(self.slider_frames)

        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addLayout(row3)

        self.combo_res.currentIndexChanged.connect(self._request_reload)
        self.slider_frames.valueConfirmed.connect(lambda: self._request_reload())
        self.range_slider.sliderMoved.connect(self._request_reload)
        self.slider_speed.valueChanged.connect(self.speedChanged.emit)

    def _request_reload(self):
        # 映射分辨率
        idx = self.combo_res.currentIndex()
        widths = [320, 512, 720, 1920]
        w = widths[idx]
        f = self.slider_frames.slider.value()
        r = (self.range_slider.min_val, self.range_slider.max_val)
        self.reloadRequested.emit(w, f, r)


# --- 6. 辅助滑块组件 (ComfySlider) ---
class ComfySlider(QtWidgets.QWidget):
    valueChanged = pyqtSignal(float)
    valueConfirmed = pyqtSignal(float)

    def __init__(self, label_text, min_v, max_v, default_v, is_float=False, suffix=""):
        super().__init__()
        self.is_float, self.suffix, self.factor = is_float, suffix, (100 if is_float else 1)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(int(min_v * self.factor), int(max_v * self.factor))
        self.slider.setValue(int(default_v * self.factor))
        self.lbl_val = BodyLabel()
        layout.addWidget(BodyLabel(label_text))
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.lbl_val)
        self.slider.valueChanged.connect(
            lambda v: (self.lbl_val.setText(f"{v / self.factor:.1f}{suffix}" if is_float else f"{v}{suffix}"),
                       self.valueChanged.emit(v / self.factor)))
        self.slider.sliderReleased.connect(lambda: self.valueConfirmed.emit(self.slider.value() / self.factor))
        self.lbl_val.setText(f"{default_v}{suffix}")


# --- 7. 主视频播放控件 ---
class VideoPlayWidget(QFrame):
    sizeHintChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_path = None
        self.setFixedSize(200, 150)  # 默认节点大小

        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # 1. 新的滑块控制面板
        self.config_bar = ComfyConfigPanel(self)
        self.config_bar.reloadRequested.connect(self._trigger_reload)
        self.config_bar.speedChanged.connect(self._update_speed)
        self.layout.addWidget(self.config_bar)

        # 2. 图片区
        self.img_label = QtWidgets.QLabel(self)
        self.img_label.setScaledContents(True)
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.layout.addWidget(self.img_label, 1)

        # 内部状态
        self._compressed_cache = []
        self._loader_thread = None
        self._current_idx = 0
        self._base_interval = 100
        self._speed_multiplier = 1.0

        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self._next_frame)
        self.config_bar.hide()

    def set_value(self, file_path):
        if file_path is None:
            self._reset_state()
            return
        if self._file_path == file_path: return
        self._file_path = file_path
        self.config_bar.show()
        self.config_bar._request_reload()  # 使用默认参数加载
        self.img_label.show()

    def _reset_state(self):
        self._file_path = None
        self.playback_timer.stop()
        if self._loader_thread: self._loader_thread.stop()
        self.img_label.clear()
        self._compressed_cache = []
        self.config_bar.hide()
        self.img_label.hide()
        self.setFixedSize(200, 150)
        self.sizeHintChanged.emit()

    def _trigger_reload(self, width, frames, range_pct):
        if not self._file_path: return
        self.playback_timer.stop()
        if self._loader_thread: self._loader_thread.stop()
        self._compressed_cache = []
        self._current_idx = 0
        self.img_label.setText("Loading...")

        self._loader_thread = VideoLoaderThread(self._file_path, width, frames, range_pct)
        self._loader_thread.meta_ready.connect(self._on_meta_ready)
        self._loader_thread.frame_ready.connect(self._on_frame_buffer)
        self._loader_thread.start()

    def _on_meta_ready(self, w, h, fps, step, duration):
        # 更新滑块的总时长显示
        panel_h = self.config_bar.sizeHint().height()  # 自动获取面板高度
        total_h = h + panel_h
        self.config_bar.range_slider.set_duration(duration)
        self._base_interval = int((1000 * step) / fps)
        # 调整大小并通知父级
        self.setFixedSize(w, total_h)
        self.sizeHintChanged.emit()
        self.updateGeometry()

    def _on_frame_buffer(self, jpeg_bytes):
        self._compressed_cache.append(jpeg_bytes)
        if len(self._compressed_cache) == 2:
            self.playback_timer.start(self._base_interval)
        if len(self._compressed_cache) == 1:
            self._render(jpeg_bytes)

    def _update_speed(self, val):
        self.playback_timer.setInterval(max(10, int(self._base_interval / val)))

    def _next_frame(self):
        if not self._compressed_cache: return
        self._current_idx = (self._current_idx + 1) % len(self._compressed_cache)
        self._render(self._compressed_cache[self._current_idx])

    def _render(self, jpeg_data):
        img = QImage.fromData(jpeg_data)
        if not img.isNull():
            self.img_label.setPixmap(QPixmap.fromImage(img))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._file_path:
            self.clicked.emit(self._file_path)
        super().mousePressEvent(event)

    def closeEvent(self, event):
        self._reset_state()
        super().closeEvent(event)