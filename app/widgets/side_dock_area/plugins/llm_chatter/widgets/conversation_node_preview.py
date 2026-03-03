from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QTimer
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor
from PyQt5.QtWidgets import QWidget, QToolTip


class ConversationNodePreview(QWidget):
    nodeClicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes = []
        self._selected_index = -1
        self._hovered_index = -1
        self._visible_index = -1
        self._node_radius = 3
        self._spacing = 16
        self.setFixedHeight(8)
        self.setStyleSheet("background-color: transparent;")
        self.setMouseTracking(True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self._nodes:
            return

        center_y = self.height() // 2
        total_width = (len(self._nodes) - 1) * self._spacing
        start_x = self.width() - total_width - 8

        # 绘制连接线
        if len(self._nodes) > 1:
            pen = QPen(QColor("#3A3A3A"))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawLine(start_x, center_y, start_x + total_width, center_y)

        # 绘制节点
        for i in range(len(self._nodes)):
            x = start_x + i * self._spacing

            if i == self._selected_index:
                color = QColor("#FFA500")
            elif i == self._hovered_index:
                color = QColor("#6BA3FF")
            elif i == self._visible_index:
                color = QColor("#00FF7F")
            else:
                color = QColor("#5A5A5A")

            painter.setPen(QPen(color))
            painter.setBrush(QBrush(color))
            painter.drawEllipse(
                QPoint(x, center_y), self._node_radius, self._node_radius
            )

    def mouseMoveEvent(self, event):
        if not self._nodes:
            return

        center_y = self.height() // 2
        total_width = (len(self._nodes) - 1) * self._spacing
        start_x = self.width() - total_width - 8

        new_hovered = -1
        for i in range(len(self._nodes)):
            x = start_x + i * self._spacing
            if abs(event.x() - x) <= 6 and abs(event.y() - center_y) <= 6:
                new_hovered = i
                break

        if new_hovered != self._hovered_index:
            self._hovered_index = new_hovered
            if new_hovered >= 0:
                preview = self._nodes[new_hovered] or ""
                if len(preview) > 50:
                    preview = preview[:50] + "..."
                # 立即显示tooltip
                QToolTip.showText(event.globalPos(), preview, self)
            else:
                QToolTip.hideText()
            self.update()

        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hovered_index = -1
        QToolTip.hideText()
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._hovered_index >= 0:
            self.nodeClicked.emit(self._hovered_index)
        super().mousePressEvent(event)

    def clear_nodes(self):
        self._nodes.clear()
        self._selected_index = -1
        self._hovered_index = -1
        self.update()

    def add_node(self, index: int, preview_text: str, timestamp: str = None):
        self._nodes.append(preview_text)
        self.update()

    def update_nodes(self, node_data: list):
        self.clear_nodes()
        for preview, timestamp in node_data:
            self.add_node(0, preview, timestamp)

    def select_node(self, index: int):
        if 0 <= index < len(self._nodes):
            self._selected_index = index
            self.update()

    def set_visible_node(self, index: int):
        if 0 <= index < len(self._nodes):
            self._visible_index = index
        else:
            self._visible_index = -1
        self.update()
