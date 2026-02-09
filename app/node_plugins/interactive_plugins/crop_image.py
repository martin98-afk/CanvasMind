# -*- coding: utf-8 -*-
import base64
import os
import pickle
import tempfile
import uuid

from PyQt5.QtCore import Qt, QPoint, QPointF, QRectF, QByteArray, QBuffer, QIODevice
from PyQt5.QtGui import (
    QImage, QPixmap, QPainter, QPen, QColor, QRegion
)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QDialog
)
from loguru import logger
from qfluentwidgets import (
    Slider, StrongBodyLabel, PrimaryPushButton
)

from app.node_plugins.base import InteractivePlugin
from app.utils.config import Settings
from app.utils.utils import ssh_send_file


class CropCanvas(QWidget):
    def __init__(self, base64_image=None, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.original_pixmap = None
        self.original_image = None  # 保留QImage用于高精度截取
        self.scale_factor = 1.0
        self.offset = QPointF(0, 0)
        self.first_show = True

        self.is_panning = False
        self.last_mouse_pos = QPoint()

        # 裁切框大小 (默认 512x512)
        self.crop_w = 512
        self.crop_h = 512

        if base64_image:
            self.load_image(base64_image)

    def load_image(self, b64):
        try:
            if "," in b64: b64 = b64.split(",")[-1]
            data = base64.b64decode(b64)
            img = QImage.fromData(data)
            if img.isNull(): return

            self.original_image = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)
            self.original_pixmap = QPixmap.fromImage(self.original_image)

            self.fit_view()
            self.update()
        except Exception as e:
            logger.exception(f"Error loading image: {e}")

    def fit_view(self):
        if not self.original_pixmap or self.width() <= 0: return
        iw, ih = self.original_pixmap.width(), self.original_pixmap.height()
        ww, wh = self.width(), self.height()
        # 初始适应窗口
        self.scale_factor = min(ww / iw, wh / ih) * 0.9
        # 居中
        self.offset = QPointF((ww - iw * self.scale_factor) / 2, (wh - ih * self.scale_factor) / 2)
        self.update()

    def resizeEvent(self, event):
        if self.first_show and self.width() > 100:
            self.fit_view()
            self.first_show = False
        super().resizeEvent(event)

    def set_crop_size(self, w, h):
        self.crop_w = w
        self.crop_h = h
        self.update()

    def get_crop_rect(self):
        # 计算屏幕中心的裁切框区域
        cx, cy = self.width() / 2, self.height() / 2
        return QRectF(cx - self.crop_w / 2, cy - self.crop_h / 2, self.crop_w, self.crop_h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(20, 20, 20))  # 深色背景

        if not self.original_pixmap: return

        # 1. 绘制底图
        painter.save()
        painter.translate(self.offset)
        painter.scale(self.scale_factor, self.scale_factor)

        if self.scale_factor < 1.0 and not self.is_panning:
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        painter.drawPixmap(0, 0, self.original_pixmap)
        painter.restore()

        # 2. 绘制遮罩层（挖空的黑色遮罩）
        # 整个窗口区域
        full_region = QRegion(self.rect())
        # 中间的裁切框区域
        crop_rect = self.get_crop_rect().toRect()
        crop_region = QRegion(crop_rect)
        # 相减得到“中间透亮，四周变暗”的区域
        mask_region = full_region.subtracted(crop_region)

        painter.setClipRegion(mask_region)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 180))  # 遮罩颜色
        painter.setClipping(False)

        # 3. 绘制裁切框边框
        painter.setPen(QPen(QColor(255, 0, 100), 2, Qt.SolidLine))  # 亮红色边框
        painter.drawRect(crop_rect)

        # 绘制尺寸文字
        painter.setPen(Qt.white)
        painter.drawText(crop_rect.topLeft() - QPoint(0, 5), f"{self.crop_w} x {self.crop_h}")

    def mouseMoveEvent(self, e):
        if self.is_panning:
            self.offset += QPointF(e.pos() - self.last_mouse_pos)
            self.last_mouse_pos = e.pos()
            self.update()

    def mousePressEvent(self, e):
        self.last_mouse_pos = e.pos()
        if e.button() == Qt.LeftButton or e.button() == Qt.MiddleButton:
            self.is_panning = True

    def mouseReleaseEvent(self, e):
        self.is_panning = False

    def wheelEvent(self, e):
        # 缩放底图
        delta = 1.1 if e.angleDelta().y() > 0 else 1 / 1.1
        new_scale = max(0.01, min(self.scale_factor * delta, 50.0))

        # 以鼠标位置为中心缩放
        mouse_pos = QPointF(e.pos())
        self.offset = mouse_pos - (mouse_pos - self.offset) * (new_scale / self.scale_factor)
        self.scale_factor = new_scale
        self.update()

    def get_cropped_result(self):
        """核心裁切逻辑"""
        if not self.original_image: return None

        # 1. 获取屏幕上的裁切框
        screen_crop_rect = self.get_crop_rect()

        # 2. 映射回原图坐标系
        # 公式: ImageX = (ScreenX - OffsetX) / Scale
        img_x = (screen_crop_rect.x() - self.offset.x()) / self.scale_factor
        img_y = (screen_crop_rect.y() - self.offset.y()) / self.scale_factor
        img_w = screen_crop_rect.width() / self.scale_factor
        img_h = screen_crop_rect.height() / self.scale_factor

        # 3. 从原图中截取 (保持 float 精度截取，防止抖动)
        # QImage copy 需要整数，所以先用 transform
        # 这里为了高质量，我们先截取一个包含该区域的整数矩形，再 resize
        src_rect = QRectF(img_x, img_y, img_w, img_h).toRect()

        # 边界保护
        # 如果选区超出了图片，QImage.copy 会自动处理黑边，但我们需要确保逻辑正确
        cropped_source = self.original_image.copy(src_rect)

        # 4. 缩放到用户指定的目标大小 (self.crop_w, self.crop_h)
        # 这一步实现了“放大”或“缩小”到指定分辨率
        final_img = cropped_source.scaled(
            self.crop_w, self.crop_h,
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation
        )

        return final_img


class CropEditor(QWidget):
    def __init__(self, image_b64, parent=None):
        super().__init__(parent)

        # 主布局
        self.lyt = QVBoxLayout(self)
        self.lyt.setContentsMargins(0, 0, 0, 0)
        self.lyt.setSpacing(0)

        # 1. 顶部控制栏
        self.control_panel = QFrame(self)
        self.control_panel.setStyleSheet("background: #2b2b2b; border-bottom: 1px solid #444;")
        self.control_panel.setFixedHeight(60)

        cp_lyt = QHBoxLayout(self.control_panel)
        cp_lyt.setContentsMargins(20, 5, 20, 5)

        # 宽度滑块
        cp_lyt.addWidget(StrongBodyLabel("宽度:"))
        self.sld_w = Slider(Qt.Horizontal)
        self.sld_w.setRange(64, 2048)
        self.sld_w.setValue(512)
        self.sld_w.setFixedWidth(200)
        cp_lyt.addWidget(self.sld_w)
        self.lbl_w_val = StrongBodyLabel("512 px")
        self.lbl_w_val.setFixedWidth(60)
        cp_lyt.addWidget(self.lbl_w_val)

        cp_lyt.addSpacing(30)

        # 高度滑块
        cp_lyt.addWidget(StrongBodyLabel("高度:"))
        self.sld_h = Slider(Qt.Horizontal)
        self.sld_h.setRange(64, 2048)
        self.sld_h.setValue(512)
        self.sld_h.setFixedWidth(200)
        cp_lyt.addWidget(self.sld_h)
        self.lbl_h_val = StrongBodyLabel("512 px")
        self.lbl_h_val.setFixedWidth(60)
        cp_lyt.addWidget(self.lbl_h_val)

        cp_lyt.addStretch()

        # 2. 中间画布
        self.canvas = CropCanvas(image_b64, self)

        self.lyt.addWidget(self.control_panel)
        self.lyt.addWidget(self.canvas)

        # 信号连接
        self.sld_w.valueChanged.connect(self.on_size_changed)
        self.sld_h.valueChanged.connect(self.on_size_changed)

    def on_size_changed(self):
        w = self.sld_w.value()
        h = self.sld_h.value()
        self.lbl_w_val.setText(f"{w} px")
        self.lbl_h_val.setText(f"{h} px")
        self.canvas.set_crop_size(w, h)


class CropImageDialog(QDialog):
    def __init__(self, title, image, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1200, 750)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint)
        self.setStyleSheet("""
            QDialog { background-color: #1a1a1a; }
            QLabel { color: white; }
        """)

        self.main_lyt = QVBoxLayout(self)
        self.main_lyt.setContentsMargins(0, 0, 0, 0)
        self.main_lyt.setSpacing(0)

        # 标题栏
        self.head_panel = QFrame()
        self.head_panel.setFixedHeight(50)
        self.head_panel.setStyleSheet("background-color: #252525; border-bottom: 1px solid #333;")
        head_lyt = QHBoxLayout(self.head_panel)
        self.title_label = StrongBodyLabel(title)
        head_lyt.addWidget(self.title_label)
        head_lyt.addStretch()
        self.main_lyt.addWidget(self.head_panel)

        # 编辑器
        self.editor = CropEditor(image, self)
        self.main_lyt.addWidget(self.editor)

        # 底部按钮
        self.bottom_panel = QFrame()
        self.bottom_panel.setFixedHeight(60)
        self.bottom_panel.setStyleSheet("background-color: #252525; border-top: 1px solid #333;")
        bot_lyt = QHBoxLayout(self.bottom_panel)

        self.btn_save = PrimaryPushButton("确认裁切并保存")
        self.btn_save.setFixedWidth(200)
        self.btn_save.clicked.connect(self.accept)

        bot_lyt.addStretch()
        bot_lyt.addWidget(self.btn_save)
        bot_lyt.addStretch()

        self.main_lyt.addWidget(self.bottom_panel)

    def get_result(self):
        img = self.editor.canvas.get_cropped_result()
        if img:
            # --- 修改开始 ---
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.WriteOnly)
            img.save(buf, "PNG")

            # 将 QByteArray 转为 base64 字符串
            # ba.toBase64() 返回 QByteArray，需转 bytes 再解码
            img_str = bytes(ba.toBase64()).decode("utf-8")
            # --- 修改结束 ---

            return {"image": f"data:image/png;base64,{img_str}"}
        return None


class CropImagePlugin(InteractivePlugin):
    plugin_id = "crop_image"
    plugin_name = "图像放大裁切"
    plugin_desc = "打开裁切窗口，设置宽高并拖动图片，截取视窗内的图片并返回。"
    plugin_template = """buffered = BytesIO()
        # 自动处理 RGBA 模式保存为 PNG（避免 JPEG 无法保存 alpha）
        format = "PNG"  # 强制含透明通道的图用 PNG
        img.save(buffered, format=format)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        mime = "image/jpeg" if format.upper() in ("JPG", "JPEG") else "image/png"
        base64_image = f"data:{mime};base64,{img_str}"
        # 触发ui出现遮罩绘制窗口
        result = self.emit_interactive_message(
            method="crop_image",
            params={"title": "请拖拽画布以选择最终裁切图像","schema": {"image": base64_image,}}
        )["image"]   # 输出结果会带前缀 data:{mime};base64, 建议后续转换用split(',')获取图像数据
"""

    def handle(self, node, params, msg=None):
        title = params.get("title", "图像裁切工具")
        response_file = params.get("response_file")
        image = params.get("schema").get("image")

        env_data = getattr(node.parent_window, 'env_data', None)
        is_ssh = env_data and env_data.get('type') == 'ssh'

        def on_confirmed(result_data):
            if not result_data: return

            if is_ssh:
                temp_path = os.path.join(tempfile.gettempdir(), f"crop_{uuid.uuid4().hex}.pkl")
                with open(temp_path, 'wb') as f:
                    pickle.dump(result_data, f)
                ssh_send_file(env_data, temp_path, response_file)
                if os.path.exists(temp_path): os.remove(temp_path)
            else:
                os.makedirs(os.path.dirname(response_file), exist_ok=True)
                with open(response_file, 'wb') as f:
                    pickle.dump(result_data, f)

        dialog = CropImageDialog(title, image, node.parent_window)
        if dialog.exec():
            if Settings.get_instance().communication_method.value == "ZMQ通信":
                return dialog.get_result()
            else:
                on_confirmed(dialog.get_result())
        return None