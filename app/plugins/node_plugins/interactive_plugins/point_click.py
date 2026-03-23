# -*- coding: utf-8 -*-
import base64
import math

from PyQt5.QtCore import Qt, QPoint, QPointF, QTimer, QRectF
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QBrush, QPolygonF
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QDialog, QLabel
from loguru import logger

from app.plugins.node_plugins.base import InteractivePlugin


class PointClickCanvas(QWidget):
    def __init__(
        self,
        base64_image=None,
        base64_mask=None,
        initial_positive_points=None,
        initial_negative_points=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.original_pixmap = None
        self.mask_pixmap = None
        self.scale_factor = 1.0
        self.offset = QPointF(0, 0)

        self.positive_points = []
        self.negative_points = []
        self.last_mouse_pos = QPoint()
        self.mouse_curr_pos = QPointF(0, 0)

        self.is_panning = False
        self.hover_point = None
        self.hit_radius = 12

        self.initial_positive = []
        self.initial_negative = []
        self._modified = False

        if base64_image:
            self.load_image(base64_image)
        if base64_mask:
            self.load_mask(base64_mask)

        if initial_positive_points:
            self.set_initial_points(initial_positive_points, initial_negative_points)

    def set_initial_points(self, positive_points, negative_points):
        if not self.original_pixmap:
            return
        w, h = self.original_pixmap.width(), self.original_pixmap.height()

        self.positive_points = [
            QPointF(pt[0] * w, pt[1] * h) for pt in (positive_points or [])
        ]
        self.negative_points = [
            QPointF(pt[0] * w, pt[1] * h) for pt in (negative_points or [])
        ]

        self.initial_positive = list(self.positive_points)
        self.initial_negative = list(self.negative_points)
        self._modified = False
        self.update()

    def load_image(self, b64):
        try:
            if "," in b64:
                b64 = b64.split(",")[-1]
            data = base64.b64decode(b64)
            img = QImage.fromData(data)
            if img.isNull():
                return
            self.original_pixmap = QPixmap.fromImage(img)
            QTimer.singleShot(50, self.fit_view)
            self.update()
        except Exception as e:
            logger.exception(f"加载图片失败: {e}")

    def load_mask(self, b64):
        try:
            if "," in b64:
                b64 = b64.split(",")[-1]
            data = base64.b64decode(b64)
            img = QImage.fromData(data)
            if img.isNull():
                return
            self.mask_pixmap = QPixmap.fromImage(img)
            self.update()
        except Exception as e:
            logger.exception(f"加载mask失败: {e}")

    def fit_view(self):
        if not self.original_pixmap:
            return
        ww, wh = float(self.width()), float(self.height())
        if ww < 50 or wh < 50:
            return
        iw, ih = (
            float(self.original_pixmap.width()),
            float(self.original_pixmap.height()),
        )
        self.scale_factor = min(ww / iw, wh / ih) * 0.95
        self.offset = QPointF(
            (ww - iw * self.scale_factor) / 2.0, (wh - ih * self.scale_factor) / 2.0
        )
        self.update()

    def img_to_screen(self, pt):
        return QPointF(
            pt.x() * self.scale_factor + self.offset.x(),
            pt.y() * self.scale_factor + self.offset.y(),
        )

    def screen_to_img(self, pt):
        return QPointF(
            (pt.x() - self.offset.x()) / self.scale_factor,
            (pt.y() - self.offset.y()) / self.scale_factor,
        )

    def get_dist(self, p1, p2):
        return math.sqrt((p1.x() - p2.x()) ** 2 + (p1.y() - p2.y()) ** 2)

    def find_hit_point(self, pos):
        for i, pt in enumerate(self.positive_points):
            if self.get_dist(self.img_to_screen(pt), pos) < self.hit_radius:
                return "positive", i
        for i, pt in enumerate(self.negative_points):
            if self.get_dist(self.img_to_screen(pt), pos) < self.hit_radius:
                return "negative", i
        return None

    def is_point_in_mask(self, pt):
        if not self.mask_pixmap:
            return False
        if not isinstance(pt, QPointF):
            img_pos = self.screen_to_img(pt)
        else:
            img_pos = pt
        if not self.original_pixmap:
            return False

        w, h = self.original_pixmap.width(), self.original_pixmap.height()
        mask_w, mask_h = self.mask_pixmap.width(), self.mask_pixmap.height()
        if img_pos.x() < 0 or img_pos.x() >= w or img_pos.y() < 0 or img_pos.y() >= h:
            return False

        x = int(img_pos.x() * mask_w / w)
        y = int(img_pos.y() * mask_h / h)
        x = min(max(x, 0), mask_w - 1)
        y = min(max(y, 0), mask_h - 1)

        mask_img = self.mask_pixmap.toImage()
        mask_img = mask_img.convertToFormat(QImage.Format_ARGB32)

        r = mask_img.pixel(x, y) & 0xFF
        return r > 127

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(30, 30, 30))

        if not self.original_pixmap:
            return

        painter.save()
        painter.translate(self.offset)
        painter.scale(self.scale_factor, self.scale_factor)
        painter.drawPixmap(0, 0, self.original_pixmap)
        painter.restore()

        if self.mask_pixmap:
            painter.save()
            painter.translate(self.offset)
            painter.scale(self.scale_factor, self.scale_factor)
            painter.setOpacity(0.5)
            if (
                self.mask_pixmap.width() != self.original_pixmap.width()
                or self.mask_pixmap.height() != self.original_pixmap.height()
            ):
                scaled_mask = self.mask_pixmap.scaled(
                    self.original_pixmap.size(),
                    Qt.IgnoreAspectRatio,
                    Qt.SmoothTransformation,
                )
                painter.drawPixmap(0, 0, scaled_mask)
            else:
                painter.drawPixmap(0, 0, self.mask_pixmap)
            painter.restore()

        for pt in self.positive_points:
            spt = self.img_to_screen(pt)
            self.draw_point(painter, spt, QColor(0, 255, 0), True)
            painter.setPen(QPen(QColor(0, 200, 0), 2))
            painter.setBrush(QBrush())
            painter.drawEllipse(spt, 10, 10)

        for pt in self.negative_points:
            spt = self.img_to_screen(pt)
            self.draw_point(painter, spt, QColor(255, 0, 0), True)
            painter.setPen(QPen(QColor(200, 0, 0), 2))
            painter.setBrush(QBrush())
            x, y = spt.x(), spt.y()
            painter.drawLine(int(x - 8), int(y - 8), int(x + 8), int(y + 8))
            painter.drawLine(int(x - 8), int(y + 8), int(x + 8), int(y - 8))

        if self.hover_point:
            self.draw_point(painter, self.hover_point, QColor(255, 255, 0), False)

    def draw_point(self, painter, spt, color, filled):
        painter.setPen(QPen(color, 2))
        painter.setBrush(QBrush(color if filled else QColor(255, 255, 255, 100)))
        painter.drawEllipse(spt, 6, 6)

    def mousePressEvent(self, e):
        self.last_mouse_pos = e.pos()

        if e.button() == Qt.LeftButton:
            hit = self.find_hit_point(e.pos())
            if hit:
                pt_type, idx = hit
                if pt_type == "positive":
                    self.positive_points.pop(idx)
                else:
                    self.negative_points.pop(idx)
                self._modified = True
            else:
                img_pt = self.screen_to_img(e.pos())
                in_mask = self.is_point_in_mask(img_pt)
                if in_mask:
                    self.negative_points.append(QPointF(img_pt))
                else:
                    self.positive_points.append(QPointF(img_pt))
                self._modified = True
            self.update()

        elif e.button() == Qt.MiddleButton:
            self.is_panning = True
            self.setCursor(Qt.ClosedHandCursor)

        elif e.button() == Qt.RightButton:
            hit = self.find_hit_point(e.pos())
            if hit:
                pt_type, idx = hit
                if pt_type == "positive":
                    self.positive_points.pop(idx)
                else:
                    self.negative_points.pop(idx)
                self._modified = True
            self.update()

    def mouseMoveEvent(self, e):
        self.mouse_curr_pos = e.pos()
        if self.is_panning:
            self.offset += QPointF(e.pos() - self.last_mouse_pos)
            self.last_mouse_pos = e.pos()
        else:
            self.hover_point = self.img_to_screen(self.screen_to_img(QPointF(e.pos())))
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self.is_panning = False
            self.setCursor(Qt.ArrowCursor)
        self.update()

    def wheelEvent(self, e):
        delta = 1.1 if e.angleDelta().y() > 0 else 1 / 1.1
        new_scale = max(0.01, min(self.scale_factor * delta, 100.0))
        mouse_pos = QPointF(e.pos())
        self.offset = mouse_pos - (mouse_pos - self.offset) * (
            new_scale / self.scale_factor
        )
        self.scale_factor = new_scale
        self.update()

    def get_normalized_result(self):
        if not self.original_pixmap:
            return {"positive_points": [], "negative_points": []}
        w, h = self.original_pixmap.width(), self.original_pixmap.height()
        return {
            "positive_points": [
                [round(pt.x() / w, 6), round(pt.y() / h, 6)]
                for pt in self.positive_points
            ],
            "negative_points": [
                [round(pt.x() / w, 6), round(pt.y() / h, 6)]
                for pt in self.negative_points
            ],
        }

    def clear_all(self):
        self.positive_points = []
        self.negative_points = []
        self._modified = True
        self.update()


class PointClickDialog(QDialog):
    def __init__(
        self,
        title,
        image_b64,
        mask_b64=None,
        initial_positive_points=None,
        initial_negative_points=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1200, 850)
        self.setStyleSheet("QDialog { background-color: #1a1a1a; }")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.head = QFrame()
        self.head.setFixedHeight(80)
        self.head.setStyleSheet(
            "background-color: #252525; border-bottom: 1px solid #333;"
        )
        head_lyt = QHBoxLayout(self.head)

        self.info_label = QLabel(
            "【左键点击】添加标注点 | 绿色=扩充区域 | 红色=排除区域\n"
            "【左键/右键点击点】删除点 | 【中键】平移 | 【滚轮】缩放"
        )
        self.info_label.setStyleSheet(
            "color: #00d2ff; font-size: 13px; background: transparent;"
        )
        head_lyt.addWidget(self.info_label)
        head_lyt.addStretch()

        from qfluentwidgets import TransparentPushButton

        btn_clear = TransparentPushButton("清空所有")
        btn_clear.clicked.connect(lambda: self.canvas.clear_all())
        head_lyt.addWidget(btn_clear)
        self.layout.addWidget(self.head)

        self.canvas = PointClickCanvas(
            image_b64, mask_b64, initial_positive_points, initial_negative_points, self
        )
        self.layout.addWidget(self.canvas)

        self.bottom = QFrame()
        self.bottom.setFixedHeight(60)
        self.bottom.setStyleSheet(
            "background-color: #252525; border-top: 1px solid #333;"
        )
        bot_lyt = QHBoxLayout(self.bottom)

        from qfluentwidgets import PrimaryPushButton, TransparentPushButton

        self.btn_ok = PrimaryPushButton("提交结果")
        self.btn_ok.clicked.connect(self.accept)
        bot_lyt.addWidget(self.btn_ok)
        self.layout.addWidget(self.bottom)

        self.finish_result = None

    def on_finish(self):
        self.finish_result = True
        self.accept()

    def get_result(self):
        result = self.canvas.get_normalized_result()
        if not self.canvas._modified:
            result["positive_points"] = []
            result["negative_points"] = []
        result["_finish"] = self.finish_result
        return result


class PointClickPlugin(InteractivePlugin):
    plugin_id = "point_click_selector"
    plugin_name = "交互式点标注"
    plugin_desc = (
        "在图像上点击选择正负样本点，绿色扩充(正)，红色排除(负)，返回归一化坐标(0-1)。"
    )

    plugin_template = """result = self.emit_message(
    method="point_click_selector",
    params={
        "title": "请标注正负样本点",
        "schema": {
            "image": "data:image/jpeg;base64,...",
            "mask": "data:image/png;base64,...",  # 可选
            "positive_points": [[0.1, 0.2], [0.3, 0.4]],  # 可选，初始正点
            "negative_points": [[0.5, 0.6]],  # 可选，初始负点
        }
    }
)
"""

    def operate(self, node, params, msg=None):
        title = params.get("title", "选择标注点")
        schema = params.get("schema", {})
        image = schema.get("image")
        mask = schema.get("mask")
        positive_points = schema.get("positive_points")
        negative_points = schema.get("negative_points")

        dialog = PointClickDialog(
            title=title,
            image_b64=image,
            mask_b64=mask,
            initial_positive_points=positive_points,
            initial_negative_points=negative_points,
            parent=node.parent_window,
        )

        if dialog.exec():
            return dialog.get_result()
