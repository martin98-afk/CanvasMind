# -*- coding: utf-8 -*-
import json

from PyQt5.QtCore import Qt, QMimeData, QPoint
from PyQt5.QtGui import QDrag, QPixmap, QPainter, QColor, QFont, QPainterPath, QPen
from PyQt5.QtWidgets import QApplication
from qfluentwidgets import CardWidget


class DraggableVariableCard(CardWidget):
    """支持拖拽的变量卡片基类"""

    def __init__(self, parent, var_type: str, var_name: str, var_value=None):
        super().__init__(parent)
        self.var_type = var_type  # 'custom', 'node_vars', 'env'
        self.var_name = var_name
        self.var_value = var_value
        self.drag_start_pos = None
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if not self.drag_start_pos:
            return
        if (event.pos() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return

        self.startDrag()
        super().mouseMoveEvent(event)

    def startDrag(self):
        """启动拖拽操作"""
        drag = QDrag(self)
        mime_data = QMimeData()

        # 设置自定义 MIME 类型，包含完整的变量信息
        drag_data = {
            "type": "global_variable",
            "var_type": self.var_type,
            "var_name": self.var_name,
            "value_preview": self._get_value_preview()
        }
        mime_data.setData("application/x-global-variable",
                          json.dumps(drag_data, ensure_ascii=False).encode('utf-8'))

        # 同时设置文本格式，便于调试和兼容
        mime_data.setText(f"变量操作/获取全局变量")

        drag.setMimeData(mime_data)
        drag.setPixmap(self.create_drag_preview())
        drag.setHotSpot(QPoint(drag.pixmap().width() // 2, drag.pixmap().height() // 2))
        drag.exec_(Qt.CopyAction)

    def _get_value_preview(self):
        """获取变量值的简短预览"""
        try:
            if self.var_value is None:
                return "None"
            elif isinstance(self.var_value, (dict, list)):
                return json.dumps(self.var_value, ensure_ascii=False, default=str)[:30] + "..."
            else:
                return str(self.var_value)[:30]
        except:
            return "<preview>"

    def create_drag_preview(self):
        """创建美观的拖拽预览图"""
        width, height = 200, 80
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        # 背景卡片
        path = QPainterPath()
        path.addRoundedRect(2, 2, width - 4, height - 4, 8, 8)
        painter.setPen(QPen(QColor("#4A90E2"), 2))
        painter.setBrush(QColor("#2D2D2D"))
        painter.drawPath(path)

        # 类型标签颜色
        type_color = {
            "custom": QColor("#3498db"),
            "node_vars": QColor("#2ecc71"),
            "env": QColor("#9b59b6")
        }.get(self.var_type, QColor("#7f8c8d"))

        # 类型标识
        painter.setPen(Qt.NoPen)
        painter.setBrush(type_color)
        painter.drawRoundedRect(8, 8, 6, 20, 3, 3)

        # 变量名
        painter.setPen(Qt.white)
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(20, 8, width - 30, 24, Qt.AlignLeft | Qt.TextWordWrap, self.var_name)

        # 变量类型标签
        painter.setPen(type_color)
        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        type_labels = {
            "custom": "CustomLabel",
            "node_vars": "Node Output",
            "env": "Environment"
        }
        painter.drawText(20, 28, width - 30, 16, Qt.AlignLeft, f"({type_labels.get(self.var_type, self.var_type)})")

        # 值预览
        if self.var_value is not None:
            painter.setPen(QColor("#bdc3c7"))
            font.setPointSize(8)
            painter.setFont(font)
            preview = self._get_value_preview()
            painter.drawText(8, 48, width - 16, 24, Qt.AlignLeft | Qt.TextWordWrap, f"Value: {preview}")

        painter.end()
        return pixmap