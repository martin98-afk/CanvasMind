# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QWidget, QApplication,
    QPlainTextEdit
)
from qfluentwidgets import (
    StrongBodyLabel, CaptionLabel, SearchLineEdit,
    InfoBar, TransparentToolButton,
    FluentIcon, SingleDirectionScrollArea, CardWidget,
    SubtitleLabel, setFont
)

from app.plugins.plugin_manager import NodePluginManager
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class PluginCard(CardWidget):
    """插件代码模板卡片组件"""

    def __init__(self, name, desc, template, parent_window, parent=None):
        super().__init__(parent)
        self.parent_window = parent_window
        self.template_code = template

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(10)

        # 1. 标题和按钮行
        header_layout = QHBoxLayout()
        self.title_label = SubtitleLabel(name)
        setFont(self.title_label, 16, QFont.Bold)

        self.copy_btn = TransparentToolButton(FluentIcon.COPY, self)
        self.copy_btn.setToolTip("复制完整代码")
        self.copy_btn.clicked.connect(self._on_copy)

        self.insert_btn = TransparentToolButton(FluentIcon.ADD, self)
        self.insert_btn.setToolTip("插入到代码")
        self.insert_btn.clicked.connect(self._on_insert)

        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.copy_btn)
        header_layout.addWidget(self.insert_btn)
        self.layout.addLayout(header_layout)

        # 2. 描述文字
        self.desc_label = CaptionLabel(desc)
        self.desc_label.setWordWrap(True)
        self.layout.addWidget(self.desc_label)

        # 3. 代码展示区域
        self.code_edit = QPlainTextEdit()
        self.code_edit.setPlainText(template.strip())
        self.code_edit.setReadOnly(True)
        self.code_edit.setMaximumHeight(150)  # 限制高度，防止超长代码撑爆卡片

        # 代码框样式：浅色背景、等宽字体、无边框
        code_font = QFont("Consolas", 13)
        if not code_font.exactMatch(): code_font = QFont("Monospace", 13)
        self.code_edit.setFont(code_font)
        self.code_edit.setStyleSheet("""
            QPlainTextEdit {
                background-color: rgba(0, 0, 0, 0.04);
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 6px;
                padding: 5px;
                color: #004E8C;
            }
        """)
        # 禁用滚动条显示（如果不需要的话），或者保持默认
        self.layout.addWidget(self.code_edit)

    def _on_copy(self):
        QApplication.clipboard().setText(self.template_code)
        InfoBar.success("复制成功", "代码模板已存入剪贴板", duration=1000, parent=self.parent_window.window())

    def _on_insert(self):
        self.parent_window.insert_to_editor(self.template_code)


class PluginTemplateToolWindow(ToolWindow):
    name = "插件模板库"
    icon = FluentIcon.CODE
    default_position = DockPosition.TOP

    def setup_ui(self):
        self.plugin_manager = NodePluginManager()

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)  # 边缘留白交给滚动区内部
        self.main_layout.setSpacing(0)

        # --- 顶部搜索栏区域 ---
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(15, 15, 15, 10)

        self.search_edit = SearchLineEdit(self)
        self.search_edit.setPlaceholderText("搜索插件名称、描述或内容...")
        self.search_edit.textChanged.connect(self.filter_plugins)

        title_row = QHBoxLayout()
        title_row.addWidget(StrongBodyLabel("可用代码片段"))
        title_row.addStretch()
        refresh_btn = TransparentToolButton(FluentIcon.SYNC)
        refresh_btn.clicked.connect(self.refresh_list)
        title_row.addWidget(refresh_btn)

        top_layout.addLayout(title_row)
        top_layout.addWidget(self.search_edit)
        self.main_layout.addWidget(top_widget)

        # --- 滚动区域 ---
        self.scroll_area = SingleDirectionScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none; background: transparent;")

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(15, 5, 15, 15)
        self.container_layout.setSpacing(15)  # 卡片之间的间距
        self.container_layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.container)
        self.main_layout.addWidget(self.scroll_area)
        self.refresh_list()

    def get_built_in_templates(self):
        """定义硬编码的内置模板"""
        return [
            {
                "name": "流式输出 (显示)",
                "desc": "流式输出结果，并将结果同步到节点端口以及全局变量，同时在节点 UI 上实时展示结果,注意流式输出params的key必须是节点端口名。",
                "template": """self.emit_message(
            method="stream.output",
            params={
                "output1": {"data": "test", "data_type": "str", "plugin": "display_str"}, 
                "output2": {"data": 1, "data_type": "list", "plugin": "display_list"},
                "output2": {"data": 1, "data_type": "list"} # 如果某个实时输出不想展示可以不填展示参数
            },
            extra={} 
        )"""
            },
            {
                "name": "流式输出 (隐藏)",
                "desc": "流式输出结果并同步到端口和变量，但不在节点 UI 上进行实时显示,注意流式输出params的key必须是节点端口名。",
                "template": """self.emit_message(
            method="stream.output",
            params={
                "output1": {"data": "test", "data_type": "str"}, 
                "output2": {"data": 1, "data_type": "list"}
            }
        )"""
            }
        ]

    def refresh_list(self):
        """刷新列表：合并内置模板和动态插件"""
        self.all_data = []

        # 1. 加入内置模板
        self.all_data.extend(self.get_built_in_templates())

        # 2. 加入动态插件
        for p in self.plugin_manager.plugins.values():
            if hasattr(p, 'plugin_template') and p.plugin_template:
                self.all_data.append({
                    "name": getattr(p, 'plugin_name', p.plugin_id),
                    "desc": getattr(p, 'plugin_desc', "暂无描述"),
                    "template": p.plugin_template
                })

        self.display_cards(self.all_data)

    def display_cards(self, data_list):
        """清空并重新渲染卡片"""
        # 清除旧卡片
        while self.container_layout.count():
            child = self.container_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # 添加新卡片
        for item in data_list:
            card = PluginCard(
                item['name'],
                item['desc'],
                item['template'],
                self
            )
            self.container_layout.addWidget(card)
        self.container_layout.addStretch(1)

    def filter_plugins(self, text):
        search_text = text.lower()
        filtered = [
            item for item in self.all_data
            if search_text in item['name'].lower() or
               search_text in item['desc'].lower() or
               search_text in item['template'].lower()
        ]
        self.display_cards(filtered)

    def insert_to_editor(self, text):
        """根据实际编辑器接口实现"""
        self.homepage._handle_insert_code_from_llm(text)
        InfoBar.success("插入成功", "模板代码已插入编辑器", duration=1000, parent=self.window())