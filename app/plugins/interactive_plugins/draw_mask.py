# -*- coding: utf-8 -*-
import base64
import os
import pickle
import tempfile
import uuid
from collections import deque

from PyQt5.QtCore import Qt, QPoint, QPointF, QByteArray, QBuffer
from PyQt5.QtGui import (
    QImage, QPixmap, QPainter, QPen, QColor
)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel
)
from qfluentwidgets import MessageBoxBase, SubtitleLabel, ToolButton, Slider, FluentIcon

from app.plugins.base import InteractivePlugin
from app.utils.utils import get_icon, ssh_send_file


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
            self.original_pixmap = QPixmap.fromImage(img)
            # 使用高性能 ARGB 格式
            self.mask_image = QImage(img.size(), QImage.Format_ARGB32_Premultiplied)
            self.mask_image.fill(Qt.transparent)
        except:
            pass

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
        painter.setRenderHint(QPainter.SmoothPixmapTransform, self.scale_factor < 1.0)
        painter.drawPixmap(0, 0, self.original_pixmap)
        painter.drawImage(0, 0, self.mask_image)
        painter.restore()

        # 2. 画笔圆圈实时预览 (始终跟随)
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
        """种子填充：点击透明区域则填充"""
        w, h = self.mask_image.width(), self.mask_image.height()
        if not (0 <= start_pt.x() < w and 0 <= start_pt.y() < h): return

        # 获取点击位置颜色
        target_color = self.mask_image.pixelColor(start_pt)
        if target_color.alpha() > 10: return  # 如果点在已有蒙版上，不处理

        # BFS 填充
        fill_color = self.mask_color
        q = deque([start_pt])

        # 性能考虑：小图直接填，大图建议后期用 mask 连通域
        # 下面演示逻辑为快速填充整个连通的透明区域
        visited = set()

        p = QPainter(self.mask_image)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.setPen(fill_color)

        # 简单高效的 Scanline 填充替代方案：如果是在封闭圆圈内，这里填满。
        # 这里用简化的算法演示，实际在大图上请确保效率
        pixel_to_fill = []
        target_alpha = 0

        queue = deque([(start_pt.x(), start_pt.y())])
        processed = set([(start_pt.x(), start_pt.y())])

        while queue:
            x, y = queue.popleft()
            pixel_to_fill.append(QPoint(x, y))
            if len(pixel_to_fill) > 500000: break  # 防止死循环或溢出

            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in processed:
                    c = self.mask_image.pixelColor(nx, ny)
                    if c.alpha() <= 10:
                        processed.add((nx, ny))
                        queue.append((nx, ny))

        for pt in pixel_to_fill:
            self.mask_image.setPixelColor(pt, fill_color)

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
        self.sld.setRange(2, 300)
        self.sld.setValue(40)
        self.sld.setStyleSheet("QSlider::handle:vertical { background: #ff0064; }")
        lp_lyt.addSpacing(10)
        lp_lyt.addWidget(self.sld, 0, Qt.AlignHCenter)
        lp_lyt.addWidget(QLabel("画笔大小"), 0, Qt.AlignHCenter)

        # 右悬浮面板
        self.right_panel = QFrame(self)
        rp_lyt = QVBoxLayout(self.right_panel)
        rp_lyt.setSpacing(10)
        self.btn_undo = ComfyToolButton(FluentIcon.LEFT_ARROW, "撤销 (Ctrl+Z)")
        self.btn_reset = ComfyToolButton(get_icon("缩放"), "居中 (R)")
        self.btn_clear = ComfyToolButton(FluentIcon.DELETE, "清空 (C)")

        self.btn_undo.setCheckable(False)
        self.btn_reset.setCheckable(False)
        self.btn_clear.setCheckable(False)

        rp_lyt.addWidget(self.btn_undo)
        rp_lyt.addWidget(self.btn_reset)
        rp_lyt.addWidget(self.btn_clear)
        rp_lyt.addStretch()

        # 信号
        self.btn_brush.clicked.connect(lambda: self.set_mode("brush"))
        self.btn_eraser.clicked.connect(lambda: self.set_mode("eraser"))
        self.btn_fill.clicked.connect(lambda: self.set_mode("fill"))
        self.btn_undo.clicked.connect(self.canvas.undo)
        self.btn_reset.clicked.connect(self.canvas.fit_view)
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


class MaskDrawDialog(MessageBoxBase):
    def __init__(self, title, image, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(title)
        self.viewLayout.addWidget(self.titleLabel)

        self.editor = ComfyEditor(image)
        self.editor.setMinimumSize(1100, 750)
        self.viewLayout.addWidget(self.editor)

        self.widget.setMinimumWidth(1150)

        # 底部按钮只留确认
        self.cancelButton.hide()
        self.yesButton.setText("完成并保存蒙版")
        self.yesButton.setMinimumHeight(45)
        self.yesButton.setStyleSheet("""
            QPushButton {
                background-color: #ff0064;
                color: white;
                font-size: 16px;
                font-weight: bold;
                border-radius: 10px;
            }
            QPushButton:hover { background-color: #ff3385; }
        """)
        self.buttonLayout.insertStretch(0, 1)  # 居中按钮

    def get_result(self):
        # 处理结果并转为 Base64
        mask = self.editor.canvas.mask_image.convertToFormat(QImage.Format_Grayscale8)
        ba = QByteArray()
        buf = QBuffer(ba)
        mask.save(buf, "PNG")
        return {"mask": f"data:image/png;base64,{bytes(ba.toBase64()).decode()}"}


class DrawMaskPlugin(InteractivePlugin):
    plugin_id = "draw_mask"

    def handle(self, node, params, msg=None):
        title = params.get("title", "ComfyUI 交互蒙版")
        response_file = params.get("response_file")
        image = params.get("schema").get("image")

        env_data = getattr(node.parent_window, 'env_data', None)
        is_ssh = env_data and env_data.get('type') == 'ssh'

        def on_confirmed(result_data):
            if is_ssh:
                temp_path = os.path.join(tempfile.gettempdir(), f"ask_{uuid.uuid4().hex}.pkl")
                with open(temp_path, 'wb') as f:
                    pickle.dump(result_data, f)
                ssh_send_file(env_data, temp_path, response_file)
                if os.path.exists(temp_path): os.remove(temp_path)
            else:
                os.makedirs(os.path.dirname(response_file), exist_ok=True)
                with open(response_file, 'wb') as f:
                    pickle.dump(result_data, f)

        dialog = MaskDrawDialog(title, image, node.parent_window)
        dialog.cancelButton.hide()
        if dialog.exec():
            on_confirmed(dialog.get_result())