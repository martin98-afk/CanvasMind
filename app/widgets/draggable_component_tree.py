from PyQt5.QtCore import Qt, QMimeData, QRectF
from PyQt5.QtGui import QDrag, QPixmap, QPainter, QColor, QPen, QFont
from PyQt5.QtWidgets import QTreeWidgetItem
# ----------------------------
# 属性面板（右侧）
# ----------------------------
from qfluentwidgets import (
    TreeWidget
)

from app.scan_components import scan_components


# ----------------------------
# 可拖拽的组件树（带预览）
# ----------------------------
class DraggableTreeWidget(TreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(False)
        self.setDragDropMode(TreeWidget.DragOnly)
        self.refresh_components()

    def startDrag(self, supportedActions):
        """开始拖拽操作，带预览"""
        item = self.currentItem()
        if item and item.parent():  # 确保是叶子节点（组件，不是分类）
            category = item.parent().text(0)
            name = item.text(0)
            full_path = f"{category}/{name}"

            # 创建拖拽对象
            drag = QDrag(self)
            mime_data = QMimeData()
            mime_data.setText(full_path)
            drag.setMimeData(mime_data)

            # 创建预览 pixmap
            preview = self.create_drag_preview(full_path)
            drag.setPixmap(preview)
            drag.setHotSpot(preview.rect().center())

            drag.exec_(Qt.CopyAction)

    def create_drag_preview(self, full_path):
        """创建拖拽预览 pixmap"""
        comp_cls = self.component_map.get(full_path)
        if not comp_cls:
            # 默认预览
            pixmap = QPixmap(120, 60)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setPen(QPen(QColor("#4A90E2"), 2))
            painter.drawRect(0, 0, 119, 59)
            painter.setPen(Qt.black)
            painter.drawText(QRectF(10, 20, 100, 20), Qt.AlignLeft, "组件")
            painter.end()
            return pixmap

        # 创建组件预览
        pixmap = QPixmap(150, 90)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)

        # 绘制节点背景
        painter.setPen(QPen(QColor("#4A90E2"), 2))
        painter.setBrush(QColor("#2D2D2D"))
        painter.drawRect(0, 0, 149, 89)

        # 绘制标题
        painter.setPen(Qt.white)
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(10, 10, 130, 20), Qt.AlignLeft, comp_cls.name)

        # 绘制类别
        painter.setPen(QColor("#888888"))
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(QRectF(10, 35, 130, 15), Qt.AlignLeft, f"类别: {comp_cls.category}")

        # 绘制输入端口
        inputs = comp_cls.get_inputs()
        if inputs:
            painter.setPen(QColor("#2ECC71"))
            painter.drawText(QRectF(10, 55, 130, 15), Qt.AlignLeft, f"输入: {len(inputs)}")

        # 绘制输出端口
        outputs = comp_cls.get_outputs()
        if outputs:
            painter.setPen(QColor("#E74C3C"))
            painter.drawText(QRectF(10, 70, 130, 15), Qt.AlignLeft, f"输出: {len(outputs)}")

        painter.end()
        return pixmap

    def build_component_tree(self):
        self.clear()
        categories = {}

        for full_path, comp_cls in self.component_map.items():
            category, name = full_path.split("/", 1)
            if category not in categories:
                cat_item = QTreeWidgetItem([category])
                self.addTopLevelItem(cat_item)
                categories[category] = cat_item
            else:
                cat_item = categories[category]
            cat_item.addChild(QTreeWidgetItem([name]))

        self.expandAll()

    def refresh_components(self):
        """刷新组件树"""
        # 重新扫描组件目录
        self.component_map, _ = scan_components()
        self.build_component_tree()