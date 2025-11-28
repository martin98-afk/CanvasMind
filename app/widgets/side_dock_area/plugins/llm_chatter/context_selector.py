# -*- coding: utf-8 -*-
import json
import traceback
from typing import Callable, Dict, Tuple, List, Any

from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QSize
from PyQt5.QtGui import QScreen, QMouseEvent
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QApplication, QWidget, QFrame, QSizePolicy
from qfluentwidgets import (
    FluentIcon, CheckBox, TransparentToolButton,
    CardWidget, CaptionLabel, BodyLabel
)


class ContextRegistry:
    _instance = None
    _contexts: Dict[str, Callable[[], Tuple[str, Any, Callable]]] = {}
    _executors: Dict[str, Callable[[Any], None]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, key: str, provider: Callable[[], Tuple[str, Any, Callable], ], excutor: Callable[[Any], None]):
        """
        注册一个上下文项
        :param key: 唯一标识，如 "@graph"
        :param provider: 无参函数，返回 (显示名称, 上下文数据, 双击回调函数)
        """
        cls._contexts[key] = provider
        cls._executors[key] = excutor

    @classmethod
    def get_executor(cls, key: str) -> Callable[[Any], None]:
        return cls._executors[key]

    @classmethod
    def get_provider(cls, key: str) -> Callable[[], Tuple[str, Any, Callable]]:
        return cls._contexts[key]

    @classmethod
    def unregister(cls, key: str):
        cls._contexts.pop(key, None)

    @classmethod
    def get_all_items(cls) -> List[Tuple[str, Callable[[], Tuple[str, Any, Callable]]]]:
        return [
            (key, provider)
            for key, provider in cls._contexts.items()
        ]

    @classmethod
    def clear(cls):
        cls._contexts.clear()


# ==================== 【改进】单个上下文标签卡片 ====================
class TagWidget(CardWidget):
    closed = pyqtSignal(str)      # 发出 key
    doubleClicked = pyqtSignal(str)  # 新增：双击信号

    def __init__(self, key: str, text: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)  # 提示可交互

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(6)

        self.label = CaptionLabel(text, self)
        self.close_btn = TransparentToolButton(FluentIcon.CLOSE, self)
        self.close_btn.setFixedSize(16, 16)
        self.close_btn.setIconSize(QSize(12, 12))
        self.close_btn.clicked.connect(lambda: self.closed.emit(self.key))

        layout.addWidget(self.label)
        layout.addWidget(self.close_btn)
        layout.addStretch()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit(self.key)
        super().mouseDoubleClickEvent(event)


# ==================== 【Popup 保持不变，仅微调类型注解】 ====================
class ContextSelectorPopup(QWidget):
    selectionChanged = pyqtSignal(set)

    def __init__(self, context_items: List[Tuple[str, Callable]], parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.context_items = context_items
        self.selected_keys = set()
        self.checkboxes = []
        self.parent_widget = parent

        self._setup_ui()

    def set_selection(self, selected_keys: set):
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

        title_label = BodyLabel("选择上下文信息：", self)
        layout.addWidget(title_label)

        for key, _ in self.context_items:
            cb = CheckBox(key, self)
            cb.stateChanged.connect(lambda state, k=key: self._on_item_toggled(k, state))
            self.checkboxes.append(cb)
            layout.addWidget(cb)

        main_frame.setMinimumWidth(180)
        main_frame.adjustSize()

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
        if self.parent_widget:
            self.parent_widget._on_context_selection_changed(self.selected_keys.copy())

    def _select_none(self):
        self.selected_keys.clear()
        self._update_checkboxes_from_selection()
        self.selectionChanged.emit(self.selected_keys.copy())
        if self.parent_widget:
            self.parent_widget._on_context_selection_changed(self.selected_keys.copy())

    def _update_checkboxes_from_selection(self):
        for cb, (key, _) in zip(self.checkboxes, self.context_items):
            cb.setChecked(key in self.selected_keys)

    def show_at(self, pos: QPoint):
        self.adjustSize()
        screen: QScreen = QApplication.primaryScreen()
        screen_rect = screen.availableGeometry()

        popup_rect = self.rect()
        x = pos.x()
        y = pos.y()

        if x + popup_rect.width() > screen_rect.right():
            x = screen_rect.right() - popup_rect.width()
        if y + popup_rect.height() > screen_rect.bottom():
            y = pos.y() - popup_rect.height()

        self.move(x, y)
        self.show()
        self.setFocus()


# ==================== 【核心改造】ContextSelector ====================
class ContextSelector(QWidget):
    selectionChanged = pyqtSignal(set)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self._selected_keys = set()
        self._context_items: List[Tuple[str, Callable]] = []
        self._context_cache: Dict[str, Tuple[str, str, Callable]] = {}  # key -> (name, formatted_text, callback)

        self._refresh_context_items()

        # ===== UI =====
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
    def context(self):
        return self._context_cache

    def get_all_context(self):
        return "===== 上下文信息开始 =====" + "\n".join([context[1] for context in self._context_cache.values()]) + "\n" + "===== 上下文信息结束 =====\n\n"

    def get_context_by_key(self, key: str) -> str:
        """获取格式化后的上下文文本"""
        return self._context_cache.get(key, ("", "", lambda: None))[1]

    def get_callback_params_by_key(self, key: str) -> Callable:
        """获取回调函数（可直接调用）"""
        return self._context_cache.get(key, ("", "", lambda: None))[2]

    def _refresh_context_items(self):
        self._context_items = ContextRegistry.get_all_items()

    def _on_popup_selection_changed(self, selected: set):
        self._selected_keys = selected
        self._update_tags()
        self.selectionChanged.emit(selected.copy())

    def _show_popup(self):
        self._refresh_context_items()
        if hasattr(self, 'popup') and self.popup:
            self.popup.close()
            self.popup.deleteLater()

        self.popup = ContextSelectorPopup(self._context_items, parent=self)
        self.popup.selectionChanged.connect(self._on_popup_selection_changed)
        self.popup.set_selection(self._selected_keys)

        btn_global_pos = self.dropdown_btn.mapToGlobal(QPoint(0, 0))
        popup_height = self.popup.sizeHint().height()
        popup_top_left = QPoint(btn_global_pos.x(), btn_global_pos.y() - popup_height)
        self.popup.show_at(popup_top_left)

    def _refresh_context_cache(self):
        """预加载所有选中项的 (name, text, callback) 到缓存"""
        self._context_cache.clear()
        for context_key, context_func in self._context_items:
            if context_key in self._selected_keys:
                try:
                    name, context_data, callback_params = context_func()
                except Exception as e:
                    logger.error(traceback.format_exc())
                    name, context_data, callback_params = "错误", f"[加载失败: {e}]", None

                if isinstance(context_data, (dict, list, tuple, set)):
                    context_str = json.dumps(context_data, indent=2, ensure_ascii=False)
                else:
                    context_str = str(context_data)

                formatted_text = f"# {name}信息:\n{context_str}\n\n"
                self._context_cache[context_key] = (name, formatted_text, callback_params)

    def _update_tags(self):
        self._refresh_context_cache()

        while self.tags_layout.count():
            child = self.tags_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not self._selected_keys:
            self.tags_container.setVisible(False)
            return

        current_row_layout = QHBoxLayout()
        current_row_layout.setContentsMargins(0, 0, 0, 0)
        current_row_layout.setSpacing(6)
        current_row_widget = QWidget()
        current_row_widget.setLayout(current_row_layout)

        max_row_width = self.parent.width() - 100
        row_width = 0

        for key in sorted(self._selected_keys):
            name = self._context_cache.get(key, ("未知", "", lambda: None))[0]
            tag = TagWidget(key, name)
            tag.closed.connect(self._on_tag_closed)
            tag.doubleClicked.connect(self._on_tag_double_clicked)  # 👈 新增连接

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
        if key in self._selected_keys:
            self._selected_keys.discard(key)
            self._update_tags()
            self.selectionChanged.emit(self._selected_keys.copy())
            if hasattr(self, 'popup') and self.popup:
                self.popup.selected_keys = self._selected_keys.copy()
                self.popup._update_checkboxes_from_selection()

    def _on_tag_double_clicked(self, key: str):
        """双击标签时，直接调用其回调函数"""
        callback = ContextRegistry.get_executor(key)
        params = self.get_callback_params_by_key(key)
        if callable(callback):
            try:
                callback(params)
            except Exception as e:
                print(f"[ContextSelector] 双击回调出错: {e}")