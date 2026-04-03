# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QApplication,
    QPlainTextEdit,
    QLabel,
)
from qfluentwidgets import (
    CaptionLabel,
    SearchLineEdit,
    InfoBar,
    TransparentToolButton,
    FluentIcon,
    SingleDirectionScrollArea,
    CardWidget,
    SubtitleLabel,
    setFont,
    isDarkTheme,
    InfoBarPosition,
    SegmentedWidget,
    StrongBodyLabel,
)

from app.plugins.constants import PluginType
from app.plugins.plugin_manager import UnifiedPluginManager
from app.utils.utils import get_icon
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


NODE_CATEGORIES = ["全部", "内置", "display", "interactive", "operate"]


class PluginCard(CardWidget):
    ARROW_ICONS = {"collapsed": get_icon("折叠"), "expanded": get_icon("展开")}

    def __init__(self, name, desc, template, plugin_type, parent_window, parent=None):
        super().__init__(parent)
        self.parent_window = parent_window
        self.template_code = template.strip()
        self.plugin_type = plugin_type
        self.is_expanded = False

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 12, 12, 12)
        self.layout.setSpacing(8)

        dark = isDarkTheme()

        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.toggle_button = TransparentToolButton(self.ARROW_ICONS["collapsed"], self)
        self.toggle_button.setFixedSize(24, 24)
        self.toggle_button.clicked.connect(self._on_toggle)

        type_badge = QLabel(plugin_type)
        type_badge.setObjectName("typeBadge")
        badge_color = "#4FC1FF" if dark else "#0066CC"
        badge_bg = "rgba(79, 193, 255, 0.15)" if dark else "rgba(0, 102, 204, 0.1)"
        type_badge.setStyleSheet(f"""
            QLabel#typeBadge {{
                background-color: {badge_bg};
                color: {badge_color};
                padding: 2px 8px;
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
            }}
        """)

        self.title_label = StrongBodyLabel(name)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        self.copy_btn = TransparentToolButton(FluentIcon.COPY, self)
        self.copy_btn.setFixedSize(28, 28)
        self.copy_btn.setToolTip("复制代码")
        self.copy_btn.clicked.connect(self._on_copy)

        self.insert_btn = TransparentToolButton(get_icon("插入"), self)
        self.insert_btn.setFixedSize(28, 28)
        self.insert_btn.setToolTip("插入编辑器")
        self.insert_btn.clicked.connect(self._on_insert)

        btn_layout.addWidget(self.insert_btn)
        btn_layout.addWidget(self.copy_btn)

        header_layout.addWidget(self.toggle_button)
        header_layout.addWidget(type_badge)
        header_layout.addWidget(self.title_label, 1)
        header_layout.addLayout(btn_layout)
        self.layout.addLayout(header_layout)

        if desc:
            self.desc_label = CaptionLabel(desc)
            self.desc_label.setWordWrap(True)
            self.desc_label.setStyleSheet(
                "color: rgba(255,255,255,0.5);" if dark else "color: rgba(0,0,0,0.5);"
            )
            self.layout.addWidget(self.desc_label)

        self.setup_code_block()
        self.layout.addWidget(self.code_edit)
        self.code_edit.setVisible(False)

    def setup_code_block(self):
        dark = isDarkTheme()
        bg_color = "rgba(255, 255, 255, 0.05)" if dark else "rgba(0, 0, 0, 0.04)"
        border_color = "rgba(255, 255, 255, 0.1)" if dark else "rgba(0, 0, 0, 0.08)"
        text_color = "#4FC1FF" if dark else "#0066CC"

        self.code_edit = QPlainTextEdit()
        self.code_edit.setPlainText(self.template_code)
        self.code_edit.setReadOnly(True)
        self.code_edit.setMaximumHeight(120)
        self.code_edit.setMinimumHeight(60)

        font_family = (
            "Consolas" if QApplication.style().objectName() != "fusion" else "Monospace"
        )
        self.code_edit.setFont(QFont(font_family, 10))

        self.code_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 6px;
                padding: 6px;
                color: {text_color};
            }}
            QScrollBar:vertical {{
                width: 6px;
                background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: {border_color};
                border-radius: 3px;
            }}
        """)

        self.code_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def _on_toggle(self):
        if self.is_expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self):
        self.is_expanded = True
        self.code_edit.setVisible(True)
        self.toggle_button.setIcon(self.ARROW_ICONS["expanded"])

    def collapse(self):
        self.is_expanded = False
        self.code_edit.setVisible(False)
        self.toggle_button.setIcon(self.ARROW_ICONS["collapsed"])

    def _on_copy(self):
        QApplication.clipboard().setText(self.template_code)
        InfoBar.success(
            "已复制",
            "代码已存入剪贴板",
            duration=1500,
            position=InfoBarPosition.TOP,
            parent=self.parent_window.window(),
        )

    def _on_insert(self):
        self.parent_window.insert_to_editor(self.template_code)


class PluginTemplateToolWindow(ToolWindow):
    name = "插件模板库"
    icon = ":/icons/组件.png"
    default_position = DockPosition.TOP
    CATEGORIES = ["运行画布", "组件开发"]
    display_order = 50

    def setup_ui(self):
        self.plugin_manager = UnifiedPluginManager.get_instance()
        self.all_data = []
        self.current_type = "全部"
        self.cards = []

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.setup_navigation()
        self.setup_content()

        self.refresh_list()

    def _setup_title_bar(self):
        title_bar = self.get_title_bar()
        title_bar.set_title("插件模板库")

        self.search_edit = SearchLineEdit(self)
        self.search_edit.setPlaceholderText("搜索...")
        self.search_edit.setFixedWidth(240)
        self.search_edit.textChanged.connect(self.filter_plugins)
        title_bar.insert_button(1, self.search_edit, 1)

    def setup_navigation(self):
        nav_widget = QWidget()
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(16, 0, 16, 8)
        nav_layout.setSpacing(8)

        nav_top_row = QHBoxLayout()
        nav_top_row.setSpacing(8)

        self.type_nav = SegmentedWidget(self)

        for name in NODE_CATEGORIES:
            self.type_nav.addItem(name, name)
        self.type_nav.setCurrentItem("全部")
        self.type_nav.currentItemChanged.connect(self.on_type_changed)

        batch_layout = QHBoxLayout()
        batch_layout.setSpacing(4)

        self.expand_all_btn = TransparentToolButton(get_icon("展开"), self)
        self.expand_all_btn.setFixedSize(28, 28)
        self.expand_all_btn.setToolTip("全部展开")
        self.expand_all_btn.clicked.connect(self._on_expand_all)

        self.collapse_all_btn = TransparentToolButton(get_icon("折叠"), self)
        self.collapse_all_btn.setFixedSize(28, 28)
        self.collapse_all_btn.setToolTip("全部折叠")
        self.collapse_all_btn.clicked.connect(self._on_collapse_all)

        batch_layout.addWidget(self.expand_all_btn)
        batch_layout.addWidget(self.collapse_all_btn)

        nav_top_row.addWidget(self.type_nav, 1)
        nav_top_row.addLayout(batch_layout)
        nav_layout.addLayout(nav_top_row)
        self.main_layout.addWidget(nav_widget)

    def setup_navigation(self):
        nav_widget = QWidget()
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(16, 0, 16, 8)
        nav_layout.setSpacing(8)

        nav_top_row = QHBoxLayout()
        nav_top_row.setSpacing(8)

        self.type_nav = SegmentedWidget(self)

        for name in NODE_CATEGORIES:
            self.type_nav.addItem(name, name)
        self.type_nav.setCurrentItem("全部")
        self.type_nav.currentItemChanged.connect(self.on_type_changed)

        batch_layout = QHBoxLayout()
        batch_layout.setSpacing(4)

        self.expand_all_btn = TransparentToolButton(get_icon("展开"), self)
        self.expand_all_btn.setFixedSize(28, 28)
        self.expand_all_btn.setToolTip("全部展开")
        self.expand_all_btn.clicked.connect(self._on_expand_all)

        self.collapse_all_btn = TransparentToolButton(get_icon("折叠"), self)
        self.collapse_all_btn.setFixedSize(28, 28)
        self.collapse_all_btn.setToolTip("全部折叠")
        self.collapse_all_btn.clicked.connect(self._on_collapse_all)

        batch_layout.addWidget(self.expand_all_btn)
        batch_layout.addWidget(self.collapse_all_btn)

        nav_top_row.addWidget(self.type_nav, 1)
        nav_top_row.addLayout(batch_layout)
        nav_layout.addLayout(nav_top_row)
        self.main_layout.addWidget(nav_widget)

    def setup_content(self):
        self.scroll_area = SingleDirectionScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMinimumWidth(380)
        self.scroll_area.setStyleSheet("border: none; background: transparent;")

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(16, 8, 16, 20)
        self.container_layout.setSpacing(8)
        self.container_layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.container)
        self.main_layout.addWidget(self.scroll_area)

    def on_type_changed(self, type_name):
        self.current_type = type_name
        self.filter_plugins(self.search_edit.text())

    def get_built_in_templates(self):
        return [
            {
                "name": "流式输出 (节点展示)",
                "desc": "流式输出结果并展示在节点上，当params的key与端口名一致时会将流式结果同步到对应端口中。",
                "template": """
        self.emit_message(
            method="stream_output",
            params={
                "output1": {"data": "test", "data_type": "str", "plugin": "display_str"}, 
                "output2": {"data": 1, "data_type": "list", "plugin": "display_list"},
                "output3": {"data": "hidden", "data_type": "str"} # 不带 plugin 参数则不实时展示
            }
        )""",
                "type": "内置",
            },
            {
                "name": "流式输出 (静默更新)",
                "desc": "流式输出结果并同步到端口和变量，但不会触发节点 UI 的实时内容展示，适用于后台静默数据同步。",
                "template": """
        self.emit_message(
            method="stream_output",
            params={
                "output1": {"data": "test", "data_type": "str"}, 
                "output2": {"data": 1, "data_type": "list"}
            }
        )""",
                "type": "内置",
            },
        ]

    def refresh_list(self):
        self.all_data = []
        self.all_data.extend(self.get_built_in_templates())

        for p in self.plugin_manager.list_plugins(PluginType.NODE).values():
            if hasattr(p, "plugin_template") and p.plugin_template:
                category = getattr(p, "plugin_category", "default")
                self.all_data.append(
                    {
                        "name": getattr(p, "plugin_name", p.plugin_id),
                        "desc": getattr(p, "plugin_desc", "节点插件模板"),
                        "template": p.plugin_template,
                        "type": category,
                    }
                )

        self.filter_plugins(self.search_edit.text())

    def display_cards(self, data_list):
        self.cards = []

        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        dark = isDarkTheme()
        stats_label = CaptionLabel(f"共 {len(data_list)} 个片段")
        stats_label.setStyleSheet(f"""
            color: {"rgba(255,255,255,0.5)" if dark else "rgba(0,0,0,0.5)"};
            padding: 4px 0;
        """)
        self.container_layout.addWidget(stats_label)

        if not data_list:
            empty_label = CaptionLabel("当前分类下暂无插件片段")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet(f"""
                padding: 40px;
                color: {"rgba(255,255,255,0.3)" if dark else "rgba(0,0,0,0.3)"};
            """)
            self.container_layout.addWidget(empty_label)
        else:
            for item in data_list:
                card = PluginCard(
                    item["name"],
                    item.get("desc", ""),
                    item["template"],
                    item.get("type", "未知"),
                    self,
                )
                self.cards.append(card)
                self.container_layout.addWidget(card)

        self.container_layout.addStretch(1)

    def filter_plugins(self, text):
        kw = text.lower()
        filtered = [
            i
            for i in self.all_data
            if (self.current_type == "全部" or i.get("type") == self.current_type)
            and (
                not kw
                or kw in i["name"].lower()
                or kw in i.get("desc", "").lower()
                or kw in i["template"].lower()
            )
        ]
        self.display_cards(filtered)

    def _on_expand_all(self):
        for card in self.cards:
            card.expand()

    def _on_collapse_all(self):
        for card in self.cards:
            card.collapse()

    def insert_to_editor(self, text):
        if hasattr(self.homepage, "_handle_insert_code_from_llm"):
            self.homepage._handle_insert_code_from_llm(text)
            InfoBar.success(
                "已插入",
                "模板代码已添加到编辑器",
                duration=1000,
                position=InfoBarPosition.TOP,
                parent=self.window(),
            )
        else:
            QApplication.clipboard().setText(text)
            InfoBar.warning(
                "插入失败",
                "未找到编辑器接口，代码已复制到剪贴板",
                duration=2000,
                parent=self.window(),
            )
