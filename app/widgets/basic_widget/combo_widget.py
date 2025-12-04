# coding:utf-8
from PyQt5.QtCore import Qt, QPoint, QSize
from PyQt5.QtGui import QPainter, QColor, QPen, QFont
from PyQt5.QtWidgets import (
    QComboBox, QStyle, QStyleOptionComboBox, QStyleFactory,
    QStyledItemDelegate
)
from qfluentwidgets import FluentStyleSheet, isDarkTheme, themeColor


class FluentComboBoxDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        original = super().sizeHint(option, index)
        # 强制高度为 36px，宽度保持不变
        return QSize(original.width(), 36)

    def paint(self, painter, option, index):
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, themeColor())
            painter.setPen(Qt.white)
        else:
            painter.setPen(Qt.white if isDarkTheme() else Qt.black)
        painter.setFont(QFont('Consolas', 12))
        painter.drawText(option.rect, Qt.AlignVCenter | Qt.AlignLeft, str(index.data()))


class CustomComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)

        # 关键：绕过 Fusion 的下拉 bug
        from PyQt5.QtWidgets import QStyleFactory
        self.setStyle(QStyleFactory.create("Windows"))

        font = QFont('Consolas', 12)
        self.setFont(font)
        FluentStyleSheet.COMBO_BOX.apply(self)
        self.setStyleSheet(self._getFluentStyle())

        # 设置最大可见项
        self.setMaxVisibleItems(8)
        self.setFixedHeight(32)
        # 设置 delegate
        self.setItemDelegate(FluentComboBoxDelegate(self))

        # ✅ 现代深色滚动条样式（仅下拉列表）
        view = self.view()
        scrollbar_style = """
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 0px 0px 0px 0px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 80);
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 160);
            }
            QScrollBar::handle:vertical:pressed {
                background: rgba(255, 255, 255, 200);
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar::corner {
                background: transparent;
            }
        """
        view.setStyleSheet(scrollbar_style)

        # 可选：设置下拉窗口背景（保持与滚动条协调）
        popup = view.window()
        if popup:
            popup.setStyleSheet("QFrame { background-color: #2d2d2d; border: 1px solid #444; border-radius: 6px; }")

    def _getFluentStyle(self):
        bg = "#ffffff" if not isDarkTheme() else "rgba(32, 32, 32, 100)"
        border = "#d3d3d3" if not isDarkTheme() else "#3c3c3c"
        text = "#000000" if not isDarkTheme() else "#ffffff"
        theme_hex = themeColor().name()
        return f"""
            QComboBox {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 4px 26px 4px 10px;
                color: {text};
                font-size: 14px;
                min-height: 28px;
            }}
            QComboBox:hover {{
                border-color: {theme_hex};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid {border};
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
            }}
            QComboBox::down-arrow {{ image: none; }}
        """

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing)
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        rect = self.style().subControlRect(QStyle.CC_ComboBox, opt, QStyle.SC_ComboBoxArrow, self)
        cx, cy = rect.center().x(), rect.center().y()
        color = QColor("#646464") if not isDarkTheme() else QColor("#ffffff")
        painter.setPen(QPen(color, 1.5))
        painter.setBrush(color)
        points = [
            QPoint(cx - 5, cy - 2),
            QPoint(cx + 5, cy - 2),
            QPoint(cx, cy + 3)
        ]
        painter.drawPolygon(points)