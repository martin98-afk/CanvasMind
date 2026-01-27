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
        """创建半透明磨砂质感的拖拽预览图"""
        width, height = 210, 85  # 稍微加大一点尺寸以免边缘裁剪
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.transparent)  # 必须先填充完全透明

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        # 1. 绘制半透明背景 (模拟磨砂玻璃底色)
        # R, G, B, Alpha(透明度 0-255). 180 是一个不错的半透明数值
        # 使用深色背景模拟，如果你是浅色主题，可以使用 (255, 255, 255, 180)
        background_color = QColor(40, 40, 40, 180)
        painter.setBrush(background_color)

        # 2. 绘制边框 (模拟玻璃边缘反光)
        # 使用微弱的白色半透明边框，增加精致感
        border_color = QColor(255, 255, 255, 40)
        painter.setPen(QPen(border_color, 1.5))

        path = QPainterPath()
        path.addRoundedRect(2, 2, width - 4, height - 4, 10, 10)  # 圆角稍微大一点
        painter.drawPath(path)

        # 3. 绘制原来的类型标识色条 (保持原有逻辑，但稍微调整位置)
        type_color = {
            "custom": QColor("#3498db"),
            "node_vars": QColor("#2ecc71"),
            "env": QColor("#9b59b6")
        }.get(self.var_type, QColor("#7f8c8d"))

        painter.setPen(Qt.NoPen)
        painter.setBrush(type_color)
        # 左侧色条
        painter.drawRoundedRect(10, 10, 4, height - 20, 2, 2)

        # 4. 绘制文字内容
        # 变量名 (高亮白色)
        painter.setPen(QColor(255, 255, 255, 230))
        font = QFont("Microsoft YaHei")  # 建议指定字体以获得更好效果
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        # 调整文字坐标以适应新布局
        painter.drawText(22, 8, width - 30, 24, Qt.AlignLeft | Qt.AlignVCenter, self.var_name)

        # 类型标签 (稍微变暗)
        painter.setPen(QColor(255, 255, 255, 150))
        font.setPointSize(8)
        font.setBold(False)
        painter.setFont(font)
        type_labels = {
            "custom": "Custom Variable",
            "node_vars": "Node Output",
            "env": "Environment"
        }
        label_text = type_labels.get(self.var_type, self.var_type)
        painter.drawText(22, 32, width - 30, 16, Qt.AlignLeft | Qt.AlignVCenter, f"{label_text}")

        # 值预览 (更暗的颜色)
        if self.var_value is not None:
            painter.setPen(QColor(255, 255, 255, 120))
            preview = self._get_value_preview()
            # 绘制背景框让值看起来更像代码块 (可选)
            # painter.setBrush(QColor(0, 0, 0, 50))
            # painter.drawRoundedRect(22, 52, width-32, 20, 4, 4)
            painter.drawText(22, 50, width - 32, 24, Qt.AlignLeft | Qt.AlignVCenter, f"{preview}")

        painter.end()
        return pixmap