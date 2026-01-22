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


# --- 1. 后台加载线程 ---
class VideoLoaderThread(QThread):
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

        total_to_extract = (end_frame - start_frame) // self.frame_step

        # 计算初始分辨率
        aspect_ratio = raw_h / raw_w if raw_w > 0 else 0.5625
        target_w = self.max_width
        target_h = int(target_w * aspect_ratio)

        self.meta_ready.emit(target_w, target_h, fps, self.frame_step, duration, total_to_extract)

        current_f = start_frame
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 75]

        while self._is_running:
            cap.set(cv2.CAP_PROP_POS_FRAMES, current_f)
            ret, frame = cap.read()
            if not ret: break

            try:
                # 预处理成固定宽度发送，减少传输压力
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


# --- 2. 配置面板 ---

class ComfySlider(QtWidgets.QWidget):
    valueChanged = pyqtSignal(float)
    valueConfirmed = pyqtSignal(float)

    def __init__(self, label_text, min_v, max_v, default_v, is_float=False, suffix=""):
        super().__init__()
        self.is_float, self.suffix, self.factor = is_float, suffix, (100 if is_float else 1)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(int(min_v * self.factor), int(max_v * self.factor))
        self.slider.setValue(int(default_v * self.factor))
        self.slider.setFixedHeight(12)

        self.lbl_tag = QLabel(label_text)
        self.lbl_tag.setStyleSheet("color: #999; font-size: 10px;")
        self.lbl_val = QLabel(f"{default_v}{suffix}")
        self.lbl_val.setStyleSheet("color: #EEE; font-size: 10px; min-width: 30px;")

        layout.addWidget(self.lbl_tag)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.lbl_val)

        self.slider.valueChanged.connect(self._on_value_changed)
        self.slider.sliderReleased.connect(lambda: self.valueConfirmed.emit(self.slider.value() / self.factor))

    def _on_value_changed(self, v):
        val = v / self.factor
        txt = f"{val:.1f}{self.suffix}" if self.is_float else f"{int(val)}{self.suffix}"
        self.lbl_val.setText(txt)
        self.valueChanged.emit(val)


class ComfyConfigPanel(QtWidgets.QFrame):
    reloadRequested = pyqtSignal(int, int, tuple)
    speedChanged = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #282828; border-bottom: 1px solid #111; color: #EEE;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 6)
        layout.setSpacing(2)

        row1 = QHBoxLayout()
        self.combo_res = CustomComboBox()
        self.combo_res.addItems(["低", "中", "高", "原生"])
        self.combo_res.setCurrentIndex(1)
        self.slider_speed = ComfySlider("倍速", 0.5, 3.0, 1.0, is_float=True, suffix="x")
        row1.addWidget(QLabel("分辨率:"))
        row1.addWidget(self.combo_res)
        row1.addWidget(self.slider_speed)

        self.slider_step = ComfySlider("采样间隔", 1, 30, 2, suffix="帧")

        layout.addLayout(row1)
        layout.addWidget(self.slider_step)

        self.combo_res.currentIndexChanged.connect(self._request_reload)
        self.slider_step.valueConfirmed.connect(lambda x: self._request_reload())
        self.slider_speed.valueChanged.connect(self.speedChanged.emit)

    def _request_reload(self):
        widths = [320, 512, 720, 1920]
        w = widths[self.combo_res.currentIndex()]
        step = int(self.slider_step.slider.value())
        self.reloadRequested.emit(w, step, (0.0, 1.0))


# --- 3. 播放控制条 ---
class PlayControlBar(QWidget):
    seekRequested = pyqtSignal(int)
    playPauseToggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setStyleSheet("background: #181818; color: #AAA; font-size: 10px;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(8)

        self.btn_play = ToolButton(FluentIcon.PAUSE)
        self.btn_play.setFixedSize(22, 22)
        self.btn_play.setCheckable(True)
        self.btn_play.setChecked(True)
        self.btn_play.setStyleSheet("color: white; border: none;")

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal { background: #333; height: 3px; border-radius: 2px; }
            QSlider::handle:horizontal { background: #00AAFF; width: 10px; height: 10px; margin: -4px 0; border-radius: 5px; }
        """)

        self.lbl_frames = QLabel("0 / 0")
        self.lbl_frames.setFixedWidth(60)

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


# --- 5. 主视频播放控件 (自适应版) ---
class VideoPlayWidget(QFrame):
    sizeHintChanged = pyqtSignal()
    valueChanged = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 1. 关键策略：允许在垂直和水平方向无限扩展
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(200, 150)
        self.setStyleSheet("VideoPlayWidget { background: #111; border: none; }")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # 顶部配置面板
        self.config_bar = ComfyConfigPanel(self)
        self.config_bar.reloadRequested.connect(self._trigger_reload)
        self.config_bar.speedChanged.connect(self._update_speed)
        self.layout.addWidget(self.config_bar)

        # 中间渲染区 (使用自定义 Label 处理比例绘制)
        self.img_label = QLabel(self)
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setStyleSheet("background: black;")
        # 必须设为 Expanding，让它吃掉所有剩余空间
        self.img_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.layout.addWidget(self.img_label, 1)

        # 底部控制条
        self.control_bar = PlayControlBar(self)
        self.control_bar.seekRequested.connect(self._seek_to_frame)
        self.control_bar.playPauseToggled.connect(self._toggle_playback)
        self.layout.addWidget(self.control_bar)

        # 内部数据
        self._compressed_cache = []
        self._loader_thread = None
        self._current_idx = 0
        self._base_interval = 40
        self._file_path = None
        self._hint_size = QSize(350, 300)

        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self._next_frame)

        # 初始隐藏
        self._show_ui(False)

    def _show_ui(self, visible):
        self.config_bar.setVisible(visible)
        self.img_label.setVisible(visible)
        self.control_bar.setVisible(visible)

    def _trigger_reload(self, width, step, range_pct):
        if not self._file_path:
            self._reset_state()
            return

        self._show_ui(True)
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
        self._base_interval = int((1000 / fps) * step)
        self._update_speed(self.config_bar.slider_speed.slider.value() / 100.0)

        # 设置初始推荐大小
        panel_h = self.config_bar.sizeHint().height()
        ctrl_h = self.control_bar.height()
        self._hint_size = QSize(w, h + panel_h + ctrl_h)

        # 触发节点刷新
        self.updateGeometry()
        self.sizeHintChanged.emit()

    def _on_frame_buffer(self, jpeg_bytes):
        self._compressed_cache.append(jpeg_bytes)
        total = len(self._compressed_cache)

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
        """高质量等比例渲染"""
        img = QImage.fromData(jpeg_data)
        if img.isNull(): return

        # 获取 Label 当前的实际尺寸
        canvas_size = self.img_label.size()
        if canvas_size.width() < 10 or canvas_size.height() < 10: return

        # 核心：根据 Label 尺寸进行等比例缩放
        pixmap = QPixmap.fromImage(img)
        scaled_pixmap = pixmap.scaled(canvas_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.img_label.setPixmap(scaled_pixmap)

    def _seek_to_frame(self, idx):
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
        interval = max(10, int(self._base_interval / (val if val > 0 else 1.0)))
        self.playback_timer.setInterval(interval)

    def resizeEvent(self, event):
        """当节点被拖大时，立即刷新当前帧的渲染尺寸"""
        super().resizeEvent(event)
        if self._compressed_cache and self._current_idx < len(self._compressed_cache):
            self._render(self._compressed_cache[self._current_idx])

    def sizeHint(self):
        return self._hint_size

    def set_value(self, file_path):
        if not file_path or not os.path.exists(file_path):
            self._reset_state()
            return
        self._file_path = file_path
        self.config_bar._request_reload()
        self.valueChanged.emit(file_path)

    def _reset_state(self):
        self._file_path = None
        self.playback_timer.stop()
        if self._loader_thread:
            self._loader_thread.stop()
        self._compressed_cache = []
        self._show_ui(False)
        self._hint_size = QSize(200, 150)
        self.updateGeometry()
        self.sizeHintChanged.emit()