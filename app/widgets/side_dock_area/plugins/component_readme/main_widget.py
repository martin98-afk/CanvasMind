# -*- coding: utf-8 -*-
import os
import markdown
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtWidgets import QVBoxLayout, QTextBrowser, QFrame
from qfluentwidgets import (StrongBodyLabel, FluentIcon, CaptionLabel)

from app.utils.utils import resource_path
from app.widgets.side_dock_area.tool_window import ToolWindow, DockPosition


class NodeDocToolWindow(ToolWindow):
    name = "节点说明"
    icon = FluentIcon.INFO
    default_position = DockPosition.TOP

    def setup_ui(self):
        """初始化UI结构，硬编码为深色主题"""
        # 设置整个窗口背景色
        self.setStyleSheet("background-color: #202020; border: none;")

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # --- 顶部标题栏 ---
        self.header_widget = QFrame()
        self.header_widget.setStyleSheet("background-color: #282828;")  # 标题栏稍微亮一点
        header_layout = QVBoxLayout(self.header_widget)
        header_layout.setContentsMargins(20, 15, 20, 10)

        self.node_name_label = StrongBodyLabel("未选择节点")
        self.node_name_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #FFFFFF;")

        self.uuid_label = CaptionLabel("请在画布中选中节点以查看文档")
        self.uuid_label.setStyleSheet("color: #AAAAAA;")

        header_layout.addWidget(self.node_name_label)
        header_layout.addWidget(self.uuid_label)

        # 分割线
        self.line = QFrame()
        self.line.setFixedHeight(1)
        self.line.setStyleSheet("background-color: #333333;")

        # --- 文档显示区 ---
        self.doc_view = QTextBrowser()
        self.doc_view.setOpenExternalLinks(True)
        self.doc_view.setFrameShape(QFrame.NoFrame)
        # 强制设置背景透明（继承窗口的深色背景）
        self.doc_view.setStyleSheet("background-color: transparent;")

        # 应用固定的深色 Markdown CSS
        self.doc_view.document().setDefaultStyleSheet(self._get_dark_markdown_css())

        self.main_layout.addWidget(self.header_widget)
        self.main_layout.addWidget(self.line)
        self.main_layout.addWidget(self.doc_view)

    def _get_dark_markdown_css(self):
        """固定的深色主题 CSS"""
        text_color = "#E3E3E3"
        h_color = "#60CDFF"  # 标题蓝色
        line_color = "#333333"  # 分割线颜色
        code_bg = "#2D2D2D"  # 代码块背景
        code_border = "#444444"  # 代码块边框
        quote_color = "#999999"  # 引用文字颜色

        return f"""
            QTextBrowser {{
                font-family: 'Segoe UI', 'Microsoft YaHei', 'PingFang SC';
                color: {text_color};
                padding: 10px 20px;
                font-size: 14px;
            }}
            h1 {{ font-size: 22px; color: {h_color}; border-bottom: 1px solid {line_color}; padding-bottom: 5px; }}
            h2 {{ font-size: 18px; color: {text_color}; border-bottom: 1px solid {line_color}; margin-top: 20px; }}
            h3 {{ font-size: 16px; font-weight: bold; color: {text_color}; }}
            p, li {{ line-height: 1.6; color: {text_color}; }}
            a {{ color: {h_color}; text-decoration: none; }}

            /* 代码块样式 */
            pre {{
                background-color: {code_bg};
                border: 1px solid {code_border};
                padding: 10px;
                border-radius: 6px;
                font-family: 'Consolas', 'Monaco', monospace;
            }}
            code {{
                background-color: {code_bg};
                color: #FF79C6; /* 让行内代码颜色鲜亮一点 */
                padding: 2px 4px;
                border-radius: 3px;
                font-family: 'Consolas', monospace;
            }}

            /* 表格样式 */
            table {{
                border-collapse: collapse;
                width: 100%;
                margin: 10px 0;
                background-color: #252525;
            }}
            th {{
                background-color: #333333;
                border: 1px solid {code_border};
                padding: 8px;
                text-align: left;
                color: {h_color};
                font-weight: bold;
            }}
            td {{
                border: 1px solid {code_border};
                padding: 8px;
                color: {text_color};
            }}

            /* 引用块样式 */
            blockquote {{
                margin: 0;
                padding-left: 15px;
                color: {quote_color};
                border-left: 4px solid {h_color};
                background-color: #252525;
            }}

            /* 图片显示优化：限制大小且居中 */
            img {{
                display: block;
                margin-left: auto;
                margin-right: auto;
                max-width: 450px;  /* 限制图片显示宽度，防止撑满屏幕 */
                border-radius: 6px;
                margin-top: 15px;
                margin-bottom: 15px;
                border: 1px solid #444; /* 给图片加个暗色边框，防止黑白图溢出 */
            }}
        """

    def show_node_doc(self, node_name, node_uuid):
        """
        接口函数：显示文档
        """
        self.node_name_label.setText(node_name)

        if not node_uuid:
            self.uuid_label.setText("UUID 缺失")
            self.doc_view.setHtml("<p style='text-align:center; color:gray; margin-top:20px;'>该节点无组件 UUID</p>")
            return

        self.uuid_label.setText(f"组件ID: {node_uuid}")

        # 1. 路径定位
        base_dir = resource_path(f"app/component_extensions/{node_uuid}")
        readme_path = os.path.join(base_dir, "README.md")

        if os.path.exists(readme_path):
            try:
                with open(readme_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # 2. Markdown 渲染 (包含 extra 扩展以支持表格)
                html_content = markdown.markdown(content, extensions=['extra', 'fenced_code', 'nl2br'])

                # 3. 设置图片搜索基准路径
                base_url = QUrl.fromLocalFile(base_dir + os.path.sep)
                self.doc_view.document().setBaseUrl(base_url)

                # 4. 显示内容
                self.doc_view.setHtml(html_content)

            except Exception as e:
                self.doc_view.setHtml(f"<p style='color:#FF5555; padding:20px;'>渲染失败: {str(e)}</p>")
        else:
            self.doc_view.setHtml(f"""
                <div style='text-align: center; margin-top: 50px; color: #666666;'>
                    <p style='font-size: 16px;'>未找到 README.md</p>
                    <p style='font-size: 12px;'>请确认文件是否存在于：</p>
                    <code style='color: #888888; background: #222;'>{readme_path}</code>
                </div>
            """)