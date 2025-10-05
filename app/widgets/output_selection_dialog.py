# -*- coding: utf-8 -*-
from collections import defaultdict
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from qfluentwidgets import (
    MessageBoxBase, ScrollArea, VBoxLayout,
    SubtitleLabel, StrongBodyLabel, CardWidget,
    PushButton, LineEdit
)


class OutputSelectionDialog(MessageBoxBase):
    def __init__(self, candidate_items, parent=None):
        super().__init__(parent)
        self.candidate_items = candidate_items
        self.item_widgets = []  # (checkbox, line_edit, item)

        title_label = SubtitleLabel('选择项目输出结果', self)
        self.viewLayout.addWidget(title_label)

        # 按组件分组
        groups = defaultdict(list)
        for item in candidate_items:
            groups[(item["node_id"], item["node_name"])].append(item)

        scroll_area = ScrollArea()
        scroll_widget = QWidget()
        scroll_widget.setAttribute(Qt.WA_TranslucentBackground)
        scroll_area.setAttribute(Qt.WA_TranslucentBackground)
        scroll_area.setStyleSheet("background: transparent; border: none;")
        scroll_widget.setStyleSheet("background: transparent;")

        layout = VBoxLayout(scroll_widget)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 0, 0)

        if not groups:
            layout.addWidget(StrongBodyLabel("暂无输出"))
        else:
            btn_layout = QHBoxLayout()
            select_all = PushButton('全选')
            deselect_all = PushButton('全不选')
            select_all.clicked.connect(lambda: self._set_all_checked(True))
            deselect_all.clicked.connect(lambda: self._set_all_checked(False))
            btn_layout.addWidget(select_all)
            btn_layout.addWidget(deselect_all)
            btn_layout.addStretch()
            layout.addLayout(btn_layout)

            for (node_id, node_name), items in groups.items():
                card = CardWidget()
                card_layout = VBoxLayout(card)
                card_layout.setContentsMargins(16, 16, 16, 16)

                title = StrongBodyLabel(node_name)
                card_layout.addWidget(title)

                for idx, item in enumerate(items):
                    row = QWidget()
                    row_layout = QHBoxLayout(row)
                    row_layout.setContentsMargins(0, 0, 0, 0)

                    from qfluentwidgets import CheckBox
                    cb = CheckBox()
                    cb.setChecked(False)

                    name_label = QLabel(item["display_name"])
                    name_label.setStyleSheet("font-size: 14px;")

                    key_edit = LineEdit()
                    key_edit.setFixedWidth(120)
                    default_key = f"output_{len(self.item_widgets)}"
                    key_edit.setText(default_key)
                    key_edit.setPlaceholderText("输出key")

                    row_layout.addWidget(cb)
                    row_layout.addWidget(name_label)
                    row_layout.addStretch()
                    row_layout.addWidget(QLabel("Key:"))
                    row_layout.addWidget(key_edit)

                    card_layout.addWidget(row)
                    self.item_widgets.append((cb, key_edit, item))

                layout.addWidget(card)

        layout.addStretch()
        scroll_widget.setLayout(layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedSize(680, 420)

        self.viewLayout.addWidget(scroll_area)

        self.yesButton.setText('确定')
        self.cancelButton.setText('取消')

    def _set_all_checked(self, checked):
        for cb, _, _ in self.item_widgets:
            cb.setChecked(checked)

    def get_selected_items(self):
        selected = []
        for cb, key_edit, item in self.item_widgets:
            if cb.isChecked():
                item = item.copy()
                item["custom_key"] = key_edit.text().strip() or f"output_{len(selected)}"
                selected.append(item)
        return selected