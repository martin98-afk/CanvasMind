# coding:utf-8
from PyQt5.QtCore import Qt, QSize, QRect
from PyQt5.QtGui import QPainter, QColor, QPen, QFont
from PyQt5.QtWidgets import (
    QComboBox,
    QStyle,
    QStyleOptionComboBox,
    QStyleFactory,
    QStyledItemDelegate,
    QFrame,
)
from qfluentwidgets import isDarkTheme, themeColor

from app.utils.config import Settings
from app.utils.utils import get_unified_font


class ProfessionalComboBoxDelegate(QStyledItemDelegate):
    """
    专业级下拉项委托：强化选中标记（左侧竖条 + 背景高亮）
    """

    def sizeHint(self, option, index):
        return QSize(super().sizeHint(option, index).width(), 34)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # 1. 获取状态逻辑
        view = option.widget
        if not view:
            return super().paint(painter, option, index)

        # 向上查找 ComboBox 实例以获取当前选中索引
        combo = view.parent()
        while combo and not isinstance(combo, QComboBox):
            combo = combo.parent()

        is_current = (index.row() == combo.currentIndex()) if combo else False
        is_hover = option.state & QStyle.State_Selected

        rect = option.rect

        # 2. 绘制背景层
        if is_hover:
            # 悬停背景：浅灰色
            bg_color = (
                QColor(255, 255, 255, 15) if isDarkTheme() else QColor(0, 0, 0, 10)
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(bg_color)
            painter.drawRoundedRect(rect.adjusted(4, 2, -4, -2), 5, 5)

        if is_current:
            # 选中背景：主题色半透明
            bg_color = themeColor()
            bg_color.setAlpha(45)
            painter.setPen(Qt.NoPen)
            painter.setBrush(bg_color)
            painter.drawRoundedRect(rect.adjusted(4, 2, -4, -2), 5, 5)

        # 3. 绘制左侧选中标记 (竖条指示器)
        if is_current:
            painter.setBrush(themeColor())
            painter.setPen(Qt.NoPen)
            # 绘制高度比例协调的圆角竖条
            indicator_rect = QRect(rect.x() + 7, rect.y() + 8, 4, rect.height() - 16)
            painter.drawRoundedRect(indicator_rect, 2, 2)

        # 4. 绘制文本内容
        if is_current:
            # 选中项文字：加粗，颜色高亮
            painter.setPen(QColor(255, 255, 255) if isDarkTheme() else themeColor())
            painter.setFont(get_unified_font(10, True))
        else:
            # 非选中项文字
            painter.setPen(
                QColor(210, 210, 210) if isDarkTheme() else QColor(50, 50, 50)
            )
            painter.setFont(get_unified_font(10))

        # 文字整体向右偏移，为左侧指示条留出呼吸空间
        text_rect = rect.adjusted(24, 0, -10, 0)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, str(index.data()))

        painter.restore()


class CustomComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)

        # 强制使用 Windows 风格以获得最佳的 UI 可控性
        self.setStyle(QStyleFactory.create("Windows"))
        self.setItemDelegate(ProfessionalComboBoxDelegate(self))

        # 下拉列表配置
        view = self.view()
        view.setFrameShape(QFrame.NoFrame)
        # 允许下拉框圆角区域透明
        view.viewport().setAttribute(Qt.WA_TranslucentBackground)

        self.setFixedHeight(35)
        self._setup_style()

    def _setup_style(self):
        dark = isDarkTheme()
        t_color = themeColor().name()
        font = self.font()
        font.setFamily(Settings.get_instance().canvas_font_selected.value)
        self.setFont(font)
        # 定义颜色变量
        bg = "#2D2D2D" if dark else "#FFFFFF"
        border = "#1A1A1A" if dark else "#DCDCDC"
        text = "#FFFFFF" if dark else "#000000"
        popup_bg = "#252525" if dark else "#FFFFFF"

        self.setStyleSheet(f"""
            QComboBox {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 2px 30px 2px 12px;
                color: {text};
                font-family: 'Segoe UI', 'Microsoft YaHei';
                font-size: 15px;
            }}
            QComboBox:hover {{
                border: 1px solid {t_color};
                background-color: {"#353535" if dark else "#F9F9F9"};
            }}
            QComboBox:on {{
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 30px;
            }}
            /* 下拉框容器样式 */
            QAbstractItemView {{
                background-color: {popup_bg};
                border: 1px solid {t_color if dark else border};
                border-radius: 6px;
                outline: 0px;
                padding: 4px 0px;
            }}
        """)

        # 滚动条美化
        self.view().verticalScrollBar().setStyleSheet("""
            QScrollBar:vertical { background: transparent; width: 6px; margin-right: 2px; }
            QScrollBar::handle:vertical { background: rgba(120, 120, 120, 200); border-radius: 4px; }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0px; }
        """)

    def paintEvent(self, event):
        """绘制工业感十足的 V 型细线箭头"""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 计算箭头位置
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        rect = self.style().subControlRect(
            QStyle.CC_ComboBox, opt, QStyle.SC_ComboBoxArrow, self
        )

        # 箭头颜色交互：悬停变色
        color = (
            themeColor()
            if self.underMouse()
            else (QColor(160, 160, 160) if isDarkTheme() else QColor(100, 100, 100))
        )
        painter.setPen(QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))

        center = rect.center()
        # 绘制简练的 V 型线
        painter.drawLine(center.x() - 4, center.y() - 1, center.x(), center.y() + 3)
        painter.drawLine(center.x(), center.y() + 3, center.x() + 4, center.y() - 1)
