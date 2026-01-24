# -*- coding: utf-8 -*-
import os
import cv2
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
from PyQt5.QtCore import Qt, QUrl, QSize
from PyQt5.QtGui import QImage
from PyQt5.QtGui import QPixmap
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
# 关键修改：Qt5 的导入方式
from PyQt5.QtWidgets import *
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QFrame, QSlider
from PyQt5.QtWidgets import QWidget
from Qt import QtWidgets
from qfluentwidgets import FluentIcon
# 引入 qfluentwidgets 的基础控件
from qfluentwidgets import ToolButton, Slider, FluentIcon as FIF

from app.widgets.basic_widget.combo_widget import CustomComboBox


class MiniAudioPlayer(QtWidgets.QWidget):
    """
    适配 PyQt5 的自定义迷你音频播放器 (带音量控制)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)

        # --- 1. 初始化播放器 ---
        self.player = QMediaPlayer(self)
        self.player.setVolume(50)  # 默认 50% 音量

        self.is_slider_pressed = False
        self.last_volume = 50  # 用于记录静音前的音量

        # --- 2. 初始化 UI 界面 ---
        self._init_ui()

        # --- 3. 信号连接 ---
        self._connect_signals()

    def _init_ui(self):
        self.h_layout = QtWidgets.QHBoxLayout(self)
        self.h_layout.setContentsMargins(10, 5, 10, 5)
        self.h_layout.setSpacing(8)  # 稍微调小间距以容纳更多控件

        # 1. 播放/暂停按钮
        self.playBtn = ToolButton(FIF.PLAY, self)
        self.playBtn.setFixedSize(30, 30)
        self.playBtn.setIconSize(QSize(14, 14))

        # 2. 当前时间
        self.lblCurrent = QtWidgets.QLabel("00:00", self)
        self.lblCurrent.setStyleSheet("color: #666; font-size: 12px;")

        # 3. 进度条 (自适应宽度)
        self.slider = Slider(Qt.Horizontal, self)
        self.slider.setRange(0, 0)
        self.slider.setMinimumWidth(200)
        # 4. 总时长
        self.lblTotal = QtWidgets.QLabel("00:00", self)
        self.lblTotal.setStyleSheet("color: #666; font-size: 12px;")

        # --- 新增音量控制部分 ---

        # 5. 音量按钮 (点击静音)
        self.volumeBtn = ToolButton(FIF.VOLUME, self)
        self.volumeBtn.setFixedSize(28, 28)
        self.volumeBtn.setIconSize(QSize(14, 14))

        # 6. 音量滑块 (固定宽度，比较短)
        self.volumeSlider = Slider(Qt.Horizontal, self)
        self.volumeSlider.setFixedSize(100, 28)  # 宽度60，高度和按钮对其
        self.volumeSlider.setRange(0, 100)
        self.volumeSlider.setValue(50)

        # 添加到布局
        self.h_layout.addWidget(self.playBtn)
        self.h_layout.addWidget(self.lblCurrent)
        self.h_layout.addWidget(self.slider, 1)  # 1 表示拉伸
        self.h_layout.addWidget(self.lblTotal)

        # 分割线或间距 (可选)
        self.h_layout.addSpacing(5)

        self.h_layout.addWidget(self.volumeBtn)
        self.h_layout.addWidget(self.volumeSlider)

    def _connect_signals(self):
        # 播放控制
        self.playBtn.clicked.connect(self._toggle_play)

        # 播放器回调
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.stateChanged.connect(self._on_state_changed)

        # 进度滑块交互
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        self.slider.valueChanged.connect(self._on_slider_moved)

        # --- 音量交互 ---
        self.volumeSlider.valueChanged.connect(self._on_volume_changed)
        self.volumeBtn.clicked.connect(self._toggle_mute)

    def set_source(self, file_path):
        self.stop()
        if not os.path.exists(file_path):
            return

        url = QUrl.fromLocalFile(file_path)
        content = QMediaContent(url)
        self.player.setMedia(content)

        self.playBtn.setIcon(FIF.PLAY)
        self.playBtn.setEnabled(True)

    def play(self):
        self.player.play()

    def stop(self):
        self.player.stop()
        self.playBtn.setIcon(FIF.PLAY)
        self.slider.setValue(0)
        self.lblCurrent.setText("00:00")

    def _toggle_play(self):
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_state_changed(self, state):
        if state == QMediaPlayer.PlayingState:
            self.playBtn.setIcon(FIF.PAUSE)
        else:
            self.playBtn.setIcon(FIF.PLAY)

    def _on_duration_changed(self, duration):
        self.slider.setRange(0, duration)
        self.lblTotal.setText(self._format_time(duration))

    def _on_position_changed(self, position):
        if not self.is_slider_pressed:
            self.slider.setValue(position)
        self.lblCurrent.setText(self._format_time(position))

    def _on_slider_pressed(self):
        self.is_slider_pressed = True

    def _on_slider_released(self):
        self.is_slider_pressed = False
        self.player.setPosition(self.slider.value())

    def _on_slider_moved(self, value):
        if self.is_slider_pressed:
            self.lblCurrent.setText(self._format_time(value))

    def _on_media_status_changed(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self.playBtn.setIcon(FIF.PLAY)

    # --- 音量控制逻辑 ---

    def _on_volume_changed(self, value):
        """滑块拖动时调用"""
        self.player.setMuted(False)  # 只要动了滑块，就取消静音
        self.player.setVolume(value)

        # 更新图标状态
        if value == 0:
            self.volumeBtn.setIcon(FIF.MUTE)
        else:
            self.volumeBtn.setIcon(FIF.VOLUME)

    def _toggle_mute(self):
        """点击喇叭图标时调用"""
        if self.player.isMuted() or self.volumeSlider.value() == 0:
            # 恢复音量
            self.player.setMuted(False)
            vol = self.last_volume if self.last_volume > 0 else 50
            self.volumeSlider.setValue(vol)
            self.volumeBtn.setIcon(FIF.VOLUME)
        else:
            # 静音
            self.last_volume = self.volumeSlider.value()  # 记住当前音量
            self.player.setMuted(True)
            self.volumeSlider.setValue(0)  # 视觉上归零
            self.volumeBtn.setIcon(FIF.MUTE)

    @staticmethod
    def _format_time(ms):
        seconds = (ms // 1000) % 60
        minutes = (ms // 60000)
        return f"{minutes:02d}:{seconds:02d}"


class AudioPlayWidget(QtWidgets.QWidget):
    valueChanged = QtCore.pyqtSignal(object)
    sizeHintChanged = QtCore.pyqtSignal()
    EXTS = ['.mp3', '.wav', '.flac', '.m4a', '.ogg']
    fixed_height = True

    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_path = None

        # 1. 布局设置
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 2. 替换为自定义的 MiniAudioPlayer
        self.playerWidget = MiniAudioPlayer(self)
        self.main_layout.addWidget(self.playerWidget)

        # 初始状态隐藏
        self.playerWidget.hide()

    def set_value(self, file_path):
        """传入本地文件路径"""
        if self._file_path == file_path:
            return

        self.stop()
        self._file_path = file_path

        if not file_path or not os.path.exists(file_path):
            self.playerWidget.hide()
            self._update_node_size()
            return

        ext = os.path.splitext(file_path)[1].lower()

        if ext in self.EXTS:
            self.playerWidget.show()
            self.playerWidget.set_source(file_path)
        else:
            self.playerWidget.hide()

        self._update_node_size()
        self.valueChanged.emit(file_path)

    def _update_node_size(self):
        """通知节点更新尺寸"""
        self.updateGeometry()
        self.sizeHintChanged.emit()

    def play(self):
        self.playerWidget.play()

    def stop(self):
        self.playerWidget.stop()

    def get_value(self):
        return self._file_path

    def sizeHint(self):
        # 动态计算尺寸：如果不显示，高度为0（或者极小）
        if self._file_path and not self.playerWidget.isHidden():
            return QSize(250, 50)  # 宽度可以稍微大一点，高度固定50
        return QSize(250, 0)  # 没有文件时尽量收缩

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