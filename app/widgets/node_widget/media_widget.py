# -*- coding: utf-8 -*-
import os
import cv2
from PyQt5 import QtWidgets
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QSize
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import QUrl
from Qt import QtWidgets, QtCore
from qfluentwidgets import BodyLabel, Slider
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


# --- 1. 后台加载线程 (逻辑保持不变，依然是极致性能的核心) ---
class VideoLoaderThread(QThread):
    meta_ready = pyqtSignal(int, int, float, int)
    frame_ready = pyqtSignal(bytes)

    def __init__(self, file_path, max_width=512, max_frames=120):
        super().__init__()
        self.file_path = file_path
        self.max_width = max_width
        self.max_frames = max_frames
        self._is_running = True

    def run(self):
        cap = cv2.VideoCapture(self.file_path)
        if not cap.isOpened(): return

        raw_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        raw_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if total_frames <= 0: total_frames = 0
        if fps <= 0: fps = 24.0

        if raw_w > 0 and raw_h > 0:
            aspect_ratio = raw_h / raw_w
            target_w = self.max_width
            target_h = int(target_w * aspect_ratio)
        else:
            target_w = self.max_width
            target_h = int(target_w * 9 / 16)

        step = max(1, total_frames // self.max_frames)
        self.meta_ready.emit(target_w, target_h, fps, step)

        current_frame = 0
        count = 0
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 75]

        while self._is_running and cap.isOpened():
            cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
            ret, frame = cap.read()
            if not ret: break
            try:
                frame = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
                success, encoded_img = cv2.imencode('.jpg', frame, encode_param)
                if success:
                    self.frame_ready.emit(encoded_img.tobytes())
            except:
                pass
            count += 1
            current_frame += step
            if count >= self.max_frames: break
        cap.release()

    def stop(self):
        self._is_running = False
        self.wait()


# --- 2. 辅助控件：带数值显示的 Slider ---
class ComfySlider(QtWidgets.QWidget):
    """封装了 Label + Slider 的组合控件"""
    valueChanged = pyqtSignal(float)  # 实时值变化
    valueConfirmed = pyqtSignal(float)  # 鼠标松开确认值

    def __init__(self, label_text, min_v, max_v, default_v, is_float=False, suffix=""):
        super().__init__()
        self.is_float = is_float
        self.suffix = suffix
        self.factor = 100 if is_float else 1  # 浮点数通过放大倍数转整数处理

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # 标签
        self.lbl_name = BodyLabel(label_text)

        # 滑块
        self.slider = Slider(Qt.Horizontal)
        self.slider.setRange(int(min_v * self.factor), int(max_v * self.factor))
        self.slider.setValue(int(default_v * self.factor))
        self.slider.setCursor(Qt.PointingHandCursor)

        # 数值显示
        self.lbl_val = BodyLabel()
        self.lbl_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._update_label(self.slider.value())

        layout.addWidget(self.lbl_name)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.lbl_val)

        # 信号连接
        self.slider.valueChanged.connect(self._on_change)
        self.slider.sliderReleased.connect(self._on_release)

    def _on_change(self, val):
        real_val = val / self.factor
        self._update_label(val)
        self.valueChanged.emit(real_val)

    def _on_release(self):
        val = self.slider.value() / self.factor
        self.valueConfirmed.emit(val)

    def _update_label(self, raw_val):
        val = raw_val / self.factor
        if self.is_float:
            self.lbl_val.setText(f"{val:.1f}{self.suffix}")
        else:
            self.lbl_val.setText(f"{int(val)}{self.suffix}")


# --- 3. ComfyUI 风格控制面板 (重构版) ---
class ComfyConfigPanel(QtWidgets.QFrame):
    # 信号：(width, max_frames)
    reloadRequested = pyqtSignal(int, int)
    speedChanged = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            ComfyConfigPanel { background: #222; border-bottom: 1px solid #333; }
            QLabel { color: #888; font-family: Consolas, monospace; font-size: 10px; }

            /* ComfyUI 风格滑块样式 */
            QSlider::groove:horizontal {
                border: 1px solid #333;
                height: 4px;
                background: #111;
                margin: 0px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #555;
                border: 1px solid #555;
                width: 10px;
                height: 10px;
                margin: -4px 0; /* 把手柄垂直居中 */
                border-radius: 5px;
            }
            QSlider::handle:horizontal:hover { background: #00A6FF; border-color: #00A6FF; }
            QSlider::sub-page:horizontal { background: #333; border-radius: 2px; }

            /* 下拉框 */
            QComboBox {
                background: #151515; color: #DDD; border: 1px solid #333; border-radius: 2px;
                padding: 0px 4px; font-size: 10px; height: 16px;
            }
            QComboBox::drop-down { border: none; width: 14px; }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # --- 第一行：分辨率 + 帧数控制 ---
        row1 = QtWidgets.QHBoxLayout()

        # 分辨率
        self.lbl_res = BodyLabel("分辨率:")
        self.combo_res = CustomComboBox()
        self.combo_res.addItems(["Low", "Mid", "High", "Full"])
        self.combo_res.setCurrentIndex(1)  # Mid
        self.combo_res.setToolTip("预览分辨率 (Low:320, Mid:512...)")

        # 帧数滑块 (范围 20 - 300)
        self.slider_frames = ComfySlider("视频长度", 20, 300, 100, is_float=False, suffix="f")
        row1.addWidget(self.lbl_res)
        row1.addWidget(self.combo_res)
        row1.addSpacing(4)
        row1.addWidget(self.slider_frames)

        # --- 第二行：播放速度 ---
        row2 = QtWidgets.QHBoxLayout()
        # 速度滑块 (范围 0.1 - 5.0)
        self.slider_speed = ComfySlider("视频速度", 0.1, 5.0, 1.0, is_float=True, suffix="x")
        row2.addWidget(self.slider_speed)

        layout.addLayout(row1)
        layout.addLayout(row2)

        # 逻辑连接
        # 1. 分辨率改变 -> 立即重载
        self.combo_res.currentIndexChanged.connect(self._request_reload)

        # 2. 帧数滑块 -> 只有松开鼠标时才重载 (避免卡顿)
        self.slider_frames.valueConfirmed.connect(lambda v: self._request_reload())

        # 3. 速度滑块 -> 实时改变 (无需重载)
        self.slider_speed.valueChanged.connect(self.speedChanged.emit)

    def _request_reload(self):
        # 映射分辨率
        idx = self.combo_res.currentIndex()
        widths = [320, 512, 720, 1920]
        w = widths[idx]

        f = int(self.slider_frames.slider.value())  # 直接读滑块当前值
        self.reloadRequested.emit(w, f)


# --- 4. 主视频节点控件 (集成新面板) ---
class VideoPlayWidget(QtWidgets.QFrame):
    sizeHintChanged = pyqtSignal()
    clicked = pyqtSignal(str)

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

    def _trigger_reload(self, width, frames):
        """重新加载视频数据"""
        if not self._file_path: return

        self.playback_timer.stop()
        if self._loader_thread:
            self._loader_thread.stop()
            self._loader_thread.wait()

        self._compressed_cache = []
        self._current_idx = 0
        self.img_label.setText("Loading...")
        self.img_label.setStyleSheet("color: #555; font-size: 10px;")

        self._loader_thread = VideoLoaderThread(self._file_path, max_width=width, max_frames=frames)
        self._loader_thread.meta_ready.connect(self._on_meta_ready)
        self._loader_thread.frame_ready.connect(self._on_frame_buffer)
        self._loader_thread.start()

    def _on_meta_ready(self, img_w, img_h, fps, step):
        # 计算新尺寸
        panel_h = self.config_bar.sizeHint().height()  # 自动获取面板高度
        total_h = img_h + panel_h

        if fps > 0:
            self._base_interval = int((1000 * step) / fps)
        else:
            self._base_interval = 100

        self._update_speed(self._speed_multiplier)  # 重新应用速度

        # 调整大小并通知父级
        self.setFixedSize(img_w, total_h)
        self.sizeHintChanged.emit()
        self.updateGeometry()

    def _on_frame_buffer(self, jpeg_bytes):
        self._compressed_cache.append(jpeg_bytes)
        if len(self._compressed_cache) == 2:  # 缓冲2帧即播
            if not self.playback_timer.isActive():
                self.playback_timer.start(self._base_interval)
        if len(self._compressed_cache) == 1:
            self._render(jpeg_bytes)

    def _update_speed(self, val):
        self._speed_multiplier = val
        if val > 0:
            real_interval = int(self._base_interval / val)
            real_interval = max(10, real_interval)
            self.playback_timer.setInterval(real_interval)

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