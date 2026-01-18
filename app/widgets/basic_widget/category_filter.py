# -*- coding: utf-8 -*-

import sys
import threading

from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QApplication
)
from qfluentwidgets import (
    SearchLineEdit, PushButton, SmoothScrollArea, CheckBox,
    SimpleCardWidget, CaptionLabel, FlowLayout, TransparentToolButton,
    FluentIcon, setFont
)
from qfluentwidgets.components.widgets.card_widget import CardSeparator

from app.scan_components import ComponentScanner

try:
    from pypinyin import lazy_pinyin
except ImportError:
    def lazy_pinyin(s):
        return [s]


class CategoryFilterDialog(QWidget):
    categories_changed = pyqtSignal(set)
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            # 只有第一次实例化时才真正创建对象
            cls._instance = super(CategoryFilterDialog, cls).__new__(cls)
        return cls._instance

    def __init__(self, parent=None, selected_categories=None):
        # 【核心修复】使用 __dict__ 检查，避免触发 PyQt 的 "super-class __init__ not called" 错误
        if "_initialized" in self.__dict__:
            # 如果已经初始化过，仅更新选中的状态，不再执行初始化 UI 的逻辑
            if selected_categories is not None:
                self.selected_categories = set(selected_categories)
                self._sync_checkbox_states()
            # 如果传入了新的 parent，可以选择更新 parent
            if parent and parent != self.parent():
                self.setParent(parent)
                self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
            return

        # --- 第一次初始化才会执行以下代码 ---
        super().__init__(parent)
        self._initialized = True

        # 窗口标志
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 核心尺寸定义
        self.WIN_WIDTH = 450
        self.ITEM_WIDTH = 165
        self.MAX_CONTENT_H = 400
        self.FIXED_EXTRA_H = 185
        self.setFixedWidth(self.WIN_WIDTH)

        self.scanner = ComponentScanner()
        self.all_categories = set()
        self.selected_categories = set(selected_categories) if selected_categories else set()
        self.checkbox_map = {}
        self.category_search_map = {}
        self._show_selected_only = False

        # 注册扫描器回调
        self.scanner.register_on_change(self.refresh_categories)

        # 初始化 UI
        self._init_ui_framework()
        self._apply_style()

        # 填充数据
        self.refresh_categories()

    def _init_ui_framework(self):
        """初始化静态 UI 结构"""
        self.card = SimpleCardWidget(self)
        self.card.setFixedWidth(self.WIN_WIDTH)

        self.main_layout = QVBoxLayout(self.card)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(10)

        # 搜索栏
        self.search_input = SearchLineEdit(self)
        self.search_input.setPlaceholderText("拼音/首字母搜索...")
        self.search_input.textChanged.connect(self._on_search_or_filter_changed)

        self.filter_btn = TransparentToolButton(FluentIcon.FILTER, self)
        self.filter_btn.setCheckable(True)
        self.filter_btn.clicked.connect(self._toggle_filter_selected)

        h = QHBoxLayout()
        h.addWidget(self.search_input)
        h.addWidget(self.filter_btn)
        self.main_layout.addLayout(h)

        # 工具按钮
        t = QHBoxLayout()
        for txt, ico, sl in [("全选", FluentIcon.ACCEPT, self._select_all_visible),
                             ("反选", FluentIcon.SYNC, self._invert_selection),
                             ("清空", FluentIcon.DELETE, self._select_none)]:
            btn = PushButton(txt, self, ico)
            btn.setFixedHeight(30)
            setFont(btn, 11)
            btn.clicked.connect(sl)
            t.addWidget(btn)
        self.main_layout.addLayout(t)
        self.main_layout.addWidget(CardSeparator())

        # 滚动区域
        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")

        self.content_widget = QWidget()
        self.flow_layout = FlowLayout(self.content_widget, needAni=True)
        self.flow_layout.setContentsMargins(0, 5, 0, 5)
        self.flow_layout.setSpacing(10)

        self.scroll_area.setWidget(self.content_widget)
        self.main_layout.addWidget(self.scroll_area)

        # 底部
        self.main_layout.addWidget(CardSeparator())
        f = QHBoxLayout()
        self.stat_label = CaptionLabel(self)
        done_btn = PushButton("完成", self)
        done_btn.setFixedWidth(100)
        done_btn.clicked.connect(self.close)
        f.addWidget(self.stat_label)
        f.addStretch(1)
        f.addWidget(done_btn)
        self.main_layout.addLayout(f)

        l = QVBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(self.card)

    def refresh_categories(self):
        """重新获取分类并刷新界面"""
        # 确保在主线程执行 UI 更新 (Scanner 可能在后台线程触发)
        if threading.current_thread() != threading.main_thread():
            QTimer.singleShot(0, self.refresh_categories)
            return

        comp_map, _ = self.scanner.get_components()
        # 获取最新的全部分类并排序
        new_all_categories = sorted({path.split("/")[0] for path in comp_map.keys()})

        self.all_categories = set(new_all_categories)
        # 剔除已不存在的分类
        self.selected_categories &= self.all_categories

        self._precompute_pinyin()

        # 清理旧组件
        self.checkbox_map.clear()
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            item.deleteLater()

        # 重新生成 CheckBox
        for cat in new_all_categories:
            cb = CheckBox(cat, self.content_widget)
            cb.setFixedWidth(self.ITEM_WIDTH)
            cb.setChecked(cat in self.selected_categories)
            # 使用默认参数保存当前循环的 cat，避免闭包陷阱
            cb.stateChanged.connect(lambda state, c=cat: self._on_toggled(c, state))
            self.checkbox_map[cat] = cb
            self.flow_layout.addWidget(cb)

        self._update_stat_text()
        self._on_search_or_filter_changed()

    def _precompute_pinyin(self):
        self.category_search_map.clear()
        for cat in self.all_categories:
            full = "".join(lazy_pinyin(cat)).lower()
            init = "".join([i[0] for i in lazy_pinyin(cat) if i]).lower()
            self.category_search_map[cat] = {"p": full, "i": init}

    def _sync_checkbox_states(self):
        """同步选中的状态到 UI"""
        for cat, cb in self.checkbox_map.items():
            cb.blockSignals(True)
            cb.setChecked(cat in self.selected_categories)
            cb.blockSignals(False)
        self._update_stat_text()

    def _on_search_or_filter_changed(self):
        txt = self.search_input.text().lower().strip()
        visible_count = 0
        for name, cb in self.checkbox_map.items():
            py = self.category_search_map.get(name, {})
            m = (txt in name.lower() or txt in py.get('p', '') or txt in py.get('i', ''))
            f = not self._show_selected_only or (name in self.selected_categories)
            cb.setVisible(m and f)
            if m and f: visible_count += 1

        self._update_dynamic_size()

    def _update_dynamic_size(self):
        # 这里的 520 是内容区的参考宽度（WIN_WIDTH - margins）
        content_h = self.flow_layout.heightForWidth(self.WIN_WIDTH - 30)
        scroll_h = max(40, min(content_h + 10, self.MAX_CONTENT_H))
        self.scroll_area.setFixedHeight(scroll_h)
        total_h = self.FIXED_EXTRA_H + scroll_h
        self.setFixedHeight(total_h)
        self.card.setFixedHeight(total_h)

    def _on_toggled(self, category, state):
        if state == Qt.Checked:
            self.selected_categories.add(category)
        else:
            self.selected_categories.discard(category)
        self._update_stat_text()
        self.categories_changed.emit(self.selected_categories)

    def _update_stat_text(self):
        self.stat_label.setText(f"已选: {len(self.selected_categories)} / {len(self.all_categories)}")

    def _apply_style(self):
        self.setStyleSheet("""
            SimpleCardWidget {
                background-color: #2D2D2D;
                border: 1px solid #454545;
                border-radius: 12px;
            }
            CheckBox {
                color: #D0D0D0;
                padding: 7px 5px;
                background: rgba(255, 255, 255, 0.05);
                border-radius: 5px;
            }
            CheckBox:checked {
                color: white;
                background: rgba(0, 150, 255, 0.3);
            }
        """)

    def _toggle_filter_selected(self):
        self._show_selected_only = self.filter_btn.isChecked()
        self._on_search_or_filter_changed()

    def _select_all_visible(self):
        for cb in self.checkbox_map.values():
            if not cb.isHidden(): cb.setChecked(True)

    def _invert_selection(self):
        for cb in self.checkbox_map.values():
            if not cb.isHidden(): cb.setChecked(not cb.isChecked())

    def _select_none(self):
        for cb in self.checkbox_map.values():
            if not cb.isHidden(): cb.setChecked(False)

    def show_at(self, pos):
        # 每次显示前重新排版
        self._on_search_or_filter_changed()
        self.show()

        screen = QApplication.primaryScreen().availableGeometry()
        x = max(screen.left(), min(pos.x(), screen.right() - self.WIN_WIDTH))
        y = pos.y()
        if y + self.height() > screen.bottom():
            y = pos.y() - self.height()

        self.move(x, y)
        self.search_input.setFocus()