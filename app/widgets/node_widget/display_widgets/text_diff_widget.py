# -*- coding: utf-8 -*-
import difflib

from qtpy import QtWidgets, QtCore, QtGui


class TextDiffWidget(QtWidgets.QTextBrowser):
    sizeHintChanged = QtCore.Signal()

    def __init__(self, parent=None, node=None):
        super().__init__(parent)
        self.setReadOnly(True)

        # 禁用横向滚动条，启用自动换行
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setLineWrapMode(QtWidgets.QTextBrowser.WidgetWidth)  # 强制在控件宽度内换行

        # 基础样式：无边框，透明背景（由外层节点控制背景）
        self.setStyleSheet("background-color: transparent; border: none;")
        self.setFrameShape(QtWidgets.QFrame.NoFrame)

        self._ideal_height = 200

    def set_value(self, value):
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            self.setHtml("<div style='color:#666;'>Empty or Invalid Data</div>")
            return

        text1 = str(value[0]).splitlines()
        text2 = str(value[1]).splitlines()

        # 使用 difflib 生成基础 HTML
        d = difflib.HtmlDiff(tabsize=4)
        # wrapcolumn 参数在这里其实会被 CSS 覆盖，但设为一个合理值有助于解析
        raw_diff_table = d.make_table(text1, text2, context=True, numlines=3)

        # 核心：深度定制 CSS 以适配深色主题和响应式布局
        # .diff_header: 行号区域
        # .diff_next: 锚点区域（隐藏）
        # .diff_add: 新增内容 (绿)
        # .diff_sub: 删除内容 (红)
        # .diff_chg: 修改内容 (黄)
        style = """
        <style>
            table.diff {
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 11px;
                border-collapse: collapse;
                width: 100%;
                table-layout: fixed; /* 锁定表格宽度，防止被内容撑开 */
                color: #d1d5db;
                background-color: #0d1117;
            }
            td {
                padding: 1px 4px;
                word-wrap: break-word; /* 强制长行换行 */
                white-space: pre-wrap; /* 保持空格的同时允许换行 */
            }
            /* 行号列样式 */
            .diff_header {
                background-color: #161b22;
                color: #484f58;
                text-align: right;
                width: 30px;
                border-right: 1px solid #30363d;
                -webkit-user-select: none;
            }
            /* 隐藏 difflib 默认的“下一处修改”跳转链接，因为在节点里没意义 */
            .diff_next { display: none; }

            /* 差异高亮颜色 - 仿 GitHub Dark 风格 */
            .diff_add { background-color: #2ea04333; color: #7ee787; } /* 半透明绿 */
            .diff_sub { background-color: #f8514933; color: #ff7b72; } /* 半透明红 */
            .diff_chg { background-color: #9e6a0333; color: #d29922; } /* 半透明黄 */

            /* 修正 difflib 内部 span 的样式 */
            span.diff_add { background-color: #2ea04366; color: #aff5b4; text-decoration: none; }
            span.diff_sub { background-color: #f8514966; color: #ffdcd7; text-decoration: none; }
            span.diff_chg { background-color: #9e6a0366; color: #f8e3a1; text-decoration: none; }

            /* 去除表格边框线，只留行号分割线 */
            border { border: none; }
        </style>
        """

        full_html = f"<html><head>{style}</head><body>{raw_diff_table}</body></html>"
        self.setHtml(full_html)

        # 延迟更新高度，确保渲染完成后计算
        QtCore.QTimer.singleShot(10, self._update_size)

    def _update_size(self):
        # 关键：根据文档内容重新计算控件所需的高度
        doc = self.document()
        doc.setTextWidth(self.width())  # 告知文档当前宽度以计算换行
        new_height = doc.size().height() + 10  # 留一点边距

        if abs(self._ideal_height - new_height) > 5:
            self._ideal_height = new_height
            self.sizeHintChanged.emit()
            self.updateGeometry()

    def sizeHint(self):
        # 宽度至少 400（由节点布局控制），高度动态返回内容高度
        return QtCore.QSize(400, int(self._ideal_height))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 当节点被用户手动拉伸宽度时，重新计算高度（因为换行会变化）
        self._update_size()