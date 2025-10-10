from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen, QImage
from PyQt5.QtCore import Qt, QRectF, QPointF


class MinimapWidget(QWidget):
    def __init__(self, parent_canvas_page):
        super().__init__(parent=parent_canvas_page.canvas_widget)
        self.canvas_page = parent_canvas_page
        self.viewer = parent_canvas_page.graph.viewer()
        self.scene = self.viewer.scene()
        self.setFixedSize(160, 120)
        self.setStyleSheet("background: rgba(0, 0, 0, 150); border: 1px solid #555;")
        self.setCursor(Qt.PointingHandCursor)
        self.dragging = False
        self.pixmap = None
        self.scene_rect = QRectF()
        self.update_minimap()
        # ✅ 确保能接收鼠标事件
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setFocusPolicy(Qt.NoFocus)
        self.raise_()  # 置顶

    def update_minimap(self):
        if not self.scene:
            return
        rect = self.scene.itemsBoundingRect()
        if rect.isEmpty():
            rect = QRectF(0, 0, 800, 600)

        image = QImage(rect.size().toSize(), QImage.Format_ARGB32)
        image.fill(Qt.transparent)  # ← 改为透明背景！
        painter = QPainter(image)
        self.scene.render(painter, QRectF(image.rect()), rect)
        painter.end()

        pixmap = QPixmap.fromImage(image).scaled(
            self.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.pixmap = pixmap
        self.scene_rect = rect
        self.update()

    def get_viewport_rect_in_scene(self):
        view_rect = self.viewer.rect()
        tl = self.viewer.mapToScene(0, 0)
        br = self.viewer.mapToScene(view_rect.width(), view_rect.height())
        return QRectF(tl, br)

    def map_scene_to_minimap(self, scene_rect):
        if self.scene_rect.isEmpty():
            return QRectF()
        x = (scene_rect.x() - self.scene_rect.x()) / self.scene_rect.width() * self.width()
        y = (scene_rect.y() - self.scene_rect.y()) / self.scene_rect.height() * self.height()
        w = scene_rect.width() / self.scene_rect.width() * self.width()
        h = scene_rect.height() / self.scene_rect.height() * self.height()
        return QRectF(x, y, w, h).normalized()

    def map_minimap_to_scene(self, mini_pos):
        if self.scene_rect.isEmpty():
            return QPointF(0, 0)
        x = self.scene_rect.x() + (mini_pos.x() / self.width()) * self.scene_rect.width()
        y = self.scene_rect.y() + (mini_pos.y() / self.height()) * self.scene_rect.height()
        return QPointF(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        # 绘制半透明背景底板
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))  # 深灰半透明底

        if self.pixmap:
            # 绘制缩略图内容（可再加一层透明度）
            painter.setOpacity(0.2)  # ← 关键：让内容也半透明
            painter.drawPixmap(0, 0, self.pixmap)
            painter.setOpacity(1.0)

        # 绘制视口框
        viewport_scene = self.get_viewport_rect_in_scene()
        viewport_mini = self.map_scene_to_minimap(viewport_scene)
        pen = QPen(QColor(0, 200, 255), 2)  # 更柔和的蓝色
        painter.setPen(pen)
        painter.setBrush(QColor(0, 200, 255, 50))  # 半透明填充
        painter.drawRect(viewport_mini)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            viewport_mini = self.map_scene_to_minimap(self.get_viewport_rect_in_scene())
            if viewport_mini.contains(event.pos()):
                # 点击在视角框内 → 进入拖拽模式
                self.dragging = True
                self.drag_offset = event.pos() - viewport_mini.topLeft()
            else:
                # 点击在视角框外 → 直接跳转
                self._jump_to_minimap_pos(event.pos())
            self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging:
            new_top_left = event.pos() - self.drag_offset
            # 限制不能拖出缩略图边界
            new_top_left.setX(max(0, min(new_top_left.x(), self.width() - 1)))
            new_top_left.setY(max(0, min(new_top_left.y(), self.height() - 1)))
            # 计算新视口中心
            new_scene_pos = self.map_minimap_to_scene(new_top_left + QPointF(self.width()/2, self.height()/2))
            self.viewer.centerOn(new_scene_pos)
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
        super().mouseReleaseEvent(event)

    def _jump_to_minimap_pos(self, pos):
        # 将缩略图点击点映射为场景中心
        scene_center = self.map_minimap_to_scene(pos)
        self.viewer.centerOn(scene_center)