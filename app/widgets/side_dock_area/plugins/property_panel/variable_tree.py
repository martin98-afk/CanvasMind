# -*- coding: utf-8 -*-
import os
import subprocess
import sys
from functools import lru_cache
from typing import Any

import numpy as np
from PyQt5.QtCore import Qt, QSize, QRect, QPoint
from PyQt5.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QImage,
    QFont, QBrush, QFontMetrics
)
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QTreeWidgetItem,
    QHeaderView, QStyledItemDelegate, QFrame, QHBoxLayout, QLabel, QStyle
)
from loguru import logger
# === Fluent Widgets ===
from qfluentwidgets import (
    TreeWidget, RoundMenu, Action, TextEdit, isDarkTheme, FluentIcon as FIF, BodyLabel, CardWidget, IconWidget
)
from qfluentwidgets.components.widgets.card_widget import CardSeparator

from app.utils.utils import get_icon

# === Spyder Plugins (Soft Import) ===
try:
    from spyder.plugins.variableexplorer.widgets.arrayeditor import ArrayEditor
    from spyder.plugins.variableexplorer.widgets.dataframeeditor import DataFrameEditor
    from spyder.plugins.variableexplorer.widgets.namespacebrowser import NamespaceBrowser

    HAS_SPYDER = True
except ImportError:
    HAS_SPYDER = False

# === Constants ===
MAX_NESTING_DEPTH = 5
MAX_DICT_KEYS = 200
MAX_LIST_ITEMS = 200

# 自定义数据角色，用于加速 Delegate 渲染
ROLE_RAW_VALUE = Qt.UserRole + 1
ROLE_TYPE_COLOR = Qt.UserRole + 2


# ==========================================
# 1. 核心数据解析逻辑 (Logic Layer)
# ==========================================

class VariableUtils:
    """处理变量类型判断、格式化和图标生成的工具类 (优化性能版)"""

    @staticmethod
    @lru_cache(maxsize=1024)
    def cached_is_file(path: str) -> bool:
        """通过缓存避免循环中的重复磁盘 I/O"""
        try:
            return isinstance(path, str) and len(path) < 1024 and os.path.isfile(path)
        except:
            return False

    @staticmethod
    def is_image_file(obj):
        if isinstance(obj, str) and VariableUtils.cached_is_file(obj):
            ext = os.path.splitext(obj.lower())[1]
            return ext in {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}
        return False

    @staticmethod
    def is_pil_image(obj):
        try:
            from PIL import Image
            return isinstance(obj, Image.Image)
        except ImportError:
            return False

    @staticmethod
    def is_pandas_series(obj):
        try:
            import pandas as pd
            return isinstance(obj, pd.Series)
        except ImportError:
            return False

    @staticmethod
    def is_dataframe(obj):
        try:
            import pandas as pd
            return isinstance(obj, pd.DataFrame)
        except ImportError:
            return False

    @staticmethod
    def get_formatted_value(obj):
        """获取用于显示的简短字符串 - 特殊处理 shape 为 () 的数组"""
        if obj is None:
            return "None"

        # 核心修改：处理 Numpy 数组
        if hasattr(obj, 'shape'):
            # [功能优化]：如果是纯数值标量数组 (shape 为 ())，直接展示数值
            if obj.shape == ():
                try:
                    return str(obj.item())
                except:
                    return str(obj)

            # 多维数组显示 shape 和类型，防止大数组格式化卡死
            dtype_info = f", {obj.dtype}" if hasattr(obj, 'dtype') else ""
            return f"<{type(obj).__name__}> shape={obj.shape}{dtype_info}"

        # 处理普通标量
        if hasattr(obj, 'dtype') and np.isscalar(obj):
            try:
                obj = obj.item()
            except:
                pass

        if isinstance(obj, bool):
            return str(obj)
        elif isinstance(obj, (int, float)):
            return str(obj)
        elif isinstance(obj, str):
            if VariableUtils.is_image_file(obj):
                return f"<Image File> {os.path.basename(obj)}"
            elif VariableUtils.cached_is_file(obj):
                return f"<File> {obj}"
            return f"'{obj}'" if len(obj) < 50 else f"'{obj[:50]}...'"

        elif VariableUtils.is_pil_image(obj):
            return f"<PIL.Image> {obj.size} {obj.mode}"
        elif isinstance(obj, (list, tuple)):
            return f"<{type(obj).__name__}> len={len(obj)}"
        elif isinstance(obj, dict):
            return f"<dict> len={len(obj)}"

        # 默认回退，截断过长的字符串
        res = str(obj)
        return res[:100] if len(res) > 100 else res

    @staticmethod
    def get_type_name(obj):
        """获取简短的类型名称用于图标"""
        if obj is None: return "None"
        if isinstance(obj, bool): return "Bool"
        if isinstance(obj, int): return "Int"
        if isinstance(obj, float): return "Float"

        if isinstance(obj, str):
            if VariableUtils.is_image_file(obj): return "Img"
            if VariableUtils.cached_is_file(obj): return "File"
            return "Str"

        if isinstance(obj, dict): return "Dict"
        if isinstance(obj, list): return "List"
        if isinstance(obj, tuple): return "Tuple"
        if VariableUtils.is_dataframe(obj): return "DF"
        if VariableUtils.is_pandas_series(obj): return "Ser"
        # 即使 shape 为 () 依然显示为数组图标，以区分基础类型
        if hasattr(obj, 'shape'): return "Arr"
        if VariableUtils.is_pil_image(obj): return "Img"
        return "Obj"

    @staticmethod
    @lru_cache(maxsize=128)
    def generate_icon(type_name: str, dark_mode: bool) -> QIcon:
        size = 28
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        colors = {
            "Str": "#CE9178", "Int": "#B5CEA8", "Float": "#B5CEA8",
            "Bool": "#569CD6", "List": "#4EC9B0", "Dict": "#C586C0",
            "DF": "#FF9800", "Arr": "#4CAF50", "Img": "#E91E63",
            "File": "#DCDCAA", "None": "#808080", "Obj": "#9CDCFE"
        }
        base_color = QColor(colors.get(type_name, "#9CDCFE"))
        bg_rect = QRect(2, 6, size - 4, size - 12)
        painter.setPen(Qt.NoPen)
        painter.setBrush(base_color)
        painter.drawRoundedRect(bg_rect, 4, 4)

        painter.setPen(QColor("black"))
        font = QFont("Consolas", 8, QFont.Bold)
        painter.setFont(font)
        painter.drawText(bg_rect, Qt.AlignCenter, type_name[:4])
        painter.end()
        return QIcon(pixmap)


# ==========================================
# 2. 视觉代理 (Visual Delegate - Optimized)
# ==========================================

class VariableValueDelegate(QStyledItemDelegate):
    """逻辑剥离，支持多行文本的高度自适应性能优化版"""

    def paint(self, painter, option, index):
        if index.column() != 1:
            super().paint(painter, option, index)
            return

        painter.save()

        # 1. 获取颜色和文本
        text_color = index.data(ROLE_TYPE_COLOR)
        if not isinstance(text_color, QColor):
            text_color = QColor("#D4D4D4") if isDarkTheme() else QColor("#333333")

        if option.state & QStyle.State_Selected:
            text_color = QColor("#FFFFFF")

        text = str(index.data(Qt.DisplayRole))

        # 2. 设置画笔和字体
        painter.setFont(QFont("Consolas", 10))
        painter.setPen(text_color)

        # 3. 绘制区域处理
        # 如果有换行符，我们顶端对齐并留出 padding；否则继续居中
        rect = option.rect.adjusted(5, 3, -5, -3)

        if '\n' in text:
            # 多行文本使用 AlignTop 避免文字重叠
            painter.drawText(rect, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, text)
        else:
            # 单行文本保持垂直居中
            painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, text)

        painter.restore()

    def sizeHint(self, option, index):
        """关键：根据内容动态计算行高"""
        size = super().sizeHint(option, index)
        if index.column() == 1:
            text = str(index.data(Qt.DisplayRole))
            if '\n' in text:
                font = QFont("Consolas", 10)
                fm = QFontMetrics(font)
                # 计算文本在当前列宽下的实际占用矩形
                # width 使用当前列宽，如果没有则给个足够大的值
                width = option.rect.width() if option.rect.width() > 0 else 500
                text_rect = fm.boundingRect(0, 0, width, 0, Qt.AlignLeft | Qt.TextWordWrap, text)

                # 返回计算的高度 + 上下间距(6)
                return QSize(size.width(), max(size.height(), text_rect.height() + 10))
        return size

# ==========================================
# 3. 详情弹窗 (Improved Detail Popup)
# ==========================================

class VariableDetailPopup(QWidget):
    """
    悬浮显示的变量详情卡片
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 100); border-radius:12px;")
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.card = CardWidget(self)
        self.main_layout.addWidget(self.card)
        self.content_layout = QVBoxLayout(self.card)
        self.content_layout.setContentsMargins(16, 12, 16, 16)

        # 标题栏
        header_layout = QHBoxLayout()
        self.icon_label = IconWidget(FIF.INFO)
        self.icon_label.setFixedSize(18, 18)
        self.title_label = BodyLabel("Variable Detail")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #FFA500;")
        header_layout.addWidget(self.icon_label)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        self.content_layout.addLayout(header_layout)

        # 分隔线
        self.content_layout.addWidget(CardSeparator(self))
        self.preview_widget = None

    def set_data(self, obj, name=""):
        self.title_label.setText(f"{name} ({type(obj).__name__})")
        if self.preview_widget:
            self.preview_widget.deleteLater()
            self.preview_widget = None

        if VariableUtils.is_image_file(obj) or VariableUtils.is_pil_image(obj):
            self.preview_widget = self._load_pixmap(obj)
        elif VariableUtils.is_dataframe(obj) or VariableUtils.is_pandas_series(obj):
            text = str(obj.head(10)) + f"\n\nShape: {obj.shape}"
            self.preview_widget = self._create_text_edit(text)
        else:
            # 防止巨大数组
            if hasattr(obj, 'shape') and hasattr(obj, 'nbytes') and obj.nbytes > 1024 * 1024 and obj.ndim > 0:
                text = f"Large Object: {type(obj).__name__}\nShape: {obj.shape}\nDtype: {obj.dtype}\n\n[Data Truncated for UI performance]"
            else:
                text = str(obj)
            self.preview_widget = self._create_text_edit(text)

        self.content_layout.addWidget(self.preview_widget)
        self.adjustSize()

    def _create_text_edit(self, text):
        widget = TextEdit()
        widget.setPlainText(text)
        widget.setReadOnly(True)
        widget.setFixedSize(500, 300)
        widget.setFont(QFont("Consolas", 10))
        return widget

    def _load_pixmap(self, obj):
        pixmap = None
        if isinstance(obj, str):
            pixmap = QPixmap(obj)
        elif VariableUtils.is_pil_image(obj):
            try:
                img = obj
                if img.mode not in ('RGB', 'RGBA'): img = img.convert('RGBA' if 'A' in img.mode else 'RGB')
                data = img.tobytes()
                qim = QImage(data, img.width, img.height,
                             QImage.Format_RGBA8888 if img.mode == 'RGBA' else QImage.Format_RGB8888)
                pixmap = QPixmap.fromImage(qim)
            except:
                pass
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(500, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            img_label = QLabel()
            img_label.setPixmap(scaled)
            img_label.setAlignment(Qt.AlignCenter)
            img_label.setStyleSheet("background: #1e1e1e; border-radius: 6px; padding: 8px;")
            return img_label
        return BodyLabel("⚠️ 图像加载失败", self)

    def show_at_left_of(self, reference_widget: QWidget):
        self.adjustSize()

        ref_rect = reference_widget.rect()
        ref_global = reference_widget.mapToGlobal(ref_rect.topLeft())
        popup_w = self.width()
        popup_h = self.height()

        x = ref_global.x() - popup_w - 4
        y = ref_global.y()

        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            x = max(x, geom.left())
            if x + popup_w > geom.right():
                x = ref_global.x() + ref_rect.width() + 4
            if y + popup_h > geom.bottom():
                y = geom.bottom() - popup_h
            y = max(y, geom.top())

        self.move(x, y)
        self.show()
        self.setFocus()

    def show_near(self, rect_global: QRect):
        """智能显示在目标区域左侧或右侧"""
        screen_geo = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        w, h = self.width(), self.height()

        # 尝试显示在左侧
        x = rect_global.left() - w - 10
        if x < screen_geo.left(): x = rect_global.right() + 10
        y = max(min(rect_global.top(), screen_geo.bottom() - h), screen_geo.top())
        self.move(x, y)
        self.show()
        self.setFocus()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape: self.close()


# ==========================================
# 4. 主树控件 (VariableTreeWidget - Optimized)
# ==========================================

class VariableTreeWidget(TreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Name", "Value"])
        self.setUniformRowHeights(True)
        self.setAnimated(False)
        self.setIconSize(QSize(20, 20))
        self.setIndentation(10)
        self.setUniformRowHeights(False)
        # 开启自动换行支持
        self.setWordWrap(True)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.setItemDelegate(VariableValueDelegate(self))
        self.itemExpanded.connect(self.on_item_expanded)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.setStyleSheet("""
            QTreeWidget { background-color: #2d2d30; color: #d4d4d4; border: none; font-family: Consolas, monospace; font-size: 11px; }
            QTreeWidget::item { padding: 2px; }
            QTreeWidget::item:hover { background-color: #3e3e42; }
            QTreeWidget::item:selected { background-color: #37373d; }
            QHeaderView::section { background-color: #252526; color: #d4d4d4; padding: 0px; border: none; }
        """)

    def set_data(self, data: Any, root_name: str = "Variables"):
        self.clear()
        root_item = QTreeWidgetItem([root_name, ""])
        self._set_node_metadata(root_item, data)
        self.addTopLevelItem(root_item)
        root_item.setExpanded(True)

    def _set_node_metadata(self, item: QTreeWidgetItem, obj: Any):
        """核心数据绑定与样式预计算"""
        item.setData(1, ROLE_RAW_VALUE, obj)
        val_str = VariableUtils.get_formatted_value(obj)
        item.setText(1, val_str)

        type_name = VariableUtils.get_type_name(obj)
        item.setIcon(0, VariableUtils.generate_icon(type_name, isDarkTheme()))

        # 预计算颜色存入 UserRole
        dark = isDarkTheme()
        if obj is None or isinstance(obj, bool):
            color = QColor("#569CD6")
        elif isinstance(obj, (int, float)) or (hasattr(obj, 'dtype') and np.isscalar(obj)):
            color = QColor("#B5CEA8") if dark else QColor("#098658")
        elif isinstance(obj, str):
            if VariableUtils.cached_is_file(obj):
                color = QColor("#DCDCAA") if dark else QColor("#795E26")
            else:
                color = QColor("#CE9178") if dark else QColor("#A31515")
        elif hasattr(obj, 'shape'):
            # 如果是标量数组，按数值着色
            if obj.shape == ():
                color = QColor("#B5CEA8") if dark else QColor("#098658")
            else:
                color = QColor("#4CAF50")
        elif isinstance(obj, (list, dict, tuple)):
            color = QColor("#C586C0")
        else:
            color = QColor("#9CDCFE")
        item.setData(1, ROLE_TYPE_COLOR, color)

        # 子节点指示器判断
        has_children = False
        try:
            if isinstance(obj, (dict, list, tuple)):
                has_children = len(obj) > 0
            elif hasattr(obj, 'shape'):
                # shape 为 () 的数组没有子维度，不显示展开图标
                has_children = obj.ndim > 0 and obj.size > 0
            elif VariableUtils.is_dataframe(obj) or VariableUtils.is_pandas_series(obj):
                has_children = not obj.empty
            elif hasattr(obj, '__dict__'):
                has_children = True
        except:
            pass

        if has_children:
            item.addChild(QTreeWidgetItem(["Loading...", ""]))
            item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)

    def on_item_expanded(self, item: QTreeWidgetItem):
        if item.childCount() == 1 and item.child(0).text(0) == "Loading...":
            item.removeChild(item.child(0))
            obj = item.data(1, ROLE_RAW_VALUE)
            self._load_children(item, obj)

    def _load_children(self, parent_item: QTreeWidgetItem, obj: Any):
        try:
            children = []
            if isinstance(obj, dict):
                for k in list(obj.keys())[:MAX_DICT_KEYS]:
                    child = QTreeWidgetItem([str(k), ""])
                    self._set_node_metadata(child, obj[k])
                    children.append(child)
            elif isinstance(obj, (list, tuple, np.ndarray)):
                length = obj.shape[0] if hasattr(obj, 'shape') else len(obj)
                for i in range(min(length, MAX_LIST_ITEMS)):
                    child = QTreeWidgetItem([f"[{i}]", ""])
                    self._set_node_metadata(child, obj[i])
                    children.append(child)
            elif VariableUtils.is_pandas_series(obj):
                for i in range(min(len(obj), MAX_LIST_ITEMS)):
                    child = QTreeWidgetItem([str(obj.index[i]), ""])
                    self._set_node_metadata(child, obj.iloc[i])
                    children.append(child)
            elif VariableUtils.is_dataframe(obj):
                for col in obj.columns:
                    child = QTreeWidgetItem([str(col), ""])
                    self._set_node_metadata(child, obj[col])
                    children.append(child)
            elif hasattr(obj, '__dict__'):
                attrs = {k: v for k, v in obj.__dict__.items() if not k.startswith('__')}
                for k, v in attrs.items():
                    child = QTreeWidgetItem([k, ""])
                    self._set_node_metadata(child, v)
                    children.append(child)
            parent_item.addChildren(children)
        except Exception as e:
            err = QTreeWidgetItem(["<Error>", str(e)])
            err.setForeground(0, QBrush(Qt.red))
            parent_item.addChild(err)

    def show_context_menu(self, pos: QPoint):
        item = self.itemAt(pos);
        if not item: return
        obj, name = item.data(1, ROLE_RAW_VALUE), item.text(0)
        menu = RoundMenu(parent=self)
        menu.addAction(Action(FIF.INFO, "查看详情", triggered=lambda: self._show_detail_popup(item, obj)))
        menu.addAction(Action(FIF.COPY, "复制值", triggered=lambda: QApplication.clipboard().setText(str(obj))))
        if HAS_SPYDER:
            if VariableUtils.is_dataframe(obj) or VariableUtils.is_pandas_series(obj):
                menu.addAction(
                    Action(get_icon("表格"), "在表格中打开", triggered=lambda: self._open_spyder_editor(obj, name)))
            elif hasattr(obj, 'shape') and hasattr(obj, 'dtype'):
                menu.addAction(
                    Action(get_icon("数组"), "查看数组", triggered=lambda: self._open_array_editor(obj, name)))
        if isinstance(obj, str) and VariableUtils.cached_is_file(obj):
            menu.addAction(Action(FIF.FOLDER, "打开所在文件夹", triggered=lambda: self._open_explorer(obj)))
        menu.exec_(self.viewport().mapToGlobal(pos))

    def _show_detail_popup(self, item, obj):
        if not hasattr(self, '_popup'): self._popup = VariableDetailPopup(self)
        self._popup.set_data(obj, item.text(0))
        rect = self.visualItemRect(item)
        self._popup.show_near(QRect(self.viewport().mapToGlobal(rect.topLeft()), rect.size()))

    def _open_explorer(self, path):
        # 1. 获取绝对路径（解决相对路径打不开的问题）
        # 2. 标准化路径（将 / 转为 \，解决第一个路径的问题）
        norm_path = os.path.normpath(os.path.abspath(path))

        # 3. 检查文件是否存在
        if not os.path.exists(norm_path):
            logger.error(f"路径不存在: {norm_path}")
            return

        if sys.platform == "win32":
            # Windows 特有：/select, 后面紧跟路径。
            # 注意：subprocess.run 会自动处理列表中的空格，不需要额外加双引号
            subprocess.run(["explorer", "/select,", norm_path])
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", norm_path])
        else:
            # Linux 只有选中功能较难通用，通常直接打开所在目录
            subprocess.run(["xdg-open", os.path.dirname(norm_path)])

    def _open_spyder_editor(self, data, title):
        if not HAS_SPYDER: return
        if VariableUtils.is_pandas_series(data): data = data.to_frame()
        editor = DataFrameEditor(parent=self, readonly=True, namespacebrowser=NamespaceBrowser(self.parent()))
        if editor.setup_and_check(data, title=title): editor.exec_()

    def _open_array_editor(self, data, title):
        if not HAS_SPYDER: return
        editor = ArrayEditor(parent=self)
        if editor.setup_and_check(data, title=title): editor.exec_()


if __name__ == "__main__":
    from qfluentwidgets import setTheme, Theme

    app = QApplication(sys.argv)
    setTheme(Theme.DARK)
    data = {
        "Numpy Scalar": np.array(3.14159),  # shape 为 ()，将显示数值
        "Numpy 1D": np.array([1, 2, 3]),
        "Huge Video Mock": np.zeros((100, 100, 100)),
        "Normal Dict": {"a": 1, "b": np.array(100)}
    }
    w = QWidget();
    layout = QVBoxLayout(w)
    tree = VariableTreeWidget(w);
    tree.set_data(data, "root")
    layout.addWidget(tree);
    w.resize(800, 600);
    w.show()
    sys.exit(app.exec_())
