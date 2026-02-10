# -*- coding: utf-8 -*-
import base64
import os
import pickle
import tempfile
import uuid

from PyQt5.QtCore import Qt, QPoint, QPointF, QTimer
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
    def __init__(self, base64_image=None, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.original_pixmap = None
        self.scale_factor = 1.0
        self.offset = QPointF(0, 0)
        self.first_show = True

        # 状态变量
        self.is_panning = False
        self.last_mouse_pos = QPoint()

        # 标注数据结构
        # polygons = [ [p1, p2, p3], [p4, p5, p6] ]  每个 p 都是 QPointF (图像坐标)
        self.polygons = []
        self.current_poly = []  # 当前正在打点的多边形

        # 交互变量
        self.hover_info = None  # (poly_idx, point_idx) poly_idx为-1表示在current_poly中
        self.dragging_info = None
        self.mouse_curr_pos = QPointF(0, 0)  # 记录鼠标实时位置用于绘制跟随线
        self.hit_radius = 8  # 命中半径（屏幕像素）

        if base64_image:
            self.load_image(base64_image)

    def load_image(self, b64):
        try:
            if "," in b64: b64 = b64.split(",")[-1]
            data = base64.b64decode(b64)
            img = QImage.fromData(data)
            if img.isNull(): return
            self.original_pixmap = QPixmap.fromImage(img)

            # 使用单次定时器，确保在窗口显示并完成布局后执行 fit_view
            QTimer.singleShot(50, self.fit_view)
            self.update()
        except Exception as e:
            logger.exception(f"加载图片失败: {e}")

    def fit_view(self):
        """ 让图片适应画布大小并居中 """
        if not self.original_pixmap: return

        # 获取当前控件实际尺寸
        ww = float(self.width())
        wh = float(self.height())

        # 如果尺寸还没准备好（太小），则不进行计算
        if ww < 50 or wh < 50:
            return

        iw = float(self.original_pixmap.width())
        ih = float(self.original_pixmap.height())

        # 计算缩放比例 (保持比例适应窗口，留 5% 边距)
        s_width = ww / iw
        s_height = wh / ih
        self.scale_factor = min(s_width, s_height) * 0.95

        # 计算居中偏移量
        self.offset = QPointF(
            (ww - iw * self.scale_factor) / 2.0,
            (wh - ih * self.scale_factor) / 2.0
        )
        self.update()

    def img_to_screen(self, pt):
        return QPointF(pt.x() * self.scale_factor + self.offset.x(),
                       pt.y() * self.scale_factor + self.offset.y())

    def screen_to_img(self, pt):
        return QPointF((pt.x() - self.offset.x()) / self.scale_factor,
                       (pt.y() - self.offset.y()) / self.scale_factor)

    def find_hit_point(self, pos):
        """ 检测鼠标是否靠近某个锚点 """
        # 先查当前正在画的
        for i, pt in enumerate(self.current_poly):
            if (self.img_to_screen(pt) - pos).manhattanLength() < self.hit_radius:
                return -1, i
        # 再查已完成的
        for p_idx, poly in enumerate(self.polygons):
            for i, pt in enumerate(poly):
                if (self.img_to_screen(pt) - pos).manhattanLength() < self.hit_radius:
                    return p_idx, i
        return None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(30, 30, 30))

        if not self.original_pixmap: return

        # 1. 绘制底图
        painter.save()
        painter.translate(self.offset)
        painter.scale(self.scale_factor, self.scale_factor)
        painter.drawPixmap(0, 0, self.original_pixmap)
        painter.restore()

        # 2. 绘制已完成的多边形
        for p_idx, poly in enumerate(self.polygons):
            screen_pts = [self.img_to_screen(pt) for pt in poly]
            qpoly = QPolygonF(screen_pts)
            # 填充半透明色
            painter.setBrush(QBrush(QColor(0, 255, 127, 40)))
            painter.setPen(QPen(QColor(0, 255, 127), 2))
            painter.drawPolygon(qpoly)
            # 绘制锚点
            for i, spt in enumerate(screen_pts):
                self.draw_anchor(painter, spt, (p_idx, i))

        # 3. 绘制当前正在标注的多边形
        if self.current_poly:
            screen_pts = [self.img_to_screen(pt) for pt in self.current_poly]
            painter.setPen(QPen(QColor(255, 170, 0), 2, Qt.DashLine))
            for i in range(len(screen_pts) - 1):
                painter.drawLine(screen_pts[i], screen_pts[i + 1])

            # 绘制跟随鼠标的最后一条线
            if self.hover_info and self.hover_info == (-1, 0):
                # 悬浮在第一个点上（闭环提示）
                painter.setPen(QPen(QColor(0, 255, 0), 2))
                painter.drawLine(screen_pts[-1], screen_pts[0])
            else:
                painter.setPen(QPen(QColor(255, 170, 0), 1, Qt.DotLine))
                painter.drawLine(screen_pts[-1], self.mouse_curr_pos)

            for i, spt in enumerate(screen_pts):
                self.draw_anchor(painter, spt, (-1, i))

    def draw_anchor(self, painter, spt, info):
        is_hover = (self.hover_info == info)
        color = QColor(0, 255, 255) if info[0] != -1 else QColor(255, 170, 0)
        if is_hover:
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            radius = 6
        else:
            painter.setBrush(QBrush(color))
            radius = 4

        painter.setPen(QPen(Qt.black, 1))
        painter.drawEllipse(spt, radius, radius)

    def mousePressEvent(self, e):
        self.last_mouse_pos = e.pos()
        hit = self.find_hit_point(e.pos())

        if e.button() == Qt.LeftButton:
            if hit:
                # 如果点的是当前多边形的第一个点，且当前点数>2，则闭环
                if hit == (-1, 0) and len(self.current_poly) > 2:
                    self.polygons.append(self.current_poly)
                    self.current_poly = []
                else:
                    # 否则开启拖拽
                    self.dragging_info = hit
            else:
                # 在空白处打点
                img_pt = self.screen_to_img(e.pos())
                self.current_poly.append(img_pt)

        elif e.button() == Qt.RightButton:
            if hit:
                # 删除悬浮的点
                p_idx, pt_idx = hit
                if p_idx == -1:
                    self.current_poly.pop(pt_idx)
                else:
                    self.polygons[p_idx].pop(pt_idx)
                    # 如果多边形点数不足3个，直接删除该多边形
                    if len(self.polygons[p_idx]) < 3:
                        self.polygons.pop(p_idx)
            else:
                # 没点到点，撤销当前多边形最后一个点
                if self.current_poly: self.current_poly.pop()

        elif e.button() == Qt.MiddleButton:
            self.is_panning = True

        self.update()

    def mouseMoveEvent(self, e):
        self.mouse_curr_pos = e.pos()

        if self.is_panning:
            self.offset += QPointF(e.pos() - self.last_mouse_pos)
            self.last_mouse_pos = e.pos()
        elif self.dragging_info:
            # 执行拖拽
            new_img_pt = self.screen_to_img(e.pos())
            p_idx, pt_idx = self.dragging_info
            if p_idx == -1:
                self.current_poly[pt_idx] = new_img_pt
            else:
                self.polygons[p_idx][pt_idx] = new_img_pt
        else:
            # 更新悬浮状态
            old_hover = self.hover_info
            self.hover_info = self.find_hit_point(e.pos())
            if old_hover != self.hover_info:
                if self.hover_info:
                    self.setCursor(Qt.PointingHandCursor)
                else:
                    self.setCursor(Qt.ArrowCursor)

        self.update()

    def mouseReleaseEvent(self, e):
        self.is_panning = False
        self.dragging_info = None
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

        res_polygons = []
        # 合并已完成和未完成的（未完成的如果不闭环也可以选择是否返回，这里只返回已完成的）
        all_polys = self.polygons + ([self.current_poly] if len(self.current_poly) > 2 else [])

        for poly in all_polys:
            norm_pts = [[round(pt.x() / w, 6), round(pt.y() / h, 6)] for pt in poly]
            res_polygons.append(norm_pts)
        return res_polygons

    def clear_all(self):
        self.polygons = []
        self.current_poly = []
        self.update()


class AnchorImageDialog(QDialog):
    def __init__(self, title, image_b64, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1200, 800)
        self.setStyleSheet("QDialog { background-color: #1a1a1a; }")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # 顶部说明栏
        self.head = QFrame()
        self.head.setFixedHeight(60)
        self.head.setStyleSheet("background-color: #252525; border-bottom: 1px solid #333;")
        head_lyt = QHBoxLayout(self.head)

        info_label = StrongBodyLabel(
            "操作指南：\n"
            "1. 左键打点，点击起始点完成闭环； 2. 悬浮锚点左键拖拽修改位置；\n"
            "3. 悬浮锚点右键删除该点； 4. 中键/Space拖动画布，滚轮缩放。"
        )
        info_label.setStyleSheet("color: #bbb; font-size: 12px;")
        head_lyt.addWidget(info_label)
        head_lyt.addStretch()

        btn_clear = TransparentPushButton("清空所有标注")
        btn_clear.clicked.connect(lambda: self.canvas.clear_all())
        head_lyt.addWidget(btn_clear)
        self.layout.addWidget(self.head)

        # 画布
        self.canvas = AnchorCanvas(image_b64, self)
        self.layout.addWidget(self.canvas)

        # 底部按钮
        self.bottom = QFrame()
        self.bottom.setFixedHeight(70)
        self.bottom.setStyleSheet("background-color: #252525; border-top: 1px solid #333;")
        bot_lyt = QHBoxLayout(self.bottom)

        self.btn_ok = PrimaryPushButton("确认并导出多边形坐标")
        self.btn_ok.setFixedWidth(250)
        self.btn_ok.clicked.connect(self.accept)

        bot_lyt.addStretch()
        bot_lyt.addWidget(self.btn_ok)
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
                "schema": {"image": base64_image}
            }
        )
"""

    def handle(self, node, params, msg=None):
        title = params.get("title", "选择锚点")
        image = params.get("schema").get("image")
        response_file = params.get("response_file")

        env_data = getattr(node.parent_window, 'env_data', None)
        is_ssh = env_data and env_data.get('type') == 'ssh'

        def on_confirmed(result_data):
            if result_data is None: return
            if is_ssh:
                temp_path = os.path.join(tempfile.gettempdir(), f"anchor_{uuid.uuid4().hex}.pkl")
                with open(temp_path, 'wb') as f:
                    pickle.dump(result_data, f)
                ssh_send_file(env_data, temp_path, response_file)
                if os.path.exists(temp_path): os.remove(temp_path)
            else:
                os.makedirs(os.path.dirname(response_file), exist_ok=True)
                with open(response_file, 'wb') as f:
                    pickle.dump(result_data, f)

        dialog = AnchorImageDialog(title, image, node.parent_window)
        if dialog.exec():
            res = dialog.get_result()
            if Settings.get_instance().communication_method.value == "ZMQ通信":
                return res
            else:
                on_confirmed(res)
        return None