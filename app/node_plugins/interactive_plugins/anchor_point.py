# -*- coding: utf-8 -*-
import base64
import os
import pickle
import tempfile
import uuid
import math

from PyQt5.QtCore import Qt, QPoint, QPointF, QTimer, QRectF
from PyQt5.QtGui import (
    QImage, QPixmap, QPainter, QPen, QColor, QBrush, QPolygonF
)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QDialog
)
from loguru import logger
from qfluentwidgets import (
    StrongBodyLabel, PrimaryPushButton, TransparentPushButton
)

from app.node_plugins.base import InteractivePlugin
from app.utils.config import Settings
from app.utils.utils import ssh_send_file


class AnchorCanvas(QWidget):
    def __init__(self, base64_image=None, initial_polygons=None, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.original_pixmap = None
        self.scale_factor = 1.0
        self.offset = QPointF(0, 0)

        # 标注数据
        self.polygons = []  # 存储为 QPointF(图像像素坐标)
        self.current_poly = []
        self.initial_norm_polygons = initial_polygons or []  # 暂存初始归一化数据

        # 交互状态
        self.is_panning = False
        self.is_drawing_rect = False
        self.rect_start_img = None
        self.last_mouse_pos = QPoint()
        self.mouse_curr_pos = QPointF(0, 0)

        self.hover_info = None  # (poly_idx, point_idx)
        self.hover_edge = None  # (poly_idx, line_index, project_pt)
        self.dragging_info = None

        self.hit_radius = 10
        self.edge_threshold = 8

        if base64_image:
            self.load_image(base64_image)

    def load_image(self, b64):
        try:
            if "," in b64: b64 = b64.split(",")[-1]
            data = base64.b64decode(b64)
            img = QImage.fromData(data)
            if img.isNull(): return
            self.original_pixmap = QPixmap.fromImage(img)

            # 图片加载后，将初始归一化坐标转换为像素坐标
            self.convert_initial_polygons()

            QTimer.singleShot(50, self.fit_view)
            self.update()
        except Exception as e:
            logger.exception(f"加载图片失败: {e}")

    def convert_initial_polygons(self):
        """ 将 0-1 的归一化坐标转换为像素坐标 """
        if not self.original_pixmap or not self.initial_norm_polygons:
            return

        w = self.original_pixmap.width()
        h = self.original_pixmap.height()

        self.polygons = []
        for poly in self.initial_norm_polygons:
            pts = [QPointF(p[0] * w, p[1] * h) for p in poly]
            if len(pts) >= 3:
                self.polygons.append(pts)
        self.initial_norm_polygons = []  # 转换后清空

    def fit_view(self):
        if not self.original_pixmap: return
        ww, wh = float(self.width()), float(self.height())
        if ww < 50 or wh < 50: return
        iw, ih = float(self.original_pixmap.width()), float(self.original_pixmap.height())
        self.scale_factor = min(ww / iw, wh / ih) * 0.95
        self.offset = QPointF((ww - iw * self.scale_factor) / 2.0, (wh - ih * self.scale_factor) / 2.0)
        self.update()

    # --- 坐标转换 ---
    def img_to_screen(self, pt):
        return QPointF(pt.x() * self.scale_factor + self.offset.x(), pt.y() * self.scale_factor + self.offset.y())

    def screen_to_img(self, pt):
        return QPointF((pt.x() - self.offset.x()) / self.scale_factor, (pt.y() - self.offset.y()) / self.scale_factor)

    # --- 几何检测 ---
    def get_dist(self, p1, p2):
        return math.sqrt((p1.x() - p2.x()) ** 2 + (p1.y() - p2.y()) ** 2)

    def find_hit_point(self, pos):
        for i, pt in enumerate(self.current_poly):
            if (self.img_to_screen(pt) - pos).manhattanLength() < self.hit_radius:
                return -1, i
        for p_idx, poly in enumerate(self.polygons):
            for i, pt in enumerate(poly):
                if (self.img_to_screen(pt) - pos).manhattanLength() < self.hit_radius:
                    return p_idx, i
        return None

    def find_hit_edge(self, pos):
        """ 检测鼠标是否靠近多边形的某条边 """
        img_pos = self.screen_to_img(pos)
        for p_idx, poly in enumerate(self.polygons):
            n = len(poly)
            for i in range(n):
                p1, p2 = poly[i], poly[(i + 1) % n]
                # 计算点到线段距离
                d, proj = self.point_to_line_dist(img_pos, p1, p2)
                if d * self.scale_factor < self.edge_threshold:
                    return p_idx, i + 1, proj
        return None

    def point_to_line_dist(self, p, a, b):
        l2 = (a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2
        if l2 == 0: return self.get_dist(p, a), a
        t = ((p.x() - a.x()) * (b.x() - a.x()) + (p.y() - a.y()) * (b.y() - a.y())) / l2
        t = max(0, min(1, t))
        proj = QPointF(a.x() + t * (b.x() - a.x()), a.y() + t * (b.y() - a.y()))
        return self.get_dist(p, proj), proj

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(30, 30, 30))

        if not self.original_pixmap: return

        # 1. 绘制图片
        painter.save()
        painter.translate(self.offset)
        painter.scale(self.scale_factor, self.scale_factor)
        painter.drawPixmap(0, 0, self.original_pixmap)
        painter.restore()

        # 2. 绘制已存多边形
        for p_idx, poly in enumerate(self.polygons):
            screen_pts = [self.img_to_screen(pt) for pt in poly]
            painter.setBrush(QBrush(QColor(0, 255, 127, 40)))
            painter.setPen(QPen(QColor(0, 255, 127), 2))
            painter.drawPolygon(QPolygonF(screen_pts))
            for i, spt in enumerate(screen_pts):
                self.draw_anchor(painter, spt, (p_idx, i))

        # 3. 绘制矩形预览
        if self.is_drawing_rect and self.rect_start_img:
            p1 = self.img_to_screen(self.rect_start_img)
            p2 = self.mouse_curr_pos
            rect = QRectF(p1, p2).normalized()
            painter.setPen(QPen(QColor(0, 170, 255), 2, Qt.DashLine))
            painter.setBrush(QBrush(QColor(0, 170, 255, 30)))
            painter.drawRect(rect)

        # 4. 绘制当前打点多边形
        elif self.current_poly:
            screen_pts = [self.img_to_screen(pt) for pt in self.current_poly]
            painter.setPen(QPen(QColor(255, 170, 0), 2, Qt.DashLine))
            for i in range(len(screen_pts) - 1):
                painter.drawLine(screen_pts[i], screen_pts[i + 1])

            # 跟随线或闭环预览
            if self.hover_info == (-1, 0) and len(self.current_poly) > 2:
                painter.setPen(QPen(QColor(0, 255, 0), 2))
                painter.drawLine(screen_pts[-1], screen_pts[0])
            else:
                painter.setPen(QPen(QColor(255, 170, 0), 1, Qt.DotLine))
                painter.drawLine(screen_pts[-1], self.mouse_curr_pos)

            for i, spt in enumerate(screen_pts):
                self.draw_anchor(painter, spt, (-1, i))

        # 5. 绘制中键加点预览
        if self.hover_edge and not self.dragging_info:
            _, _, proj_pt = self.hover_edge
            painter.setPen(QPen(Qt.white, 1))
            painter.setBrush(QBrush(QColor(255, 255, 255, 180)))
            painter.drawEllipse(self.img_to_screen(proj_pt), 5, 5)

    def draw_anchor(self, painter, spt, info):
        is_hover = (self.hover_info == info)
        color = QColor(0, 255, 255) if info[0] != -1 else QColor(255, 170, 0)
        radius = 6 if is_hover else 4
        painter.setBrush(QBrush(Qt.white if is_hover else color))
        painter.setPen(QPen(Qt.black, 1))
        painter.drawEllipse(spt, radius, radius)

    def mousePressEvent(self, e):
        self.last_mouse_pos = e.pos()
        hit = self.find_hit_point(e.pos())

        if e.button() == Qt.LeftButton:
            if hit:
                if hit == (-1, 0) and len(self.current_poly) > 2:
                    self.polygons.append(self.current_poly)
                    self.current_poly = []
                else:
                    self.dragging_info = hit
            else:
                # 准备绘制矩形或打点
                self.rect_start_img = self.screen_to_img(e.pos())
                self.is_drawing_rect = False

        elif e.button() == Qt.MiddleButton:
            edge_hit = self.find_hit_edge(e.pos())
            if edge_hit:
                p_idx, ins_idx, proj_pt = edge_hit
                self.polygons[p_idx].insert(ins_idx, proj_pt)
                self.dragging_info = (p_idx, ins_idx)  # 插入后立即允许拖拽
            else:
                self.is_panning = True
                self.setCursor(Qt.ClosedHandCursor)

        elif e.button() == Qt.RightButton:
            if hit:
                p_idx, pt_idx = hit
                if p_idx == -1:
                    self.current_poly.pop(pt_idx)
                else:
                    self.polygons[p_idx].pop(pt_idx)
                    if len(self.polygons[p_idx]) < 3: self.polygons.pop(p_idx)
            else:
                if self.current_poly: self.current_poly.pop()
        self.update()

    def mouseMoveEvent(self, e):
        self.mouse_curr_pos = e.pos()
        if self.is_panning:
            self.offset += QPointF(e.pos() - self.last_mouse_pos)
            self.last_mouse_pos = e.pos()
        elif self.dragging_info:
            p_idx, pt_idx = self.dragging_info
            new_pt = self.screen_to_img(e.pos())
            if p_idx == -1:
                self.current_poly[pt_idx] = new_pt
            else:
                self.polygons[p_idx][pt_idx] = new_pt
        elif e.buttons() & Qt.LeftButton and self.rect_start_img:
            if (e.pos() - self.last_mouse_pos).manhattanLength() > 5:
                self.is_drawing_rect = True
        else:
            self.hover_info = self.find_hit_point(e.pos())
            self.hover_edge = self.find_hit_edge(e.pos()) if not self.hover_info else None
            if self.hover_info or self.hover_edge:
                self.setCursor(Qt.PointingHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect_start_img:
            if self.is_drawing_rect:
                p1 = self.rect_start_img
                p2 = self.screen_to_img(e.pos())
                self.polygons.append([
                    QPointF(p1.x(), p1.y()), QPointF(p2.x(), p1.y()),
                    QPointF(p2.x(), p2.y()), QPointF(p1.x(), p2.y())
                ])
            elif not self.dragging_info:
                self.current_poly.append(self.rect_start_img)

        self.is_panning = False
        self.is_drawing_rect = False
        self.rect_start_img = None
        self.dragging_info = None
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def wheelEvent(self, e):
        delta = 1.1 if e.angleDelta().y() > 0 else 1 / 1.1
        new_scale = max(0.01, min(self.scale_factor * delta, 100.0))
        mouse_pos = QPointF(e.pos())
        self.offset = mouse_pos - (mouse_pos - self.offset) * (new_scale / self.scale_factor)
        self.scale_factor = new_scale
        self.update()

    def get_normalized_result(self):
        if not self.original_pixmap: return []
        w, h = self.original_pixmap.width(), self.original_pixmap.height()
        res = []
        all_polys = self.polygons + ([self.current_poly] if len(self.current_poly) > 2 else [])
        for poly in all_polys:
            res.append([[round(pt.x() / w, 6), round(pt.y() / h, 6)] for pt in poly])
        return res

    def clear_all(self):
        self.polygons = []
        self.current_poly = []
        self.update()


class AnchorImageDialog(QDialog):
    def __init__(self, title, image_b64, initial_polygons=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1200, 850)
        self.setStyleSheet("QDialog { background-color: #1a1a1a; }")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # 头部说明
        self.head = QFrame()
        self.head.setFixedHeight(80)
        self.head.setStyleSheet("background-color: #252525; border-bottom: 1px solid #333;")
        head_lyt = QHBoxLayout(self.head)

        info_label = StrongBodyLabel(
            "【矩形】左键拖拽绘制 | 【多边形】左键连续点击，点击起点闭环\n"
            "【编辑】中键点击边加点 | 左键拖动点 | 右键点删点/撤销\n"
            "【视图】中键按住空白处平移 | 滚轮缩放"
        )
        info_label.setStyleSheet("color: #00d2ff; font-size: 13px;")
        head_lyt.addWidget(info_label)
        head_lyt.addStretch()

        btn_clear = TransparentPushButton("清空所有")
        btn_clear.clicked.connect(lambda: self.canvas.clear_all())
        head_lyt.addWidget(btn_clear)
        self.layout.addWidget(self.head)

        # 画布传入已有多边形
        self.canvas = AnchorCanvas(image_b64, initial_polygons, self)
        self.layout.addWidget(self.canvas)

        # 底部
        self.bottom = QFrame()
        self.bottom.setFixedHeight(60)
        self.bottom.setStyleSheet("background-color: #252525; border-top: 1px solid #333;")
        bot_lyt = QHBoxLayout(self.bottom)
        self.btn_ok = PrimaryPushButton("完成并导出坐标")
        self.btn_ok.setFixedWidth(200)
        self.btn_ok.clicked.connect(self.accept)
        bot_lyt.addStretch();
        bot_lyt.addWidget(self.btn_ok);
        bot_lyt.addStretch()
        self.layout.addWidget(self.bottom)

    def get_result(self):
        return {"polygons": self.canvas.get_normalized_result()}


class AnchorPointPlugin(InteractivePlugin):
    plugin_id = "anchor_selector"
    plugin_name = "图像锚点选择"
    plugin_desc = "在图像上点击选择多个点，返回其归一化坐标(0-1)。"

    # 插件模板示例
    plugin_template = """buffered = BytesIO()
        # 自动处理 RGBA 模式保存为 PNG（避免 JPEG 无法保存 alpha）
        format = "PNG"  # 强制含透明通道的图用 PNG
        img.save(buffered, format=format)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        mime = "image/jpeg" if format.upper() in ("JPG", "JPEG") else "image/png"
        base64_image = f"data:{mime};base64,{img_str}"
        result = self.emit_interactive_message(
            method="anchor_selector",
            params={
                "title": "请选择关键点锚点",
                "schema": {
                    "image": "data:image/jpeg;base64,...",
                    "polygons": [
                        [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]] # 预设一个矩形（可选）
                    ]
                }
            }
        )
"""

    def operate(self, node, params, msg=None):
        title = params.get("title", "选择锚点")
        schema = params.get("schema", {})
        image = schema.get("image")
        initial_polygons = schema.get("polygons", [])

        # 按顺序传入 initial_polygons，或者使用关键字参数
        dialog = AnchorImageDialog(
            title=title,
            image_b64=image,
            initial_polygons=initial_polygons,
            parent=node.parent_window
        )

        if dialog.exec():
            return dialog.get_result()