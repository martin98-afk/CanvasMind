# -*- coding: utf-8 -*-
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QWidget,
    QFrame,
)
from qfluentwidgets import (
    BodyLabel,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    SwitchButton, ToggleToolButton, FluentIcon, TransparentToolButton, ListWidget,
)
from qfluentwidgets.components.widgets.card_widget import CardSeparator


class MemoryItemWidget(QWidget):
    """记忆项显示组件"""

    deleted = pyqtSignal(int)
    toggled = pyqtSignal(int, bool)

    def __init__(self, item_id: int, content: str, enabled: bool = True, parent=None):
        super().__init__(parent)
        self.item_id = item_id
        self.content = content
        self._init_ui(enabled)

    def _init_ui(self, enabled):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 8, 5, 8)
        main_layout.setSpacing(0)

        self.label = BodyLabel(self.content, self)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("padding: 5px 10px;")
        main_layout.addWidget(self.label, 1)
        main_layout.addWidget(CardSeparator())

        self.switch = SwitchButton(self)
        self.switch.setChecked(enabled)
        self.switch.setOnText("")
        self.switch.setOffText("")
        self.switch.checkedChanged.connect(
            lambda checked: self.toggled.emit(self.item_id, checked)
        )
        main_layout.addWidget(self.switch)

        main_layout.addWidget(CardSeparator())
        self.delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
        self.delete_btn.clicked.connect(lambda: self.deleted.emit(self.item_id))
        main_layout.addWidget(self.delete_btn)


class MemoryManagerDialog(QDialog):
    memoryUpdated = pyqtSignal(list)

    def __init__(self, memories: list, parent=None):
        super().__init__(parent)
        self.memories = memories if memories else []
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("长期记忆管理")
        self.setMinimumSize(800, 600)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #e0e0e0;
            }
            QListWidget {
                background-color: #252526;
                border: 1px solid #3e3e42;
                color: #e0e0e0;
            }
            QListWidget::item {
                padding: 5px;
                border-bottom: 1px solid #3e3e42;
            }
            QListWidget::item:selected {
                background-color: #094771;
            }
            QLineEdit, QTextEdit {
                background-color: #252526;
                border: 1px solid #3e3e42;
                color: #e0e0e0;
                padding: 5px;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0d5a8f;
            }
            QCheckBox {
                color: #e0e0e0;
            }
            BodyLabel {
                color: #e0e0e0;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        title = BodyLabel("长期记忆管理", self)
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        desc = BodyLabel("管理用户的偏好、特定需求和用户导向型内容", self)
        desc.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(desc)

        layout.addWidget(BodyLabel("记忆列表（勾选启用）:", self))

        self.list_widget = ListWidget(self)
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        layout.addWidget(self.list_widget)

        self._load_memories()

        input_layout = QHBoxLayout()
        self.input_edit = LineEdit(self)
        self.input_edit.setPlaceholderText("添加新的记忆...")
        self.add_btn = PrimaryPushButton("添加", self)
        self.add_btn.clicked.connect(self._add_memory)
        input_layout.addWidget(self.input_edit, 1)
        input_layout.addWidget(self.add_btn)
        layout.addLayout(input_layout)

        btn_layout = QHBoxLayout()

        select_all_btn = PushButton("全部启用", self)
        select_all_btn.clicked.connect(self._select_all)

        deselect_all_btn = PushButton("全部关闭", self)
        deselect_all_btn.clicked.connect(self._deselect_all)

        clear_disabled_btn = PushButton("删除未启用", self)
        clear_disabled_btn.clicked.connect(self._clear_disabled)

        btn_layout.addWidget(select_all_btn)
        btn_layout.addWidget(deselect_all_btn)
        btn_layout.addWidget(clear_disabled_btn)
        btn_layout.addStretch()

        cancel_btn = PushButton("取消", self)
        cancel_btn.clicked.connect(self.reject)

        save_btn = PrimaryPushButton("保存", self)
        save_btn.clicked.connect(self._save_and_close)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def _load_memories(self):
        self.list_widget.clear()
        for i, mem in enumerate(self.memories):
            if isinstance(mem, dict):
                content = mem.get("content", "")
                enabled = mem.get("enabled", True)
            else:
                content = str(mem)
                enabled = True

            item = QListWidgetItem(self.list_widget)
            widget = MemoryItemWidget(i, content, enabled)
            widget.deleted.connect(self._delete_item)
            widget.toggled.connect(self._toggle_item)
            self.list_widget.setItemWidget(item, widget)
            item.setSizeHint(widget.sizeHint())

    def _add_memory(self):
        content = self.input_edit.text().strip()
        if not content:
            return

        if isinstance(self.memories, list):
            self.memories.append({"content": content, "enabled": True})
        else:
            self.memories.append({"content": content, "enabled": True})

        self.input_edit.clear()
        self._load_memories()

    def _delete_item(self, item_id: int):
        if 0 <= item_id < len(self.memories):
            self.memories.pop(item_id)
            self._load_memories()

    def _toggle_item(self, item_id: int, enabled: bool):
        if 0 <= item_id < len(self.memories):
            if isinstance(self.memories[item_id], dict):
                self.memories[item_id]["enabled"] = enabled
            else:
                self.memories[item_id] = {
                    "content": str(self.memories[item_id]),
                    "enabled": enabled,
                }

    def _select_all(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            widget = self.list_widget.itemWidget(item)
            if widget:
                widget.switch.setChecked(True)

    def _deselect_all(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            widget = self.list_widget.itemWidget(item)
            if widget:
                widget.switch.setChecked(False)

    def _clear_disabled(self):
        enabled_memories = []
        for mem in self.memories:
            if isinstance(mem, dict):
                if mem.get("enabled", True):
                    enabled_memories.append(mem)
            else:
                enabled_memories.append({"content": str(mem), "enabled": True})

        self.memories = enabled_memories
        self._load_memories()

    def _save_and_close(self):
        self.memoryUpdated.emit(self.memories)
        self.accept()

    def get_memories(self) -> list:
        return self.memories
