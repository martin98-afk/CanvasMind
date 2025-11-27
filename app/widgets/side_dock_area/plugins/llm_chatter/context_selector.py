# -*- coding: utf-8 -*-

from typing import Callable, Dict, Tuple, List

from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QSize
from PyQt5.QtGui import QScreen
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QApplication, QWidget, QFrame, QSizePolicy
from qfluentwidgets import (
    FluentIcon, CheckBox, TransparentToolButton,
    CardWidget, CaptionLabel, BodyLabel
)


class ContextRegistry:
    _instance = None
    _contexts: Dict[str, Tuple[str, Callable[[], dict]]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, key: str, name: str, provider: Callable[[], dict]):
        """
        注册一个上下文项
        :param key: 唯一标识，如 "@graph"
        :param name: 显示名称，如 "当前画布"
        :param provider: 无参函数，返回上下文数据（dict）
        """
        cls._contexts[key] = (name, provider)

    @classmethod
    def unregister(cls, key: str):
        cls._contexts.pop(key, None)

    @classmethod
    def get_all_items(cls) -> List[Tuple[str, str, Callable[[], dict]]]:
        """
        返回 [(key, name, provider), ...]
        """
        return [
            (key, name, provider)
            for key, (name, provider) in cls._contexts.items()
        ]

    @classmethod
    def clear(cls):
        cls._contexts.clear()


# ==================== 【新增】单个上下文标签卡片 ====================
class TagWidget(CardWidget):
    """单个上下文标签，带关闭按钮"""
    closed = pyqtSignal(str)  # 发出 key

    def __init__(self, key: str, text: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(6)

        # 文本标签
        self.label = CaptionLabel(text, self)

        # 关闭按钮
        self.close_btn = TransparentToolButton(FluentIcon.CLOSE, self)
        self.close_btn.setFixedSize(16, 16)
        self.close_btn.setIconSize(QSize(12, 12))
        self.close_btn.clicked.connect(lambda: self.closed.emit(self.key))

        layout.addWidget(self.label)
        layout.addWidget(self.close_btn)
        layout.addStretch()


# ==================== 【新增】上下文选择 Popup ====================
class ContextSelectorPopup(QWidget):
    selectionChanged = pyqtSignal(set)

    def __init__(self, context_items: List[Tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.context_items = context_items
        self.selected_keys = set()  # 👈 默认为空，不默认全选！
        self.checkboxes = []
        self.parent_widget = parent  # 保留，但谨慎使用

        self._setup_ui()

    def set_selection(self, selected_keys: set):
        """外部主动设置选中项，用于初始化同步"""
        self.selected_keys = selected_keys.copy()
        self._update_checkboxes_from_selection()

    def _setup_ui(self):
        main_frame = QFrame(self)
        main_frame.setObjectName("popupFrame")
        main_frame.setStyleSheet("""
            QFrame#popupFrame {
                background-color: #2d2d2d;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 6px;
            }
        """)

        layout = QVBoxLayout(main_frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 添加标题
        title_label = BodyLabel("选择上下文", self)
        layout.addWidget(title_label)

        # 复选框列表
        for key, label, _ in self.context_items:
            cb = CheckBox(label, self)
            cb.stateChanged.connect(lambda state, k=key: self._on_item_toggled(k, state))
            self.checkboxes.append(cb)
            layout.addWidget(cb)

        # 设置最小宽度
        main_frame.setMinimumWidth(180)
        main_frame.adjustSize()

        # 添加到窗口
        window_layout = QVBoxLayout(self)
        window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.addWidget(main_frame)

    def _on_item_toggled(self, key: str, state: int):
        if state == Qt.Checked:
            self.selected_keys.add(key)
        else:
            self.selected_keys.discard(key)
        self.selectionChanged.emit(self.selected_keys.copy())
        if self.parent_widget and hasattr(self.parent_widget, '_on_context_selection_changed'):
            self.parent_widget._on_context_selection_changed(self.selected_keys.copy())

    def _select_all(self):
        self.selected_keys = {key for key, _ in self.context_items}
        self._update_checkboxes_from_selection()
        self.selectionChanged.emit(self.selected_keys.copy())
        if self.parent_widget and hasattr(self.parent_widget, '_on_context_selection_changed'):
            self.parent_widget._on_context_selection_changed(self.selected_keys.copy())

    def _select_none(self):
        self.selected_keys.clear()
        self._update_checkboxes_from_selection()
        self.selectionChanged.emit(self.selected_keys.copy())
        if self.parent_widget and hasattr(self.parent_widget, '_on_context_selection_changed'):
            self.parent_widget._on_context_selection_changed(self.selected_keys.copy())

    def _update_checkboxes_from_selection(self):
        """根据 selected_keys 更新所有 CheckBox 状态"""
        for cb, (key, _, _) in zip(self.checkboxes, self.context_items):
            cb.setChecked(key in self.selected_keys)

    def show_at(self, pos: QPoint):
        """在指定位置显示弹窗，并自动调整不超出屏幕"""
        self.adjustSize()
        screen: QScreen = QApplication.primaryScreen()
        screen_rect = screen.availableGeometry()

        # 计算弹窗应显示的位置
        popup_rect = self.rect()
        x = pos.x()
        y = pos.y()

        # 防止超出右边界
        if x + popup_rect.width() > screen_rect.right():
            x = screen_rect.right() - popup_rect.width()
        # 防止超出下边界
        if y + popup_rect.height() > screen_rect.bottom():
            y = pos.y() - popup_rect.height()  # 尝试向上弹出

        self.move(x, y)
        self.show()
        self.setFocus()


# ==================== 【改造】上下文选择器（带标签卡片） ====================
class ContextSelector(QWidget):
    selectionChanged = pyqtSignal(set)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_keys = set()

        # 不再接收 context_items！
        self._refresh_context_items()  # 从注册表加载

        # ===== 构建 UI =====
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.dropdown_btn = TransparentToolButton(FluentIcon.ADD, self)
        self.dropdown_btn.setFixedSize(24, 24)
        self.dropdown_btn.clicked.connect(self._show_popup)

        self.tags_container = QWidget(self)
        self.tags_container.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Minimum)
        self.tags_layout = QVBoxLayout(self.tags_container)
        self.tags_layout.setContentsMargins(0, 0, 0, 0)
        self.tags_layout.setSpacing(4)

        main_layout.addWidget(self.dropdown_btn)
        main_layout.addWidget(self.tags_container)
        main_layout.addStretch(1)

        self._update_tags()

    @property
    def selected_keys(self):
        return self._selected_keys.copy()

    @property
    def context_items(self):
        return self._context_items

    def _refresh_context_items(self):
        """从全局注册表加载最新上下文项"""
        items = ContextRegistry.get_all_items()
        self._context_items = items
        self._item_map = {key: name for key, name, _ in items}

    def _on_popup_selection_changed(self, selected: set):
        self._selected_keys = selected
        self._update_tags()
        self.selectionChanged.emit(selected.copy())

    def _on_context_selection_changed(self, selected: set):
        # 注意：这个方法现在仅在 popup 打开后用户操作时被调用
        # 但我们依然通过 selectionChanged 信号统一处理，所以可以简化
        self._on_popup_selection_changed(selected)

    def _show_popup(self):
        # 每次点击都从注册表获取最新上下文，重建 popup
        self._refresh_context_items()

        # 销毁旧 popup（如有）
        if hasattr(self, 'popup') and self.popup:
            self.popup.close()
            self.popup.deleteLater()

        # 创建新 popup
        self.popup = ContextSelectorPopup(self._context_items, parent=self)
        self.popup.selectionChanged.connect(self._on_popup_selection_changed)
        self.popup.set_selection(self._selected_keys)

        # 显示
        btn_global_pos = self.dropdown_btn.mapToGlobal(QPoint(0, 0))
        popup_height = self.popup.sizeHint().height()
        popup_top_left = QPoint(btn_global_pos.x(), btn_global_pos.y() - popup_height)
        self.popup.show_at(popup_top_left)

    def _update_tags(self):
        # 清空现有标签
        while self.tags_layout.count():
            child = self.tags_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not self._selected_keys:
            self.tags_container.setVisible(False)
            return

        # 创建水平行容器
        current_row_layout = QHBoxLayout()
        current_row_layout.setContentsMargins(0, 0, 0, 0)
        current_row_layout.setSpacing(6)
        current_row_widget = QWidget()
        current_row_widget.setLayout(current_row_layout)

        max_row_width = 300
        row_width = 0

        for key in sorted(self._selected_keys):
            text = self._item_map.get(key, key)
            tag = TagWidget(key, text)
            tag.closed.connect(self._on_tag_closed)

            tag_width = tag.sizeHint().width()
            if row_width + tag_width > max_row_width and row_width > 0:
                self.tags_layout.addWidget(current_row_widget)
                current_row_layout = QHBoxLayout()
                current_row_layout.setContentsMargins(0, 0, 0, 0)
                current_row_layout.setSpacing(6)
                current_row_widget = QWidget()
                current_row_widget.setLayout(current_row_layout)
                row_width = 0

            current_row_layout.addWidget(tag)
            row_width += tag_width + 6

        if row_width > 0:
            self.tags_layout.addWidget(current_row_widget)

        self.tags_container.setVisible(True)
        self.tags_container.adjustSize()

    def _on_tag_closed(self, key: str):
        """点击标签关闭按钮时调用"""
        if key in self._selected_keys:
            self._selected_keys.discard(key)
            self._update_tags()
            self.selectionChanged.emit(self._selected_keys.copy())
            # 通知 popup 更新（虽然 popup 可能没打开，但状态要一致）
            self.popup.selected_keys = self._selected_keys.copy()
            self.popup._update_checkboxes_from_selection()