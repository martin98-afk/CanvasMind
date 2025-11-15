# coding:utf-8
from PyQt5.QtCore import Qt, pyqtSignal, QPoint
from PyQt5.QtGui import QPainter, QColor, QPen
from PyQt5.QtWidgets import (QComboBox, QStyle, QStyleOptionComboBox,
                             QFrame)

from qfluentwidgets import FluentStyleSheet, isDarkTheme
from qfluentwidgets.common.font import setFont
from qfluentwidgets.common.style_sheet import themeColor


class CustomComboBox(QComboBox):
    """
    Fluent风格的ComboBox，使用QComboBox的原生下拉功能
    解决在nodegraphqt环境中RoundMenu显示问题
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # 应用fluent样式
        FluentStyleSheet.COMBO_BOX.apply(self)
        # 设置样式和字体
        setFont(self)
        self.setStyleSheet(self._getFluentStyle())

    def _getFluentStyle(self):
        """ 获取fluent风格的样式表 """
        # 可以根据主题调整颜色
        bg_color = "#ffffff" if not isDarkTheme() else "rgba(32, 32, 32, 100)"
        border_color = "#d3d3d3" if not isDarkTheme() else "#3c3c3c"
        text_color = "#000000" if not isDarkTheme() else "#ffffff"

        return f"""
            QComboBox {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 4px;
                padding: 4px 10px 4px 10px;
                color: {text_color};
                font-size: 14px;
            }}
            QComboBox:hover {{
                border-color: {themeColor().name()};
            }}
            QComboBox:focus {{
                border-color: {themeColor().name()};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid {border_color};
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
            }}
            QComboBox::down-arrow {{
                image: none; /* 我们将在paintEvent中手动绘制箭头 */
            }}
            QComboBox QAbstractItemView {{
               background-color: #323232;
               border: 1px solid #545454;
               border-radius: 5px;
               selection-background-color: #0078d4;
               selection-color: white;
               color: white;
               outline: 0;
               padding: 4px 0;             /* 增加上下内边距，避免贴边 */
               font-size: 14px;            /* ⬅️ 关键：增大下拉项字体 */
               font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
           }}
           QComboBox QAbstractItemView::item {{
                min-height: 36px;      /* 从 32px → 36px */
                padding: 8px 16px;     /* 从 6px 12px → 8px 16px */
                border-bottom: 1px solid #444444; /* 添加分隔线更清晰 */
            }}
           QComboBox QAbstractItemView::item:selected {{
               background-color: #0078d4;
           }}
        """

    def paintEvent(self, event):
        """ 重写paintEvent以绘制fluent风格的下拉箭头 """
        super().paintEvent(event)

        # 绘制fluent风格的箭头
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)

        # 计算箭头位置（在右侧）
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        arrow_rect = self.style().subControlRect(
            QStyle.CC_ComboBox, opt, QStyle.SC_ComboBoxArrow, self
        )

        # 调整箭头位置以更好地居中
        arrow_size = 10
        arrow_x = arrow_rect.center().x() - arrow_size // 2
        arrow_y = arrow_rect.center().y() - arrow_size // 2

        # 根据主题设置颜色
        arrow_color = QColor("#646464") if not isDarkTheme() else QColor("#ffffff")

        # 绘制箭头
        painter.setPen(QPen(arrow_color, 1.5))
        painter.setBrush(arrow_color)

        # 绘制向下的箭头（三角形）
        points = [
            QPoint(arrow_x, arrow_y + 2),
            QPoint(arrow_x + arrow_size, arrow_y + 2),
            QPoint(arrow_x + arrow_size // 2, arrow_y + arrow_size - 2)
        ]
        painter.drawPolygon(points)