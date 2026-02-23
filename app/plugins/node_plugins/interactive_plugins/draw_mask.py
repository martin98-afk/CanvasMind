# -*- coding: utf-8 -*-
import base64

import cv2
import numpy as np
from PyQt5.QtCore import Qt, QPoint, QPointF, QByteArray, QBuffer
from PyQt5.QtGui import (
    QImage, QPixmap, QPainter, QPen, QColor
)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QDialog
)
from loguru import logger
from qfluentwidgets import ToolButton, Slider, FluentIcon, StrongBodyLabel, \
    PrimaryPushButton

from app.plugins.node_plugins.base import InteractivePlugin
from app.utils.utils import get_icon


class MaskCanvas(QWidget):
    def __init__(self, base64_image=None, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.original_pixmap = None
        self.mask_image = None
        self.scale_factor = 1.0
        self.offset = QPointF(0, 0)
        self.first_show = True

        self.draw_mode = "brush"  # brush, eraser, fill
        self.brush_size = 40
        self.mask_color = QColor(255, 0, 100, 160)

        self.is_drawing = False
        self.is_panning = False
        self.last_mouse_pos = QPoint()
        self.mouse_now = QPoint()

        self.undo_stack = []

        if base64_image:
            self.load_image(base64_image)

    def load_image(self, b64):
        try:
            if "," in b64: b64 = b64.split(",")[-1]
            data = base64.b64decode(b64)
            img = QImage.fromData(data)
            if img.isNull(): return

            # 1. 统一原图格式
            img = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)
            self.original_pixmap = QPixmap.fromImage(img)

            w, h = img.width(), img.height()

            # 2. 初始化遮罩层（全透明）
            self.mask_image = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
            self.mask_image.fill(Qt.transparent)

            # 3. 智能识别：是“扣底图”还是“实心图”？
            if img.hasAlphaChannel():
                ptr_src = img.constBits()
                ptr_src.setsize(img.byteCount())
                # 获取原图 Alpha 通道
                src_arr = np.frombuffer(ptr_src, np.uint8).reshape((h, w, 4))
                alpha_channel = src_arr[:, :, 3]

                # 【关键修复】检查是否存在透明像素
                # 如果最小值也是 255，说明整张图都是实心的（没有透明背景），此时不应该生成遮罩
                min_alpha = np.min(alpha_channel)

                if min_alpha < 250:  # 只有当存在透明区域时，才执行自动遮罩
                    # 逻辑：原图不透明的地方(Alpha>0) -> 变成遮罩色
                    mask_indices = alpha_channel > 0

                    if np.any(mask_indices):
                        ptr_mask = self.mask_image.bits()
                        ptr_mask.setsize(self.mask_image.byteCount())
                        mask_arr = np.frombuffer(ptr_mask, np.uint8).reshape((h, w, 4))

                        # 计算预乘颜色
                        c = self.mask_color
                        a = c.alpha()
                        r = int(c.red() * (a / 255))
                        g = int(c.green() * (a / 255))
                        b = int(c.blue() * (a / 255))

                        # 赋值
                        mask_arr[mask_indices] = [b, g, r, a]

            self.fit_view()
            self.update()
        except Exception as e:
            logger.exception(f"Error loading image: {e}")

    def fit_view(self):
        if not self.original_pixmap or self.width() <= 0: return
        iw, ih = self.original_pixmap.width(), self.original_pixmap.height()
        ww, wh = self.width(), self.height()
        self.scale_factor = min(ww / iw, wh / ih) * 0.95
        self.offset = QPointF((ww - iw * self.scale_factor) / 2, (wh - ih * self.scale_factor) / 2)
        self.update()

    def resizeEvent(self, event):
        if self.first_show and self.width() > 100:
            self.fit_view()
            self.first_show = False
        super().resizeEvent(event)

    def to_img_pos(self, p):
        return (QPointF(p) - self.offset) / self.scale_factor

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(15, 15, 15))

        if not self.original_pixmap: return

        # 1. 绘制底图和蒙版
        painter.save()
        painter.translate(self.offset)
        painter.scale(self.scale_factor, self.scale_factor)

        # 【性能优化】只有在静止状态（不拖拽、不绘画）时才开启平滑抗锯齿
        if not self.is_panning and not self.is_drawing and self.scale_factor < 1.0:
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        else:
            painter.setRenderHint(QPainter.SmoothPixmapTransform, False)

        painter.drawPixmap(0, 0, self.original_pixmap)
        painter.drawImage(0, 0, self.mask_image)
        painter.restore()

        # 2. 画笔圆圈实时预览
        if not self.is_panning and self.draw_mode != "fill":
            painter.setRenderHint(QPainter.Antialiasing)
            r = (self.brush_size * self.scale_factor) / 2
            painter.setPen(QPen(Qt.white, 1.2))
            painter.drawEllipse(self.mouse_now, r, r)
            painter.setPen(QPen(Qt.black, 1.0, Qt.DotLine))
            painter.drawEllipse(self.mouse_now, r + 1, r + 1)

    def mouseMoveEvent(self, e):
        self.mouse_now = e.pos()
        if self.is_panning:
            self.offset += QPointF(e.pos() - self.last_mouse_pos)
            self.last_mouse_pos = e.pos()
        elif self.is_drawing:
            p1 = self.to_img_pos(self.last_mouse_pos)
            p2 = self.to_img_pos(e.pos())
            self.draw_line(p1, p2)
            self.last_mouse_pos = e.pos()
        self.update()

    def mousePressEvent(self, e):
        self.last_mouse_pos = e.pos()
        if e.button() == Qt.MiddleButton or (e.button() == Qt.LeftButton and e.modifiers() & Qt.AltModifier):
            self.is_panning = True
            return

        if e.button() == Qt.LeftButton:
            self.push_undo()
            img_pos = self.to_img_pos(e.pos())
            if self.draw_mode == "fill":
                self.flood_fill(img_pos.toPoint())
            else:
                self.is_drawing = True
                self.draw_at(img_pos)
            self.update()

    def mouseReleaseEvent(self, e):
        self.is_drawing = False
        self.is_panning = False

    def wheelEvent(self, e):
        delta = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        new_scale = max(0.01, min(self.scale_factor * delta, 50.0))
        self.offset = QPointF(e.pos()) - (QPointF(e.pos()) - self.offset) * (new_scale / self.scale_factor)
        self.scale_factor = new_scale
        self.update()

    def draw_at(self, pos):
        p = QPainter(self.mask_image)
        p.setRenderHint(QPainter.Antialiasing)
        p.setCompositionMode(
            QPainter.CompositionMode_SourceOver if self.draw_mode == "brush" else QPainter.CompositionMode_Clear)
        p.setBrush(self.mask_color)
        p.setPen(Qt.NoPen)
        p.drawEllipse(pos, self.brush_size / 2, self.brush_size / 2)

    def draw_line(self, p1, p2):
        p = QPainter(self.mask_image)
        p.setRenderHint(QPainter.Antialiasing)
        if self.draw_mode == "brush":
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            pen = QPen(self.mask_color, self.brush_size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        else:
            p.setCompositionMode(QPainter.CompositionMode_Clear)
            pen = QPen(Qt.transparent, self.brush_size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.drawLine(p1, p2)

    def flood_fill(self, start_pt):
        """修复颜色不一致的高性能填充"""
        w, h = self.mask_image.width(), self.mask_image.height()
        sx, sy = start_pt.x(), start_pt.y()
        if not (0 <= sx < w and 0 <= sy < h): return

        # 获取数据指针
        ptr = self.mask_image.bits() # 注意这里用 bits() 只有读写权限
        ptr.setsize(self.mask_image.byteCount())
        img_arr = np.frombuffer(ptr, np.uint8).reshape((h, w, 4))

        # 检查点击位置是否已经是遮罩色 (避免重复计算)
        # 比较 Alpha 值即可
        if img_arr[sy, sx, 3] > 10: return

        # 准备 OpenCV 填充用的 mask
        # 提取当前遮罩的 alpha 通道作为屏障
        current_alpha = img_arr[:, :, 3].copy()
        h_mask, w_mask = h + 2, w + 2
        fill_mask = np.zeros((h_mask, w_mask), np.uint8)

        # 填充算法 (loDiff/upDiff 控制容差)
        cv2.floodFill(current_alpha, fill_mask, (sx, sy), 255, loDiff=5, upDiff=5)

        # 提取填充区域
        filled_region = fill_mask[1:-1, 1:-1] == 1

        # 【关键修复】应用预乘颜色，使其与画笔一致
        c = self.mask_color
        a = c.alpha()
        # 必须进行预乘： C_new = C_origin * (Alpha / 255)
        r = int(c.red() * (a / 255))
        g = int(c.green() * (a / 255))
        b = int(c.blue() * (a / 255))

        # 赋值 [B, G, R, A]
        img_arr[filled_region] = [b, g, r, a]

        # 触发重绘
        self.update()

    def invert_mask(self):
        """高性能遮罩取反"""
        self.push_undo()  # 记录撤销

        w, h = self.mask_image.width(), self.mask_image.height()

        # 获取内存视图
        ptr = self.mask_image.bits()
        ptr.setsize(self.mask_image.byteCount())
        img_arr = np.frombuffer(ptr, np.uint8).reshape((h, w, 4))

        # 1. 识别区域
        # Alpha通道为0的是“未遮罩区”，大于0的是“已遮罩区”
        alpha_channel = img_arr[:, :, 3]
        to_fill_indices = alpha_channel == 0  # 原本透明的地方 -> 需要填色
        to_clear_indices = alpha_channel > 0  # 原本有色的地方 -> 需要清空

        # 2. 准备遮罩颜色 (预乘处理，确保颜色一致)
        c = self.mask_color
        a = c.alpha()
        r = int(c.red() * (a / 255))
        g = int(c.green() * (a / 255))
        b = int(c.blue() * (a / 255))

        # 3. 执行取反 (直接操作内存，毫秒级)
        # 先把原本有色的清空
        img_arr[to_clear_indices] = 0
        # 再把原本透明的填满
        img_arr[to_fill_indices] = [b, g, r, a]

        self.update()

    def push_undo(self):
        if len(self.undo_stack) > 30: self.undo_stack.pop(0)
        self.undo_stack.append(self.mask_image.copy())

    def undo(self):
        if self.undo_stack:
            self.mask_image = self.undo_stack.pop()
            self.update()

    def clear(self):
        """修复 AttributeError 的关键函数"""
        self.push_undo()
        self.mask_image.fill(Qt.transparent)
        self.update()


class ComfyToolButton(ToolButton):

    def __init__(self, icon, tip, parent=None):
        super().__init__(parent)
        if icon:
            self.setIcon(icon)
        else:
            self.setText(tip[:1])  # 回退文字

        self.setToolTip(tip)
        self.setFixedSize(45, 45)
        self.setCheckable(True)
        self.setStyleSheet("""
            QToolButton {
                background: rgba(40, 40, 40, 180);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 8px;
                color: white;
            }
            QToolButton:hover { background: rgba(80, 80, 80, 200); }
            QToolButton:checked { background: #ff0064; border: 1px solid white; }
        """)


class ComfyEditor(QWidget):
    def __init__(self, image_b64, parent=None):
        super().__init__(parent)
        self.canvas = MaskCanvas(image_b64, self)

        # 主布局
        self.lyt = QHBoxLayout(self)
        self.lyt.setContentsMargins(0, 0, 0, 0)
        self.lyt.addWidget(self.canvas)

        # 左悬浮面板
        self.left_panel = QFrame(self)
        self.left_panel.setStyleSheet("background: transparent;")
        lp_lyt = QVBoxLayout(self.left_panel)

        self.btn_brush = ComfyToolButton(get_icon("brush"), "画笔 (B)")
        self.btn_eraser = ComfyToolButton(get_icon("eraser"), "橡皮 (E)")
        self.btn_fill = ComfyToolButton(get_icon("fill"), "填充 (F)")

        self.btn_brush.setChecked(True)
        lp_lyt.addWidget(self.btn_brush)
        lp_lyt.addWidget(self.btn_eraser)
        lp_lyt.addWidget(self.btn_fill)

        # 笔刷滑块
        self.sld = Slider(Qt.Vertical)
        self.sld.setRange(2, 80)
        self.sld.setValue(30)
        self.sld.setStyleSheet("QSlider::handle:vertical { background: #ff0064; }")
        lp_lyt.addSpacing(10)
        lp_lyt.addWidget(self.sld, 0, Qt.AlignHCenter)
        lp_lyt.addWidget(StrongBodyLabel("画笔大小"), 0, Qt.AlignHCenter)

        # 右悬浮面板
        self.right_panel = QFrame(self)
        rp_lyt = QVBoxLayout(self.right_panel)
        rp_lyt.setSpacing(10)
        self.btn_undo = ComfyToolButton(FluentIcon.LEFT_ARROW, "撤销 (Ctrl+Z)")
        self.btn_reset = ComfyToolButton(get_icon("缩放"), "居中 (R)")
        self.btn_invert = ComfyToolButton(FluentIcon.SYNC, "反选遮罩 (I)")

        self.btn_clear = ComfyToolButton(FluentIcon.DELETE, "清空 (C)")

        self.btn_undo.setCheckable(False)
        self.btn_reset.setCheckable(False)
        self.btn_invert.setCheckable(False)  # 新增
        self.btn_clear.setCheckable(False)

        rp_lyt.addWidget(self.btn_undo)
        rp_lyt.addWidget(self.btn_reset)
        rp_lyt.addWidget(self.btn_invert)  # 新增
        rp_lyt.addWidget(self.btn_clear)
        rp_lyt.addStretch()

        # 信号
        self.btn_brush.clicked.connect(lambda: self.set_mode("brush"))
        self.btn_eraser.clicked.connect(lambda: self.set_mode("eraser"))
        self.btn_fill.clicked.connect(lambda: self.set_mode("fill"))
        self.btn_undo.clicked.connect(self.canvas.undo)
        self.btn_reset.clicked.connect(self.canvas.fit_view)
        self.btn_invert.clicked.connect(self.canvas.invert_mask)
        self.btn_clear.clicked.connect(self.canvas.clear)
        self.sld.valueChanged.connect(lambda v: setattr(self.canvas, 'brush_size', v))

    def set_mode(self, m):
        self.canvas.draw_mode = m
        self.btn_brush.setChecked(m == "brush")
        self.btn_eraser.setChecked(m == "eraser")
        self.btn_fill.setChecked(m == "fill")

    def resizeEvent(self, e):
        self.left_panel.setGeometry(20, 20, 60, 450)
        self.right_panel.setGeometry(self.width() - 80, 20, 60, 300)
        super().resizeEvent(e)


class MaskDrawDialog(QDialog):
    def __init__(self, title, image, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1200, 800)
        # 设置窗口标志：去掉帮助按钮，增加最大化最小化
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint)
        self.setStyleSheet("""
            QDialog { background-color: #1a1a1a; }
            QLabel { color: white; }
            QFrame#Toolbar { 
                background-color: rgba(45, 45, 45, 230); 
                border-radius: 10px;
            }
        """)

        self.main_lyt = QVBoxLayout(self)
        self.main_lyt.setContentsMargins(0, 0, 0, 0)
        self.main_lyt.setSpacing(0)

        # 标题栏区域
        self.head_panel = QFrame()
        self.head_panel.setFixedHeight(50)
        self.head_panel.setStyleSheet("background-color: #252525; border-bottom: 1px solid #333;")
        head_lyt = QHBoxLayout(self.head_panel)
        self.title_label = StrongBodyLabel(title)
        head_lyt.addWidget(self.title_label)
        head_lyt.addStretch()
        self.main_lyt.addWidget(self.head_panel)

        # 中间内容区
        self.content_container = ComfyEditor(image, parent)
        self.main_lyt.addWidget(self.content_container)

        self.bottom_panel = QFrame()
        self.bottom_panel.setFixedHeight(60)
        self.bottom_panel.setStyleSheet("background-color: #252525; border-top: 1px solid #333;")
        bot_lyt = QHBoxLayout(self.bottom_panel)
        self.btn_save = PrimaryPushButton("保存蒙版并退出")
        self.btn_save.setFixedWidth(180)
        self.btn_save.clicked.connect(self.accept)
        bot_lyt.addWidget(self.btn_save, 1)
        self.main_lyt.addWidget(self.bottom_panel)

    def get_result(self):
        mask = self.content_container.canvas.mask_image.convertToFormat(QImage.Format_Grayscale8)
        ba = QByteArray()
        buf = QBuffer(ba)
        mask.save(buf, "PNG")
        return {"mask": f"data:image/png;base64,{bytes(ba.toBase64()).decode()}"}


class DrawMaskPlugin(InteractivePlugin):
    plugin_id = "draw_mask"
    plugin_name = "绘制图像遮罩"
    plugin_desc = "将指定图片用 ComfyUI 绘制图像遮罩弹窗打开，绘制完会返回绘制结果。"
    plugin_template = """buffered = BytesIO()
        # 自动处理 RGBA 模式保存为 PNG（避免 JPEG 无法保存 alpha）
        format = "PNG"  # 强制含透明通道的图用 PNG
        img.save(buffered, format=format)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        mime = "image/jpeg" if format.upper() in ("JPG", "JPEG") else "image/png"
        base64_image = f"data:{mime};base64,{img_str}"
        # 触发ui出现遮罩绘制窗口
        result = self.emit_interactive_message(
            method="draw_mask",
            params={"title": "请绘制图像遮罩","schema": {"image": base64_image,}}
        )["mask"]   # 输出结果会带前缀 data:{mime};base64, 建议后续转换用split(',')获取图像数据
"""

    def operate(self, node, params, msg=None):
        title = params.get("title", "绘制遮罩")
        image = params.get("schema").get("image")

        dialog = MaskDrawDialog(title, image, node.parent_window)
        if dialog.exec():
            return dialog.get_result()