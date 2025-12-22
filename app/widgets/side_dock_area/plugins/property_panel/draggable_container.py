# -*- coding: utf-8 -*-
import numpy as np
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QListWidgetItem, QFrame
from PyQt5.QtCore import Qt, QMimeData, QTimer
from PyQt5.QtGui import QDrag, QPainter, QColor
from qfluentwidgets import (
    CardWidget, BodyLabel, SubtitleLabel,
    TransparentToolButton, FluentIcon, InfoBar, InfoBarPosition
)

from app.utils.utils import topological_sort
from app.widgets.side_dock_area.plugins.property_panel.internal_node_list import InternalNodeList

# ===== 新增：插入位置预览线 =====
class InsertionIndicator(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(3)
        self.setStyleSheet("background-color: #4A90E2; border-radius: 1px;")
        self.hide()


# ===== 优化后的可拖拽容器 =====
class DraggableContainer(QWidget):
    def __init__(self, panel_widget):
        super().__init__()
        self.panel_widget = panel_widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)  # 为插入线留空间
        self.setAcceptDrops(True)
        self.setAcceptDrops(True)

        self.insert_line = InsertionIndicator(self)
        self._current_target_index = -1

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text().startswith("component_index:"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if not (event.mimeData().hasText() and event.mimeData().text().startswith("component_index:")):
            event.ignore()
            return

        layout = self.layout()
        cards = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), CardWidget):
                cards.append(item.widget())

        drop_y = event.pos().y()
        insert_index = len(cards)  # 默认插在最后

        if cards:
            for i, card in enumerate(cards):
                card_top = card.y()
                card_center = card_top + card.height() / 2
                if drop_y < card_center:
                    insert_index = i
                    break

        self._show_insert_line_at(insert_index)
        event.accept()

    def dragLeaveEvent(self, event):
        self.insert_line.hide()
        self._current_target_index = -1
        event.accept()

    def dropEvent(self, event):
        if not (event.mimeData().hasText() and event.mimeData().text().startswith("component_index:")):
            return

        try:
            source_idx = int(event.mimeData().text().split(":")[1])
        except (ValueError, IndexError):
            return

        layout = self.layout()
        cards = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), CardWidget):
                cards.append(item.widget())

        if not cards or source_idx < 0 or source_idx >= len(cards):
            self.insert_line.hide()
            self._current_target_index = -1
            return

        drop_y = event.pos().y()
        target_index = len(cards)
        for i, card in enumerate(cards):
            if drop_y < card.y() + card.height() / 2:
                target_index = i
                break

        if target_index == source_idx or (target_index == source_idx + 1):
            self.insert_line.hide()
            self._current_target_index = -1
            return

        # 更新数据模型
        comp = self.panel_widget._current_components.pop(source_idx)
        insert_idx = target_index if target_index <= source_idx else target_index - 1
        self.panel_widget._current_components.insert(insert_idx, comp)

        self.insert_line.hide()
        self._current_target_index = -1

        # 刷新 UI
        self.panel_widget._refresh_ui_from_current_components()
        event.accept()

    def _show_insert_line_at(self, index):
        if self._current_target_index == index:
            return

        layout = self.layout()
        cards = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), CardWidget):
                cards.append(item.widget())

        if index == 0:
            y = 0
        elif index >= len(cards):
            y = cards[-1].y() + cards[-1].height() if cards else 0
        else:
            y = cards[index].y()

        self.insert_line.move(0, y)
        self.insert_line.resize(self.width(), 3)
        self.insert_line.show()
        self._current_target_index = index

    def resizeEvent(self, event):
        if self.insert_line.isVisible():
            self.insert_line.resize(self.width(), 3)
        super().resizeEvent(event)