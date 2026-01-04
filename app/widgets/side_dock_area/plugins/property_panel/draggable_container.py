# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QFrame
from PyQt5.QtCore import Qt
from qfluentwidgets import CardWidget


class InsertionIndicator(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(3)
        self.setStyleSheet("background-color: #4A90E2; border-radius: 1px;")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)  # 别挡着 Drop
        self.hide()


class DraggableContainer(QWidget):
    def __init__(self, panel_widget):
        super().__init__(panel_widget)
        self.panel_widget = panel_widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)
        self.setAcceptDrops(True)

        self.insert_line = InsertionIndicator(self)
        self._current_target_index = -1

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text().startswith("component_index:"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        layout = self.layout()
        cards = [layout.itemAt(i).widget() for i in range(layout.count())
                 if layout.itemAt(i).widget() and isinstance(layout.itemAt(i).widget(), CardWidget)]

        drop_y = event.pos().y()
        insert_index = len(cards)

        for i, card in enumerate(cards):
            # 计算中点触发
            if drop_y < (card.y() + card.height() / 2):
                insert_index = i
                break

        self._show_insert_line_at(insert_index, cards)
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.insert_line.hide()
        self._current_target_index = -1

    def dropEvent(self, event):
        data = event.mimeData().text()
        try:
            source_idx = int(data.split(":")[1])
        except:
            return

        layout = self.layout()
        cards = [layout.itemAt(i).widget() for i in range(layout.count())
                 if layout.itemAt(i).widget() and isinstance(layout.itemAt(i).widget(), CardWidget)]

        drop_y = event.pos().y()
        target_index = len(cards)
        for i, card in enumerate(cards):
            if drop_y < card.y() + card.height() / 2:
                target_index = i
                break

        self.insert_line.hide()

        # 逻辑：如果是原位或紧随其后，不处理
        if target_index == source_idx or target_index == source_idx + 1:
            return

        # 移动数据
        comp = self.panel_widget._current_components.pop(source_idx)
        # 计算新索引
        new_idx = target_index if target_index <= source_idx else target_index - 1
        self.panel_widget._current_components.insert(new_idx, comp)

        # 刷新 UI (调用优化后的刷新方法)
        self.panel_widget._refresh_ui_from_current_components()
        event.acceptProposedAction()

    def _show_insert_line_at(self, index, cards):
        if self._current_target_index == index: return

        if index == 0:
            y = 5
        elif index >= len(cards):
            y = cards[-1].y() + cards[-1].height() + 4
        else:
            y = cards[index].y() - 4

        self.insert_line.move(0, y)
        self.insert_line.resize(self.width(), 3)
        self.insert_line.show()
        self.insert_line.raise_()  # 确保在最上层
        self._current_target_index = index

    def resizeEvent(self, event):
        self.insert_line.resize(self.width(), 3)
        super().resizeEvent(event)