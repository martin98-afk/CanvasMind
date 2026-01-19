# -*- coding: utf-8 -*-
import os

import cv2
from PyQt5 import QtWidgets
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QSize
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QImage
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import *
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QFrame, QSlider
from PyQt5.QtWidgets import QWidget, QComboBox
from Qt import QtWidgets, QtCore
from qfluentwidgets import ToolButton, FluentIcon
from qfluentwidgets.multimedia import SimpleMediaPlayBar

from app.widgets.basic_widget.combo_widget import CustomComboBox


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


# --- 1. 后台加载线程 (改为采样间隔控制) ---
class VideoLoaderThread(QThread):
    # (width, height, fps, actual_step, duration, total_extracted_count)
    meta_ready = pyqtSignal(int, int, float, int, float, int)
    frame_ready = pyqtSignal(bytes)

    def __init__(self, file_path, max_width=512, frame_step=1, range_pct=(0.0, 1.0)):
        super().__init__()
        self.file_path = file_path
        self.max_width = max_width
        self.frame_step = max(1, frame_step)
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

        # 计算采样总数
        total_to_extract = (end_frame - start_frame) // self.frame_step

        # 分辨率计算
        aspect_ratio = raw_h / raw_w if raw_w > 0 else 0.5625
        target_w = self.max_width
        target_h = int(target_w * aspect_ratio)

        self.meta_ready.emit(target_w, target_h, fps, self.frame_step, duration, total_to_extract)

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

            current_f += self.frame_step
            if current_f >= end_frame: break

        cap.release()

    def stop(self):
        self._is_running = False
        self.wait()


# --- 2. 配置面板 (采样数 -> 采样间隔) ---
class ComfyConfigPanel(QtWidgets.QFrame):
    reloadRequested = pyqtSignal(int, int, tuple)
    speedChanged = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #222; border-bottom: 1px solid #333; color: #EEE;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # 第一行：分辨率 + 播放倍速
        row1 = QHBoxLayout()
        self.combo_res = CustomComboBox()
        self.combo_res.addItems(["低", "中", "高", "原生"])
        self.combo_res.setCurrentIndex(1)
        self.slider_speed = ComfySlider("倍速", 0.5, 3.0, 1.0, is_float=True, suffix="x")
        row1.addWidget(QLabel("分辨率:"))
        row1.addWidget(self.combo_res)
        row1.addWidget(self.slider_speed)

        # 第三行：采样间隔 (控制流畅度)
        self.slider_step = ComfySlider("采样间隔", 1, 30, 2, suffix="帧/步")

        layout.addLayout(row1)
        layout.addWidget(self.slider_step)

        self.combo_res.currentIndexChanged.connect(self._request_reload)
        self.slider_step.valueConfirmed.connect(lambda: self._request_reload())
        self.slider_speed.valueChanged.connect(self.speedChanged.emit)

    def _request_reload(self):
        widths = [320, 512, 720, 1920]
        w = widths[self.combo_res.currentIndex()]
        step = int(self.slider_step.slider.value())
        r = (0.0, 1.0)  # 简化逻辑，实际可从 range_slider 获取
        self.reloadRequested.emit(w, step, r)


# --- 3. 播放控制条 (新增) ---
class PlayControlBar(QWidget):
    seekRequested = pyqtSignal(int)
    playPauseToggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setStyleSheet("background: #111; color: #AAA; font-size: 10px;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(8)

        # 播放/暂停按钮
        self.btn_play = ToolButton(FluentIcon.PAUSE)  # 使用符号简单表示
        self.btn_play.setFixedSize(24, 24)
        self.btn_play.setCheckable(True)
        self.btn_play.setChecked(True)

        # 进度条
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setStyleSheet("""
            QSlider::handle:horizontal { background: #444; width: 12px; margin: -2px 0; border-radius: 6px; }
            QSlider::groove:horizontal { background: #333; height: 4px; }
        """)

        # 帧数显示
        self.lbl_frames = QLabel("0 / 0")

        layout.addWidget(self.btn_play)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.lbl_frames)

        self.btn_play.toggled.connect(self._on_btn_toggled)
        self.slider.sliderMoved.connect(self.seekRequested.emit)
        self.slider.sliderPressed.connect(lambda: self.playPauseToggled.emit(False))

    def _on_btn_toggled(self, checked):
        self.btn_play.setIcon(FluentIcon.PAUSE if checked else FluentIcon.PLAY)
        self.playPauseToggled.emit(checked)

    def update_info(self, current, total):
        self.slider.setMaximum(max(0, total - 1))
        self.slider.setValue(current)
        self.lbl_frames.setText(f"{current} / {total}")


# --- 4. 辅助滑块 (保持不变) ---
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
        self.lbl_val = QLabel(f"{default_v}{suffix}")
        layout.addWidget(QLabel(label_text))
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.lbl_val)
        self.slider.valueChanged.connect(lambda v: (
            self.lbl_val.setText(f"{v / self.factor:.1f}{suffix}" if is_float else f"{v}{suffix}"),
            self.valueChanged.emit(v / self.factor)))
        self.slider.sliderReleased.connect(lambda: self.valueConfirmed.emit(self.slider.value() / self.factor))


# --- 5. 主视频播放控件 ---
class VideoPlayWidget(QFrame):
    sizeHintChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("VideoPlayWidget { background: transparent; border: none; }")
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # 1. 顶部配置面板
        self.config_bar = ComfyConfigPanel(self)
        self.config_bar.reloadRequested.connect(self._trigger_reload)
        self.config_bar.speedChanged.connect(self._update_speed)
        self.layout.addWidget(self.config_bar)

        # 2. 中间图片区
        self.img_label = QLabel(self)
        self.img_label.setScaledContents(True)
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.layout.addWidget(self.img_label, 1)

        # 3. 底部播放控制条
        self.control_bar = PlayControlBar(self)
        self.control_bar.seekRequested.connect(self._seek_to_frame)
        self.control_bar.playPauseToggled.connect(self._toggle_playback)
        self.layout.addWidget(self.control_bar)

        # 内部状态
        self._compressed_cache = []
        self._loader_thread = None
        self._current_idx = 0
        self._base_interval = 40
        self._file_path = None

        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self._next_frame)

    def _trigger_reload(self, width, step, range_pct):
        if not self._file_path:
            self._reset_state()
            return

        self.config_bar.show()
        self.img_label.show()
        self.control_bar.show()
        self.playback_timer.stop()
        if self._loader_thread:
            self._loader_thread.stop()

        self._compressed_cache = []
        self._current_idx = 0
        self.img_label.setText("Loading...")

        self._loader_thread = VideoLoaderThread(self._file_path, width, step, range_pct)
        self._loader_thread.meta_ready.connect(self._on_meta_ready)
        self._loader_thread.frame_ready.connect(self._on_frame_buffer)
        self._loader_thread.start()

    def _on_meta_ready(self, w, h, fps, step, duration, total_count):
        # 计算每一帧预览图应该播放的时间间隔
        # 比如视频30fps, step是2, 那预览图每帧间隔就是 (1000/30)*2 = 66ms
        self._base_interval = int((1000 / fps) * step)
        self._update_speed(self.config_bar.slider_speed.slider.value() / 100.0)

        # 调整 UI 尺寸 (面板 + 图片 + 控制条)
        panel_h = self.config_bar.sizeHint().height()
        ctrl_h = self.control_bar.height()
        self.setFixedSize(w, h + panel_h + ctrl_h)
        self.updateGeometry()
        self.sizeHintChanged.emit()

    def _on_frame_buffer(self, jpeg_bytes):
        self._compressed_cache.append(jpeg_bytes)
        total = len(self._compressed_cache)

        # 缓冲到前几帧就开始播放
        if total == 1:
            self._render(jpeg_bytes)
        if total == 5 and self.control_bar.btn_play.isChecked():
            self.playback_timer.start()

        self.control_bar.update_info(self._current_idx, total)

    def _next_frame(self):
        if not self._compressed_cache: return
        self._current_idx = (self._current_idx + 1) % len(self._compressed_cache)
        self._render(self._compressed_cache[self._current_idx])
        self.control_bar.update_info(self._current_idx, len(self._compressed_cache))

    def _render(self, jpeg_data):
        img = QImage.fromData(jpeg_data)
        if not img.isNull():
            self.img_label.setPixmap(QPixmap.fromImage(img))

    def _seek_to_frame(self, idx):
        # 拖动进度条时停止播放并跳转
        self.playback_timer.stop()
        self.control_bar.btn_play.setChecked(False)
        if 0 <= idx < len(self._compressed_cache):
            self._current_idx = idx
            self._render(self._compressed_cache[idx])
            self.control_bar.update_info(idx, len(self._compressed_cache))

    def _toggle_playback(self, playing):
        if playing and self._compressed_cache:
            self.playback_timer.start()
        else:
            self.playback_timer.stop()

    def _update_speed(self, val):
        interval = max(10, int(self._base_interval / val))
        self.playback_timer.setInterval(interval)

    def set_value(self, file_path):
        self._file_path = file_path
        self.config_bar._request_reload()

    def _reset_state(self):
        self._file_path = None
        self.playback_timer.stop()
        if self._loader_thread:
            self._loader_thread.stop()
        self.img_label.clear()
        self._compressed_cache = []
        self.config_bar.hide()
        self.img_label.hide()
        self.control_bar.hide()
        self.setFixedSize(200, 150)
        self.updateGeometry()
        self.sizeHintChanged.emit()