# -*- coding: utf-8 -*-
from collections import defaultdict

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from qfluentwidgets import (
    MessageBoxBase, ScrollArea, VBoxLayout,
    SubtitleLabel, StrongBodyLabel, CardWidget,
    PushButton, SegmentedWidget, LineEdit
)


class InputSelectionDialog(MessageBoxBase):
    def __init__(self, candidate_items, parent=None, current_selected_items=None):
        super().__init__(parent)
        self.candidate_items = candidate_items
        # current_selected_items: Dict where key is custom_key, value is item detail from project_spec
        self.current_selected_items = current_selected_items or {}
        # 存储: (checkbox, line_edit, item)
        self.item_widgets = []

        title_label = SubtitleLabel('选择项目输入参数（未勾选的将使用当前值固化）', self)
        self.viewLayout.addWidget(title_label)

        # 分组
        input_ports = [item for item in candidate_items if item["type"] == "组件输入"]
        component_params = [item for item in candidate_items if item["type"] == "组件超参数"]

        input_groups = defaultdict(list)
        param_groups = defaultdict(list)
        for item in input_ports:
            input_groups[(item["node_id"], item["node_name"])].append(item)
        for item in component_params:
            param_groups[(item["node_id"], item["node_name"])].append(item)

        # 分段
        segmented_widget = SegmentedWidget(self)
        segmented_widget.addItem("ports", "输入端口")
        segmented_widget.addItem("params", "组件参数")
        segmented_widget.setCurrentItem("ports")
        self.viewLayout.addWidget(segmented_widget)

        self.scroll_ports = self._create_grouped_scroll(input_groups, is_input=True)
        self.scroll_params = self._create_grouped_scroll(param_groups, is_input=True)

        self.viewLayout.addWidget(self.scroll_ports)
        self.viewLayout.addWidget(self.scroll_params)
        self.scroll_params.hide()

        segmented_widget.currentItemChanged.connect(
            lambda name: (
                self.scroll_ports.setVisible(name == "ports"),
                self.scroll_params.setVisible(name == "params")
            )
        )

        self.yesButton.setText('确定')
        self.cancelButton.setText('取消')

    def _create_grouped_scroll(self, groups, is_input=True):
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
            layout.addWidget(StrongBodyLabel("暂无项目"))
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

            # 按组件分组
            for (node_id, node_name), items in groups.items():
                card = CardWidget()
                card_layout = VBoxLayout(card)
                card_layout.setContentsMargins(16, 16, 16, 16)

                title = StrongBodyLabel(node_name)
                card_layout.addWidget(title)

                for idx, item in enumerate(items):
                    # 每行：CheckBox + Label + LineEdit
                    row = QWidget()
                    row_layout = QHBoxLayout(row)
                    row_layout.setContentsMargins(0, 0, 0, 0)

                    from qfluentwidgets import CheckBox
                    cb = CheckBox()

                    # --- Pre-populate Check State and Custom Key ---
                    is_selected = False
                    custom_key = ""
                    # Find if this candidate item matches any in current_selected_items
                    for spec_key, spec_details in self.current_selected_items.items():
                        if (spec_details.get('node_id') == item.get('node_id') and
                            ((spec_details.get('param_name') and spec_details.get('param_name') == item.get('param_name')) or
                             (spec_details.get('port_name') and spec_details.get('port_name') == item.get('port_name')))):
                            is_selected = True
                            custom_key = spec_details.get('custom_key', spec_key)
                            break

                    cb.setChecked(is_selected)

                    # 显示名称
                    name_label = QLabel(item["display_name"])
                    name_label.setStyleSheet("font-size: 14px;")

                    # Key 输入框
                    key_edit = LineEdit()
                    key_edit.setFixedWidth(120)
                    # Set the pre-filled custom key, or default to param/port name
                    if custom_key:
                        key_edit.setText(custom_key)
                    else:
                        default_key = item.get("port_name") or item.get("param_name")
                        key_edit.setText(default_key)
                    key_edit.setPlaceholderText("输入key")

                    # Enable/disable key_edit based on checkbox
                    key_edit.setEnabled(is_selected)
                    cb.stateChanged.connect(lambda state, w=key_edit: w.setEnabled(state == Qt.Checked))

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
        return scroll_area

    def _set_all_checked(self, checked):
        for cb, key_edit, _ in self.item_widgets:
            cb.setChecked(checked)
            key_edit.setEnabled(checked)

    def get_selected_items(self):
        selected = []
        for cb, key_edit, item in self.item_widgets:
            if cb.isChecked():
                item = item.copy()
                item["custom_key"] = key_edit.text().strip() or f"input_{len(selected)}"
                selected.append(item)
        return selected