# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QWidget, QApplication,
    QPlainTextEdit
)
from qfluentwidgets import (
    CaptionLabel, SearchLineEdit,
    InfoBar, TransparentToolButton, FluentIcon,
    SingleDirectionScrollArea, CardWidget, SubtitleLabel,
    setFont, isDarkTheme, InfoBarPosition
)

from app.plugins.constants import PluginType
from app.plugins.plugin_manager import UnifiedPluginManager
from app.utils.utils import get_icon
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class PluginCard(CardWidget):
    """优化后的插件代码模板卡片"""

    def __init__(self, name, desc, template, parent_window, parent=None):
        super().__init__(parent)
        self.parent_window = parent_window
        self.template_code = template.strip()

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(12)

        # 1. 顶部栏：标题 + 按钮组
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.title_label = SubtitleLabel(self.tr(name))

        # 按钮组：复制 & 插入
        self.btn_layout = QHBoxLayout()
        self.btn_layout.setSpacing(4)

        self.copy_btn = TransparentToolButton(FluentIcon.COPY, self)
        self.copy_btn.setFixedSize(32, 32)
        self.copy_btn.setToolTip("复制完整代码")
        self.copy_btn.clicked.connect(self._on_copy)

        self.insert_btn = TransparentToolButton(get_icon("插入"), self)
        self.insert_btn.setFixedSize(32, 32)
        self.insert_btn.setToolTip("一键插入编辑器")
        self.insert_btn.clicked.connect(self._on_insert)

        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.insert_btn)
        header_layout.addWidget(self.copy_btn)
        self.layout.addLayout(header_layout)

        # 2. 描述区域：使用半透明副文本色
        self.desc_label = CaptionLabel(self.tr(desc))
        self.desc_label.setWordWrap(True)
        self.layout.addWidget(self.desc_label)

        # 3. 代码容器
        self.setup_code_block()

    def setup_code_block(self):
        """配置适配主题的代码编辑器样式"""
        self.code_edit = QPlainTextEdit()
        self.code_edit.setPlainText(self.template_code)
        self.code_edit.setReadOnly(True)
        self.code_edit.setMaximumHeight(160)
        self.code_edit.setMinimumHeight(80)

        # 字体设置
        font_family = "Consolas" if QApplication.style().objectName() != "fusion" else "Monospace"
        code_font = QFont(font_family, 11)
        self.code_edit.setFont(code_font)

        # 根据深浅色主题调整颜色方案
        dark = isDarkTheme()
        bg_color = "rgba(255, 255, 255, 0.05)" if dark else "rgba(0, 0, 0, 0.04)"
        border_color = "rgba(255, 255, 255, 0.1)" if dark else "rgba(0, 0, 0, 0.08)"
        text_color = "#4FC1FF" if dark else "#004E8C"  # 深色模式浅蓝，浅色模式深蓝

        self.code_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
                padding: 8px;
                color: {text_color};
            }}
            QScrollBar:vertical {{
                width: 8px;
                background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: {border_color};
                border-radius: 4px;
            }}
        """)

        # 隐藏水平滚动条，垂直按需
        self.code_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.layout.addWidget(self.code_edit)

    def _on_copy(self):
        QApplication.clipboard().setText(self.template_code)
        InfoBar.success("复制成功", "代码模板已存入剪贴板",
                        duration=1500, position=InfoBarPosition.TOP, parent=self.parent_window.window())

    def _on_insert(self):
        self.parent_window.insert_to_editor(self.template_code)


class PluginTemplateToolWindow(ToolWindow):
    name = "插件模板库"
    icon = ":/icons/组件.png"
    default_position = DockPosition.TOP

    def setup_ui(self):
        self.plugin_manager = UnifiedPluginManager.get_instance()
        self.all_data = []

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # --- 顶部交互区 ---
        top_container = QWidget()
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(16, 16, 16, 8)
        top_layout.setSpacing(12)

        # 标题行
        title_row = QHBoxLayout()
        title_label = SubtitleLabel("可用插件片段")
        setFont(title_label, 18, QFont.Bold)

        self.refresh_btn = TransparentToolButton(FluentIcon.SYNC)
        self.refresh_btn.setToolTip("刷新插件列表")
        self.refresh_btn.clicked.connect(self.refresh_list)

        title_row.addWidget(title_label)
        title_row.addStretch()
        title_row.addWidget(self.refresh_btn)
        top_layout.addLayout(title_row)

        # 搜索框
        self.search_edit = SearchLineEdit(self)
        self.search_edit.setPlaceholderText("搜索插件名称、描述或代码内容...")
        self.search_edit.textChanged.connect(self.filter_plugins)
        top_layout.addWidget(self.search_edit)

        self.main_layout.addWidget(top_container)

        # --- 滚动卡片列表 ---
        self.scroll_area = SingleDirectionScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMinimumWidth(350)
        self.scroll_area.setStyleSheet("border: none; background: transparent;")

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(16, 8, 16, 20)
        self.container_layout.setSpacing(5)
        self.container_layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.container)
        self.main_layout.addWidget(self.scroll_area)

        # 初次加载
        self.refresh_list()

    def get_built_in_templates(self):
        """定义硬编码的内置模板"""
        return [
            {
                "name": "流式输出 (节点展示)",
                "desc": "流式输出结果并同步到端口。extra['display']=True 会在节点 UI 上显示实时结果，注意 params 的键必须与节点端口名一致。",
                "template": """
        self.emit_message(
            method="stream.output",
            params={
                "output1": {"data": "test", "data_type": "str", "plugin": "display_str"}, 
                "output2": {"data": 1, "data_type": "list", "plugin": "display_list"},
                "output3": {"data": "hidden", "data_type": "str"} # 不带 plugin 参数则不实时展示
            }
        )"""
            },
            {
                "name": "流式输出 (静默更新)",
                "desc": "流式输出结果并同步到端口和变量，但不会触发节点 UI 的实时内容展示，适用于后台静默数据同步。",
                "template": """
        self.emit_message(
            method="stream.output",
            params={
                "output1": {"data": "test", "data_type": "str"}, 
                "output2": {"data": 1, "data_type": "list"}
            }
        )"""
            }
        ]

    def refresh_list(self):
        """重新扫描插件并刷新 UI"""
        self.all_data = []
        # 1. 内置模板
        self.all_data.extend(self.get_built_in_templates())
        # 2. 插件动态模板
        for p in self.plugin_manager.list_plugins(PluginType.NODE).values():
            if hasattr(p, 'plugin_template') and p.plugin_template:
                self.all_data.append({
                    "name": getattr(p, 'plugin_name', p.plugin_id),
                    "desc": getattr(p, 'plugin_desc', "动态加载的插件模板"),
                    "template": p.plugin_template
                })
        self.display_cards(self.all_data)

    def display_cards(self, data_list):
        """清除并重新渲染卡片流"""
        # 清理旧组件
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 重新生成
        for item in data_list:
            card = PluginCard(
                item['name'],
                item['desc'],
                item['template'],
                self
            )
            self.container_layout.addWidget(card)

        # 底部留白确保滚动顺滑
        self.container_layout.addStretch(1)

    def filter_plugins(self, text):
        kw = text.lower()
        filtered = [
            i for i in self.all_data
            if kw in i['name'].lower() or kw in i['desc'].lower() or kw in i['template'].lower()
        ]
        self.display_cards(filtered)

    def insert_to_editor(self, text):
        """调用主窗口逻辑插入代码"""
        if hasattr(self.homepage, '_handle_insert_code_from_llm'):
            self.homepage._handle_insert_code_from_llm(text)
            InfoBar.success("已插入", "模板代码已成功添加到编辑器",
                            duration=1000, position=InfoBarPosition.TOP, parent=self.window())
        else:
            QApplication.clipboard().setText(text)
            InfoBar.warning("插入失败", "未找到编辑器接口，代码已复制到剪贴板",
                            duration=2000, parent=self.window())