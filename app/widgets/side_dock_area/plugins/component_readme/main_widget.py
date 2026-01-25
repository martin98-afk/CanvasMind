# -*- coding: utf-8 -*-
import os
import markdown
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtWidgets import QVBoxLayout, QTextBrowser, QFrame
from qfluentwidgets import (StrongBodyLabel, FluentIcon, CaptionLabel,
                            isDarkTheme)

from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class NodeDocToolWindow(ToolWindow):
    name = "节点说明"
    icon = FluentIcon.INFO
    default_position = DockPosition.TOP

    def setup_ui(self):
        """初始化UI结构"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # --- 顶部标题栏 ---
        self.header_widget = QFrame()
        header_layout = QVBoxLayout(self.header_widget)
        header_layout.setContentsMargins(20, 15, 20, 10)

        self.node_name_label = StrongBodyLabel("未选择节点")
        self.node_name_label.setStyleSheet("font-size: 18px; font-weight: bold;")

        self.uuid_label = CaptionLabel("请在画布中选中节点以查看文档")

        header_layout.addWidget(self.node_name_label)
        header_layout.addWidget(self.uuid_label)

        # 分割线
        self.line = QFrame()
        self.line.setFixedHeight(1)

        # --- 文档显示区 ---
        self.doc_view = QTextBrowser()
        self.doc_view.setOpenExternalLinks(True)
        self.doc_view.setFrameShape(QFrame.NoFrame)
        # 允许加载外部资源
        self.doc_view.setSearchPaths([])

        self.main_layout.addWidget(self.header_widget)
        self.main_layout.addWidget(self.line)
        self.main_layout.addWidget(self.doc_view)

        # 初始应用主题样式
        self._apply_theme_style()

    def _get_markdown_css(self):
        """根据当前主题获取 CSS"""
        dark = isDarkTheme()

        # 颜色变量
        bg_color = "transparent"
        text_color = "#E3E3E3" if dark else "#201F1E"
        h_color = "#60CDFF" if dark else "#0078D4"
        line_color = "#333333" if dark else "#EEEEEE"
        code_bg = "#2D2D2D" if dark else "#F6F8FA"
        code_border = "#444444" if dark else "#E1E4E8"
        quote_color = "#999999" if dark else "#6A737D"

        return f"""
            QTextBrowser {{
                font-family: 'Segoe UI', 'Microsoft YaHei', 'PingFang SC';
                background-color: {bg_color};
                color: {text_color};
                padding: 10px 20px;
                font-size: 14px;
            }}
            h1 {{ font-size: 22px; color: {h_color}; border-bottom: 1px solid {line_color}; padding-bottom: 5px; }}
            h2 {{ font-size: 18px; color: {text_color}; border-bottom: 1px solid {line_color}; margin-top: 20px; }}
            h3 {{ font-size: 16px; font-weight: bold; color: {text_color}; }}
            p, li {{ line-height: 1.6; color: {text_color}; }}
            a {{ color: {h_color}; text-decoration: none; }}

            pre {{
                background-color: {code_bg};
                border: 1px solid {code_border};
                padding: 10px;
                border-radius: 6px;
                font-family: 'Consolas', 'Monaco', monospace;
            }}
            code {{
                background-color: {code_bg};
                color: {text_color};
                padding: 2px 4px;
                border-radius: 3px;
                font-family: 'Consolas', monospace;
            }}

            table {{
                border-collapse: collapse;
                width: 100%;
                margin: 10px 0;
            }}
            th {{
                background-color: {code_bg};
                border: 1px solid {code_border};
                padding: 8px;
                text-align: left;
                color: {text_color};
            }}
            td {{
                border: 1px solid {code_border};
                padding: 8px;
                color: {text_color};
            }}

            blockquote {{
                margin: 0;
                padding-left: 15px;
                color: {quote_color};
                border-left: 4px solid {code_border};
            }}

            img {{
                max-width: 100%;
                height: auto;
                border-radius: 4px;
                margin: 10px 0;
            }}
        """

    def _apply_theme_style(self):
        """应用主题颜色"""
        dark = not isDarkTheme()
        self.uuid_label.setStyleSheet("color: #AAAAAA;" if dark else "color: #666666;")
        self.line.setStyleSheet("background-color: #333333;" if dark else "background-color: #EEEEEE;")
        # 更新默认样式表
        self.doc_view.document().setDefaultStyleSheet(self._get_markdown_css())

    def show_node_doc(self, node_name, node_uuid):
        """
        接口函数：根据 node 的 uuid 查找并显示 README.md
        """
        self.node_name_label.setText(node_name)

        if not node_uuid:
            self.uuid_label.setText("UUID 缺失")
            self.doc_view.setHtml("<p style='text-align:center;'>该节点无组件 UUID</p>")
            return

        self.uuid_label.setText(f"组件ID: {node_uuid}")

        # 1. 路径定位
        base_dir = os.path.abspath(os.path.join(os.getcwd(), "app", "component_extensions", node_uuid))
        readme_path = os.path.join(base_dir, "README.md")

        if os.path.exists(readme_path):
            try:
                with open(readme_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # 2. Markdown 渲染
                html_content = markdown.markdown(content, extensions=['extra', 'fenced_code', 'nl2br'])

                # 3. 修复 arguments 报错：
                # 在 QTextBrowser 中，正确设置 BaseUrl 的方法是通过 document()
                base_url = QUrl.fromLocalFile(base_dir + os.path.sep)
                self.doc_view.document().setBaseUrl(base_url)

                # 4. 只传一个参数给 setHtml
                self.doc_view.setHtml(html_content)

            except Exception as e:
                self.doc_view.setHtml(f"<p style='color:red;'>渲染失败: {str(e)}</p>")
        else:
            self.doc_view.setHtml(f"""
                <div style='text-align: center; margin-top: 50px; color: gray;'>
                    <p>未找到 README.md</p>
                    <code style='font-size: 10px;'>{readme_path}</code>
                </div>
            """)