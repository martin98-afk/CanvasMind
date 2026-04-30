# -*- coding: utf-8 -*-
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QWidget,
    QScrollArea,
)
from typing import Dict, List
from qfluentwidgets import (
    BodyLabel,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    SwitchButton,
    FluentIcon,
    TransparentToolButton,
    ListWidget,
    ComboBox,
    SegmentedWidget,
)
from qfluentwidgets.components.widgets.card_widget import CardSeparator
from app.utils.utils import get_font_family_css

MEMORY_CATEGORIES_WIDGET = {
    "agent_identity": "【智能体自身身份记忆】",
    "user_identity": "【用户身份记忆】",
    "task_preference": "【用户任务偏好】",
    "task_taboos": "【任务忌讳】",
    "key_knowledge": "【关键事实】",
}

MEMORY_CATEGORY_SHORT_NAMES = {
    "agent_identity": "智能体身份",
    "user_identity": "用户身份",
    "task_preference": "任务偏好",
    "task_taboos": "任务忌讳",
    "key_knowledge": "关键事实",
}


class MemoryItemWidget(QWidget):
    """记忆项显示组件"""

    deleted = pyqtSignal(int)
    toggled = pyqtSignal(int, bool)

    def __init__(
        self,
        item_id: int,
        content: str,
        enabled: bool = True,
        meta_text: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.item_id = item_id
        self.content = content
        self.meta_text = meta_text
        self._init_ui(enabled)

    def _init_ui(self, enabled):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 8, 5, 8)
        main_layout.setSpacing(0)

        text_wrap = QWidget(self)
        text_layout = QVBoxLayout(text_wrap)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self.label = BodyLabel(self.content, self)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("padding: 5px 10px 0 10px;")
        text_layout.addWidget(self.label)

        if self.meta_text:
            self.meta_label = BodyLabel(self.meta_text, self)
            self.meta_label.setWordWrap(True)
            self.meta_label.setStyleSheet(f"padding: 0 10px 5px 10px; color: #8c99ad; {get_font_family_css()} font-size: 11px;")
            text_layout.addWidget(self.meta_label)

        main_layout.addWidget(text_wrap, 1)
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
        self._current_category = "agent_identity"
        self._category_indices: Dict[str, int] = {}
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
                padding: 0;
                border-bottom: 1px solid #3e3e42;
            }
            QListWidget::item:selected {
                background-color: #094771;
            }
            QLineEdit {
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
            BodyLabel {
                color: #e0e0e0;
            }
            QComboBox {
                background-color: #252526;
                border: 1px solid #3e3e42;
                color: #e0e0e0;
                padding: 5px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #e0e0e0;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        title = BodyLabel("长期记忆管理", self)
        title.setStyleSheet(f"{get_font_family_css()} font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        desc = BodyLabel("分类管理用户的偏好、特定需求和用户导向型内容", self)
        desc.setStyleSheet(f"color: #888; {get_font_family_css()} font-size: 12px;")
        layout.addWidget(desc)

        self.segmented_widget = SegmentedWidget(self)
        segment_keys = list(MEMORY_CATEGORIES_WIDGET.keys())
        for k in segment_keys:
            self.segmented_widget.addItem(k, MEMORY_CATEGORY_SHORT_NAMES[k])
        self.segmented_widget.setCurrentItem(segment_keys[0])
        self.segmented_widget.currentItemChanged.connect(self._on_category_changed)
        layout.addWidget(self.segmented_widget)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)
        self.category_header = BodyLabel(self)
        self.category_header.setStyleSheet(f"font-weight: bold; {get_font_family_css()} font-size: 14px;")
        self.category_count_label = BodyLabel(self)
        self.category_count_label.setStyleSheet(f"color: #888; {get_font_family_css()} font-size: 12px;")
        header_layout.addWidget(self.category_header, 1)
        header_layout.addWidget(self.category_count_label, 0, Qt.AlignVCenter | Qt.AlignRight)  # type: ignore
        layout.addLayout(header_layout)

        self.list_widget = ListWidget(self)
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        layout.addWidget(self.list_widget, 1)

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

        self._load_memories()

    def _on_category_changed(self, key: str):
        if key in MEMORY_CATEGORIES_WIDGET:
            self._current_category = key
            self.category_header.setText(MEMORY_CATEGORIES_WIDGET[self._current_category])
            self._load_memories()

    def _update_category_count_label(self, category_memories: Dict[str, List]):
        counts = {k: len(v) for k, v in category_memories.items()}
        total = sum(counts.values())
        current_count = counts.get(self._current_category, 0)
        from app.llm_chatter.core.memory_manager import MEMORY_CATEGORY_LIMITS
        limit = MEMORY_CATEGORY_LIMITS.get(self._current_category, 20)
        self.category_count_label.setText(
            f"当前分类: {current_count}/{limit} | 总记忆: {total}"
        )

    def _load_memories(self):
        self.list_widget.clear()

        category_memories: Dict[str, List[tuple]] = {k: [] for k in MEMORY_CATEGORIES_WIDGET}

        global_index = 0
        for i, mem in enumerate(self.memories):
            if isinstance(mem, dict):
                content = mem.get("content", "")
                enabled = mem.get("enabled", True)
                source = mem.get("source", "manual")
                confidence = mem.get("confidence", 0.8)
                hit_count = mem.get("hit_count", 0)
                last_used = mem.get("last_used_at", "")
                category = mem.get("category", "task_preference")
                meta_parts = [f"source={source}", f"conf={confidence:.2f}"]
                if hit_count > 0:
                    meta_parts.append(f"hits={hit_count}")
                if last_used:
                    days_ago = ""
                    try:
                        from datetime import datetime as dt
                        used_date = dt.strptime(last_used, "%Y-%m-%d %H:%M:%S")
                        days = (dt.now() - used_date).days
                        if days == 0:
                            days_ago = "today"
                        elif days == 1:
                            days_ago = "1d"
                        else:
                            days_ago = f"{days}d"
                        meta_parts.append(f"used={days_ago}")
                    except:
                        pass
                meta_text = " | ".join(meta_parts)
            else:
                content = str(mem)
                enabled = True
                meta_text = "source=legacy"
                category = "task_preference"

            if category not in MEMORY_CATEGORIES_WIDGET:
                category = "task_preference"

            category_memories[category].append((global_index, content, enabled, meta_text))
            global_index += 1

        self.category_header.setText(MEMORY_CATEGORIES_WIDGET[self._current_category])
        self._update_category_count_label(category_memories)
        current_memories = category_memories.get(self._current_category, [])

        for idx, (item_id, content, enabled, meta_text) in enumerate(current_memories):
            item = QListWidgetItem(self.list_widget)
            widget = MemoryItemWidget(item_id, content, enabled, meta_text=meta_text)
            widget.deleted.connect(self._delete_item)
            widget.toggled.connect(self._toggle_item)
            self.list_widget.setItemWidget(item, widget)
            item.setSizeHint(widget.sizeHint())

    def _get_memory_index_from_item_id(self, item_id: int) -> int:
        category_memories: Dict[str, List[tuple]] = {k: [] for k in MEMORY_CATEGORIES_WIDGET}
        global_index = 0
        for i, mem in enumerate(self.memories):
            if isinstance(mem, dict):
                category = mem.get("category", "task_preference")
            else:
                category = "task_preference"
            if category not in MEMORY_CATEGORIES_WIDGET:
                category = "task_preference"
            category_memories[category].append((global_index, i))
            global_index += 1

        current_memories = category_memories.get(self._current_category, [])
        for local_idx, (item_id_check, mem_idx) in enumerate(current_memories):
            if item_id_check == item_id:
                return mem_idx
        return -1

    def _add_memory(self):
        content = self.input_edit.text().strip()
        if not content:
            return

        new_entry = {
            "content": content,
            "enabled": True,
            "confidence": 0.8,
            "source": "manual",
            "last_used_at": "",
            "conflict_group": "",
            "category": self._current_category,
        }

        if isinstance(self.memories, list):
            self.memories.append(new_entry)

        self.input_edit.clear()
        self._load_memories()

    def _delete_item(self, item_id: int):
        mem_idx = self._get_memory_index_from_item_id(item_id)
        if 0 <= mem_idx < len(self.memories):
            self.memories.pop(mem_idx)
            self._load_memories()

    def _toggle_item(self, item_id: int, enabled: bool):
        mem_idx = self._get_memory_index_from_item_id(item_id)
        if 0 <= mem_idx < len(self.memories):
            if isinstance(self.memories[mem_idx], dict):
                self.memories[mem_idx]["enabled"] = enabled
            else:
                self.memories[mem_idx] = {
                    "content": str(self.memories[mem_idx]),
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
                enabled_memories.append({"content": str(mem), "enabled": True, "category": "task_preference"})

        self.memories = enabled_memories
        self._load_memories()

    def _save_and_close(self):
        self.memoryUpdated.emit(self.memories)
        self.accept()

    def get_memories(self) -> list:
        return self.memories
