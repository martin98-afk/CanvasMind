# -*- coding: utf-8 -*-
import json
import traceback
from loguru import logger
from typing import Callable, Dict, Tuple, List, Any

from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QSize
from PyQt5.QtGui import QScreen, QMouseEvent
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QApplication, QWidget, QFrame, QSizePolicy
from qfluentwidgets import (
    FluentIcon, CheckBox, TransparentToolButton,
    CardWidget, CaptionLabel, BodyLabel
)

from app.utils.utils import serialize_for_json, get_icon


class ContextRegistry:
    # 注意：不再有 _instance，也不再是单例

    def __init__(self):
        # 每个实例都有独立的上下文和执行器字典
        self._contexts: Dict[str, Callable[[], Tuple[str, Any, Callable]]] = {}
        self._executors: Dict[str, Callable[[Any], None]] = {}

    def register(self, key: str, provider: Callable[[], Tuple[str, Any, Callable]], executor: Callable[[Any], None]):
        """
        注册一个上下文项
        :param key: 唯一标识，如 "@graph"
        :param provider: 无参函数，返回 (显示名称, 上下文数据, 双击回调函数)
        :param executor: 执行函数，接收上下文数据
        """
        self._contexts[key] = provider
        self._executors[key] = executor

    def get_executor(self, key: str) -> Callable[[Any], None]:
        return self._executors[key]

    def get_provider(self, key: str) -> Callable[[], Tuple[str, Any, Callable]]:
        return self._contexts[key]

    def unregister(self, key: str):
        self._contexts.pop(key, None)
        self._executors.pop(key, None)

    def get_all_items(self) -> List[Tuple[str, Callable[[], Tuple[str, Any, Callable]]]]:
        return [
            (key, provider)
            for key, provider in self._contexts.items()
        ]

    def clear(self):
        self._contexts.clear()
        self._executors.clear()


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
        self._context_cache: Dict[str, Tuple[str, str, Callable, bool]] = {}  # key -> (name, formatted_text, callback)

        self._refresh_context_items()

        # ===== UI =====
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.dropdown_btn = TransparentToolButton(get_icon("回形针"), self)
        self.dropdown_btn.setToolTip("添加上下文")
        self.dropdown_btn.setFixedSize(26, 26)
        self.dropdown_btn.clicked.connect(self._show_popup)

        self.refresh_btn = TransparentToolButton(get_icon("更新"), self)
        self.refresh_btn.setToolTip("刷新上下文")
        self.refresh_btn.setFixedSize(26, 26)
        self.refresh_btn.clicked.connect(self._update_tags)

        self.tags_container = QWidget(self)
        self.tags_container.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Minimum)
        self.tags_layout = QVBoxLayout(self.tags_container)
        self.tags_layout.setContentsMargins(0, 0, 0, 0)
        self.tags_layout.setSpacing(4)

        main_layout.addWidget(self.dropdown_btn)
        main_layout.addWidget(self.refresh_btn)
        main_layout.addWidget(self.tags_container, 1)

        self._update_tags()

    @property
    def selected_keys(self):
        return self._selected_keys.copy()

    @property
    def context(self):
        return self._context_cache

    def get_multimodal_context_items(self) -> List[Dict[str, Any]]:
        """
        返回可用于多模态大模型的上下文项列表。
        每项为 dict，可能包含 'text' 或 'image_url'
        """
        items = []
        for key in sorted(self._selected_keys):
            if key not in self._context_cache:
                continue
            name, context, _, is_image = self._context_cache[key]
            if is_image:
                # 多模态图片格式
                if "text" in context:
                    items.append({
                        "type": "text",
                        "text": f"# {name}信息:\n{context['text']}"
                    })
                items.append({
                    "type": "image_url",
                    "image_url": {"url": context["url"]}  # {"url": "data:image/..."}
                })
            else:
                # 文本
                items.append({
                    "type": "text",
                    "text": f"# {name}信息:\n{context}"
                })
        return items

    def get_text_context(self):
        context = ("===== 画布上下文信息开始 =====\n\n" +
                   "\n".join([context[1] for context in self._context_cache.values() if not context[3]]) +
                   "\n===== 上下文信息结束 =====\n\n") if self._context_cache else ""
        return context

    def get_context_by_key(self, key: str) -> str:
        """获取格式化后的上下文文本"""
        return self._context_cache.get(key, ("", "", lambda: None))[1]

    def get_callback_params_by_key(self, key: str) -> Callable:
        """获取回调函数（可直接调用）"""
        return self._context_cache.get(key, ("", "", lambda: None))[2]

    def _refresh_context_items(self):
        if hasattr(self.parent.homepage, 'context_register'):
            self._context_items = self.parent.homepage.context_register.get_all_items()
        else:
            self._context_items = []

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
        self._context_cache.clear()
        for context_key, context_func in self._context_items:
            if context_key in self._selected_keys:
                try:
                    name, context_data, callback_params = context_func()
                except Exception as e:
                    logger.error(traceback.format_exc())
                    name, context_data, callback_params = "错误", f"[加载失败: {e}]", None

                # ✅ 关键：保留原始数据结构，不做强制字符串化
                # 判断是否是图片 dict
                is_image = (
                        isinstance(context_data, dict) and
                        "url" in context_data and
                        isinstance(context_data["url"], str) and
                        context_data["url"].startswith("data:image/")
                )

                if not is_image:
                    # 普通文本：转为字符串
                    if isinstance(context_data, (dict, list, tuple, set)):
                        context_str = serialize_for_json(context_data)
                    else:
                        context_str = str(context_data)
                    context_data = f"# {name}信息:\n{context_str}\n\n"

                self._context_cache[context_key] = (name, context_data, callback_params, is_image)

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
            tag.doubleClicked.connect(lambda k=key, t=tag: self._on_tag_double_clicked(k, t))

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

    def _on_tag_double_clicked(self, key: str, tag: TagWidget):
        """双击标签时，直接调用其回调函数"""
        callback = self.parent.homepage.context_register.get_executor(key)
        params = self.get_callback_params_by_key(key)
        if callable(callback):
            try:
                callback(params, tag)
            except Exception as e:
                print(f"[ContextSelector] 双击回调出错: {e}")