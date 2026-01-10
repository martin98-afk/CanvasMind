# -*- coding: utf-8 -*-

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QApplication
)
from qfluentwidgets import (
    SearchLineEdit, PushButton, SmoothScrollArea, CheckBox,
    SimpleCardWidget, CaptionLabel, FlowLayout, TransparentToolButton,
    FluentIcon, setFont
)
from qfluentwidgets.components.widgets.card_widget import CardSeparator

try:
    from pypinyin import lazy_pinyin
except ImportError:
    def lazy_pinyin(s):
        return [s]


class CategoryFilterDialog(QWidget):
    categories_changed = pyqtSignal(set)

    def __init__(self, categories, parent=None, selected_categories=None, direction="auto", max_visible=8):
        super().__init__(parent)
        # 窗口标志
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # ---------------------------------------------------------
        # 1. 核心尺寸定义
        # ---------------------------------------------------------
        self.WIN_WIDTH = 450  # 整体宽度固定
        self.ITEM_WIDTH = 165  # 每个 CheckBox 宽度 (3个正好)
        self.MAX_CONTENT_H = 400  # 列表最大高度，超过则滚动
        self.FIXED_EXTRA_H = 185  # 除去列表外，搜素框+按钮+底部的固定高度总和

        self.setFixedWidth(self.WIN_WIDTH)

        self.all_categories = categories
        self.selected_categories = set(selected_categories) if selected_categories else set()
        self.checkbox_map = {}
        self.category_search_map = {}
        self._show_selected_only = False

        self._precompute_pinyin()
        self._init_ui()
        self._apply_style()

    def _precompute_pinyin(self):
        for cat in self.all_categories:
            full = "".join(lazy_pinyin(cat)).lower()
            init = "".join([i[0] for i in lazy_pinyin(cat) if i]).lower()
            self.category_search_map[cat] = {"p": full, "i": init}

    def _init_ui(self):
        # 2. 主容器
        self.card = SimpleCardWidget(self)
        self.card.setFixedWidth(self.WIN_WIDTH)

        # 使用普通的 QVBoxLayout，不要设置 SetFixedSize，由我们手动控高
        self.main_layout = QVBoxLayout(self.card)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(10)

        # 3. 搜索栏
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

        # 4. 工具按钮
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

        # 5. 滚动区域
        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")

        self.content_widget = QWidget()
        self.flow_layout = FlowLayout(self.content_widget, needAni=True)
        self.flow_layout.setContentsMargins(0, 5, 0, 5)
        self.flow_layout.setSpacing(10)

        for cat in self.all_categories:
            cb = CheckBox(cat, self.content_widget)
            cb.setFixedWidth(self.ITEM_WIDTH)  # 强制 3 列的核心
            cb.setChecked(cat in self.selected_categories)
            cb.stateChanged.connect(lambda state, c=cat: self._on_toggled(c, state))
            self.checkbox_map[cat] = cb
            self.flow_layout.addWidget(cb)

        self.scroll_area.setWidget(self.content_widget)
        self.main_layout.addWidget(self.scroll_area)

        # 6. 底部
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

        # 顶层布局
        l = QVBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(self.card)

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

    def _on_search_or_filter_changed(self):
        txt = self.search_input.text().lower().strip()
        visible_count = 0
        for name, cb in self.checkbox_map.items():
            py = self.category_search_map.get(name, {})
            m = (txt in name.lower() or txt in py['p'] or txt in py['i'])
            f = not self._show_selected_only or (name in self.selected_categories)
            cb.setVisible(m and f)
            if m and f: visible_count += 1

        self.flow_layout.layout()
        self._update_dynamic_size()

    def _update_dynamic_size(self):
        """精准控制：宽度锁死，高度动态"""
        # 1. 计算内容在当前宽度下需要的高度
        # 这里的宽 = 总宽(550) - 边距(15*2) = 520
        content_h = self.flow_layout.heightForWidth(520)

        # 2. 设置滚动区域高度
        scroll_h = max(40, min(content_h + 10, self.MAX_CONTENT_H))
        self.scroll_area.setFixedHeight(scroll_h)

        # 3. 计算并设置【窗口整体】的高度
        # 总高度 = 固定头部底部高度 + 滚动区高度
        total_h = self.FIXED_EXTRA_H + scroll_h
        self.setFixedHeight(total_h)
        self.card.setFixedHeight(total_h)  # 确保卡片也跟着变

    def _on_toggled(self, category, state):
        if state == Qt.Checked:
            self.selected_categories.add(category)
        else:
            self.selected_categories.discard(category)
        self._update_stat_text()
        self.categories_changed.emit(self.selected_categories)

    def _update_stat_text(self):
        self.stat_label.setText(f"已选: {len(self.selected_categories)} / {len(self.all_categories)}")

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
        # 初始化尺寸
        self._on_search_or_filter_changed()
        self.show()

        # 修正位置逻辑
        screen = QApplication.primaryScreen().availableGeometry()
        x = max(screen.left(), min(pos.x(), screen.right() - self.WIN_WIDTH))
        y = pos.y()
        if y + self.height() > screen.bottom():
            y = pos.y() - self.height()

        self.move(x, y)
        self.search_input.setFocus()