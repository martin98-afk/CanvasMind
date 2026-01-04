import os
import sys
import subprocess
from functools import lru_cache
from typing import Any, Dict, List, Optional

import numpy as np
from PyQt5.QtCore import Qt, QSize, QRect, QPoint, QEvent
from PyQt5.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QPen, QImage,
    QFont, QFontMetrics, QBrush, QLinearGradient
)
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QTreeWidgetItem,
    QHeaderView, QStyledItemDelegate, QStyleOptionViewItem,
    QFrame, QHBoxLayout, QLabel, QStyle
)

# === Fluent Widgets ===
from qfluentwidgets import (
    TreeWidget, RoundMenu, Action, MessageBoxBase,
    TextEdit, ImageLabel, isDarkTheme, themeColor,
    FluentIcon as FIF, BodyLabel, CardWidget, IconWidget
)

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


# ==========================================
# 1. 核心数据解析逻辑 (Logic Layer)
# ==========================================

class VariableUtils:
    """处理变量类型判断、格式化和图标生成的工具类"""

    @staticmethod
    def is_image_file(obj):
        if isinstance(obj, str) and os.path.isfile(obj):
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
        """获取用于显示的简短字符串"""
        if obj is None:
            return "None"

        # 处理 Numpy 标量
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
            # [修改部分] 优先判断是否为图片，其次判断是否为普通文件
            if VariableUtils.is_image_file(obj):
                return f"<Image File> {os.path.basename(obj)}"
            elif os.path.isfile(obj):  # <--- 新增逻辑：如果是存在的路径
                return f"<File> {obj}"

            return f"'{obj}'" if len(obj) < 50 else f"'{obj[:50]}...'"

        elif VariableUtils.is_pil_image(obj):
            return f"<PIL.Image> {obj.size} {obj.mode}"
        elif isinstance(obj, (list, tuple)):
            return f"<{type(obj).__name__}> len={len(obj)}"
        elif isinstance(obj, dict):
            return f"<dict> len={len(obj)}"
        elif hasattr(obj, 'shape'):
            return f"<{type(obj).__name__}> shape={obj.shape}"

        return str(obj)[:100]

    @staticmethod
    def get_type_name(obj):
        """获取简短的类型名称用于图标"""
        if obj is None: return "None"
        if isinstance(obj, bool): return "Bool"
        if isinstance(obj, int): return "Int"
        if isinstance(obj, float): return "Float"

        # [修改部分] 字符串类型细分
        if isinstance(obj, str):
            if VariableUtils.is_image_file(obj): return "Img"
            if os.path.isfile(obj): return "File"  # <--- 新增类型：File
            return "Str"

        if isinstance(obj, dict): return "Dict"
        if isinstance(obj, list): return "List"
        if isinstance(obj, tuple): return "Tuple"
        if VariableUtils.is_dataframe(obj): return "DF"
        if VariableUtils.is_pandas_series(obj): return "Ser"
        if hasattr(obj, 'shape'): return "Arr"
        if VariableUtils.is_pil_image(obj): return "Img"
        return "Obj"

    @staticmethod
    @lru_cache(maxsize=128)
    def generate_icon(type_name: str, dark_mode: bool) -> QIcon:
        """生成带背景色的类型图标 (缓存以提升性能)"""
        size = 28
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # 配色方案
        colors = {
            "Str": "#CE9178", "Int": "#B5CEA8", "Float": "#B5CEA8",
            "Bool": "#569CD6", "List": "#4EC9B0", "Dict": "#C586C0",
            "DF": "#FF9800", "Arr": "#4CAF50", "Img": "#E91E63",
            "File": "#DCDCAA",  # <--- 新增配色 (淡黄色/米色)
            "None": "#808080", "Obj": "#9CDCFE"
        }
        base_color = QColor(colors.get(type_name, "#9CDCFE"))

        # 绘制背景圆角矩形
        bg_rect = QRect(2, 6, size - 4, size - 12)
        painter.setPen(Qt.NoPen)
        painter.setBrush(base_color)
        painter.drawRoundedRect(bg_rect, 4, 4)

        # 绘制文字
        # File 类型背景较亮，如果是 File 类型且不是暗黑模式，或者暗黑模式下File色也较亮，这里简单处理
        # 统一使用黑白逻辑，或者对 File 特殊处理
        text_color = QColor("black") if (dark_mode and type_name == "File") or (
                    not dark_mode and type_name == "File") else (QColor("black") if dark_mode else QColor("white"))
        # 为保持一致性，还是使用原逻辑，但 File 可以稍微深一点
        painter.setPen(QColor("black") if dark_mode else QColor("white"))
        if type_name == "File":  # File 颜色较亮，始终用黑色字比较清楚
            painter.setPen(QColor("black"))

        font = QFont("Consolas", 8, QFont.Bold)
        painter.setFont(font)
        # 允许显示4个字符，以便显示 File
        painter.drawText(bg_rect, Qt.AlignCenter, type_name[:4])

        painter.end()
        return QIcon(pixmap)


# ==========================================
# 2. 视觉代理 (Visual Delegate)
# ==========================================

class VariableValueDelegate(QStyledItemDelegate):
    """
    负责'值'列的渲染，实现语法高亮效果。
    """

    def paint(self, painter, option, index):
        if index.column() != 1:
            super().paint(painter, option, index)
            return

        painter.save()

        # 获取数据
        raw_obj = index.data(Qt.UserRole)
        text = index.data(Qt.DisplayRole)

        # 字体
        painter.setFont(QFont("Consolas", 10))

        # 语法高亮颜色确定
        # 默认颜色
        text_color = QColor("#D4D4D4") if isDarkTheme() else QColor("#333333")

        if raw_obj is None:
            text_color = QColor("#569CD6")  # Blue
        elif isinstance(raw_obj, bool):
            text_color = QColor("#569CD6")  # Blue
        elif isinstance(raw_obj, (int, float)) or (hasattr(raw_obj, 'dtype') and np.isscalar(raw_obj)):
            text_color = QColor("#B5CEA8") if isDarkTheme() else QColor("#098658")  # Greenish
        elif isinstance(raw_obj, str):
            # [修改部分] 增加 File 类型的颜色高亮
            if os.path.isfile(raw_obj):
                text_color = QColor("#DCDCAA") if isDarkTheme() else QColor("#795E26")  # File color
            else:
                text_color = QColor("#CE9178") if isDarkTheme() else QColor("#A31515")  # String color
        elif hasattr(raw_obj, 'shape') or isinstance(raw_obj, (list, dict, tuple)):
            text_color = QColor("#C586C0")  # Purple

        # --- 修复点：使用 QStyle.State_Selected ---
        if option.state & QStyle.State_Selected:
            text_color = QColor("#FFFFFF")  # 选中时强制白色高亮

        painter.setPen(text_color)

        # 垂直居中绘制
        rect = option.rect
        text_rect = rect.adjusted(5, 0, -5, 0)  # Padding
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, text)

        painter.restore()


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
        # 深色半透明背景
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
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #444;" if isDarkTheme() else "color: #DDD;")
        self.content_layout.addWidget(line)

        # 内容区域 (动态替换)
        self.preview_widget = None

    def set_data(self, obj, name=""):
        self.title_label.setText(f"{name} ({type(obj).__name__})")

        # 清理旧内容
        if self.preview_widget:
            self.preview_widget.deleteLater()
            self.preview_widget = None

        # 根据类型决定显示内容
        if VariableUtils.is_image_file(obj) or VariableUtils.is_pil_image(obj):
            self.preview_widget = self._load_pixmap(obj)

        elif isinstance(obj, (pd.DataFrame, pd.Series)) if 'pd' in locals() else False:
            # DataFrame 显示简略信息
            text = str(obj.head(10)) + f"\n\nShape: {obj.shape}"
            self.preview_widget = TextEdit()
            self.preview_widget.setPlainText(text)
            self.preview_widget.setReadOnly(True)
            self.preview_widget.setFixedSize(500, 300)

        else:
            # 默认文本/结构显示
            text = str(obj)
            # if len(text) > 5000: text = text[:5000] + "\n... (truncated)"
            self.preview_widget = TextEdit()
            self.preview_widget.setPlainText(text)
            self.preview_widget.setReadOnly(True)
            self.preview_widget.setFixedSize(500, 300)
            self.preview_widget.setFont(QFont("Consolas", 10))

        self.content_layout.addWidget(self.preview_widget)
        self.adjustSize()

    def _load_pixmap(self, obj):
        pixmap = None
        if isinstance(obj, str):
            pixmap = QPixmap(obj)
        elif VariableUtils.is_pil_image(obj):
            try:
                img = obj
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGBA' if 'A' in img.mode else 'RGB')
                data = img.tobytes()
                qim = QImage(data, img.width, img.height,
                             QImage.Format_RGBA8888 if img.mode == 'RGBA' else QImage.Format_RGB8888)
                pixmap = QPixmap.fromImage(qim)
            except Exception:
                pass

        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(500, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            img_label = QLabel()
            img_label.setPixmap(scaled)
            img_label.setAlignment(Qt.AlignCenter)
            img_label.setStyleSheet("background: #1e1e1e; border-radius: 6px; padding: 8px;")
            return img_label
        else:
            label = BodyLabel("⚠️ 图像加载失败", self)
            label.setStyleSheet("color: #ff6b6b;")
            return label

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
        if x < screen_geo.left():
            # 左侧不够，显示在右侧
            x = rect_global.right() + 10

        # 垂直居中但防止溢出
        y = rect_global.top()
        if y + h > screen_geo.bottom():
            y = screen_geo.bottom() - h

        self.move(x, y)
        self.show()
        self.setFocus()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()


# ==========================================
# 4. 主树控件 (Main Tree Widget)
# ==========================================

class VariableTreeWidget(TreeWidget):
    """
    优化的变量展示树：
    1. 使用 Fluent TreeWidget
    2. 支持懒加载
    3. 支持语法高亮 Delegate
    4. 优雅的菜单和弹窗
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Name", "Value"])

        # 样式与配置
        self.setAlternatingRowColors(False)  # Fluent UI 不需要交替色
        self.setIconSize(QSize(20, 20))
        self.setIndentation(15)
        self.setExpandsOnDoubleClick(True)
        self.setAnimated(True)

        # 列宽设置
        self.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.header().setStretchLastSection(False)  # 允许 Value 列拉伸

        # 设置代理
        self.setItemDelegate(VariableValueDelegate(self))

        # 信号
        self.itemExpanded.connect(self.on_item_expanded)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        # 内部样式覆盖 (使字体一致)
        self.setStyleSheet("""
            QTreeWidget {
                background-color: #2d2d30;
                color: #d4d4d4;
                border: none;
                font-family: Consolas, monospace;
                font-size: 11px;
            }
            QTreeWidget::item {
                padding: 2px;
            }
            QTreeWidget::item:hover {
                background-color: #3e3e42;
            }
            QTreeWidget::item:selected {
                background-color: #37373d;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #d4d4d4;
                padding: 4px;
                border: none;
            }
        """)

    def set_data(self, data: Any, root_name: str = "Variables"):
        """设置根数据"""
        self.clear()

        # 构建根节点
        root_val_str = VariableUtils.get_formatted_value(data)
        root_item = QTreeWidgetItem([root_name, root_val_str])

        # 设置元数据
        self._set_node_metadata(root_item, data)

        self.addTopLevelItem(root_item)
        root_item.setExpanded(True)  # 默认展开第一层

    def _set_node_metadata(self, item: QTreeWidgetItem, obj: Any):
        """设置节点的数据、图标和子节点标识"""
        item.setData(1, Qt.UserRole, obj)  # 将原始对象存在第二列的 UserRole
        item.setData(1, Qt.DisplayRole, VariableUtils.get_formatted_value(obj))

        type_name = VariableUtils.get_type_name(obj)
        item.setIcon(0, VariableUtils.generate_icon(type_name, isDarkTheme()))

        # 判断是否有子节点 (用于懒加载)
        has_children = False
        if isinstance(obj, (dict, list, tuple)):
            has_children = len(obj) > 0
        elif hasattr(obj, 'shape') and hasattr(obj, 'dtype'):  # Numpy
            has_children = obj.size > 0 and obj.ndim > 0
        elif VariableUtils.is_dataframe(obj) or VariableUtils.is_pandas_series(obj):
            has_children = not obj.empty
        elif hasattr(obj, '__dict__'):
            has_children = True

        if has_children:
            # 添加一个占位符子节点，触发展开信号
            item.addChild(QTreeWidgetItem(["Loading...", ""]))
            item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)

    def on_item_expanded(self, item: QTreeWidgetItem):
        """懒加载逻辑"""
        # 如果第一个子节点是 Loading...，则说明从未加载过
        if item.childCount() == 1 and item.child(0).text(0) == "Loading...":
            item.removeChild(item.child(0))

            obj = item.data(1, Qt.UserRole)
            self._load_children(item, obj)

    def _load_children(self, parent_item: QTreeWidgetItem, obj: Any):
        """根据对象类型加载子节点"""
        try:
            children = []

            if isinstance(obj, dict):
                for k, v in list(obj.items())[:MAX_DICT_KEYS]:
                    child = QTreeWidgetItem([str(k), ""])
                    self._set_node_metadata(child, v)
                    children.append(child)

            elif isinstance(obj, (list, tuple)):
                for i, v in enumerate(obj[:MAX_LIST_ITEMS]):
                    child = QTreeWidgetItem([str(i), ""])
                    self._set_node_metadata(child, v)
                    children.append(child)

            elif VariableUtils.is_pandas_series(obj):
                for i in range(min(len(obj), MAX_LIST_ITEMS)):
                    idx = obj.index[i]
                    val = obj.iloc[i]
                    child = QTreeWidgetItem([str(idx), ""])
                    self._set_node_metadata(child, val)
                    children.append(child)

            elif VariableUtils.is_dataframe(obj):
                for col in obj.columns:
                    child = QTreeWidgetItem([str(col), ""])
                    self._set_node_metadata(child, obj[col])
                    children.append(child)

            elif hasattr(obj, 'shape') and hasattr(obj, 'dtype'):  # Numpy array
                # 仅展开第一维
                for i in range(min(obj.shape[0], MAX_LIST_ITEMS)):
                    child = QTreeWidgetItem([f"[{i}]", ""])
                    self._set_node_metadata(child, obj[i])
                    children.append(child)

            elif hasattr(obj, '__dict__'):
                for k, v in obj.__dict__.items():
                    if not k.startswith('__'):
                        child = QTreeWidgetItem([k, ""])
                        self._set_node_metadata(child, v)
                        children.append(child)

            parent_item.addChildren(children)

        except Exception as e:
            err_item = QTreeWidgetItem(["<Error>", str(e)])
            err_item.setForeground(0, QBrush(Qt.red))
            parent_item.addChild(err_item)

    def show_context_menu(self, pos: QPoint):
        item = self.itemAt(pos)
        if not item: return

        obj = item.data(1, Qt.UserRole)
        name = item.text(0)

        menu = RoundMenu(parent=self)

        # 1. 详情预览
        menu.addAction(Action(FIF.INFO, "查看详情", triggered=lambda: self._show_detail_popup(item, obj)))

        # 2. 复制
        menu.addAction(Action(FIF.COPY, "复制值", triggered=lambda: QApplication.clipboard().setText(str(obj))))

        # 3. 高级预览 (如果支持)
        if HAS_SPYDER:
            if VariableUtils.is_dataframe(obj) or VariableUtils.is_pandas_series(obj):
                menu.addAction(
                    Action(get_icon("表格"), "在表格中打开", triggered=lambda: self._open_spyder_editor(obj, name)))
            elif hasattr(obj, 'shape') and hasattr(obj, 'dtype'):
                menu.addAction(
                    Action(get_icon("数组"), "查看数组", triggered=lambda: self._open_array_editor(obj, name)))

        # 4. 文件操作
        if isinstance(obj, str) and os.path.isfile(obj):
            menu.addAction(Action(FIF.FOLDER, "打开所在文件夹", triggered=lambda: self._open_explorer(obj)))

        menu.exec_(self.viewport().mapToGlobal(pos))

    def _show_detail_popup(self, item, obj):
        # 延迟导入以避免循环依赖或在初始化时卡顿
        self._popup = VariableDetailPopup(self)
        self._popup.set_data(obj, item.text(0))

        # 计算位置
        rect = self.visualItemRect(item)
        global_rect = QRect(self.viewport().mapToGlobal(rect.topLeft()), rect.size())
        self._popup.show_near(global_rect)

    def _open_explorer(self, path):
        if sys.platform == "win32":
            subprocess.run(["explorer", "/select,", path])
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", path])
        else:
            subprocess.run(["xdg-open", os.path.dirname(path)])

    # === Spyder Integration Helpers ===
    def _open_spyder_editor(self, data, title):
        if not HAS_SPYDER: return
        if VariableUtils.is_pandas_series(data):
            data = data.to_frame()
        editor = DataFrameEditor(parent=self, readonly=True)
        if editor.setup_and_check(data, title=title):
            editor.exec_()

    def _open_array_editor(self, data, title):
        if not HAS_SPYDER: return
        editor = ArrayEditor(parent=self)
        if editor.setup_and_check(data, title=title):
            editor.exec_()


# ==========================================
# 5. 测试主程序
# ==========================================

if __name__ == "__main__":
    from qfluentwidgets import setTheme, Theme

    # 启用高分屏支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)

    app = QApplication(sys.argv)

    # 设置主题 (Auto, Dark, Light)
    setTheme(Theme.DARK)

    # 测试数据构造
    data = {
        "Config": {
            "version": 1.0,
            "debug": True,
            "paths": ["/usr/bin", "/etc/config"],
            "real_file": __file__  # <--- 测试用：当前脚本路径，应显示为 File
        },
        "Statistics": {
            "score": 98.5,
            "count": 1024,
            "history": [10, 20, 30, 40, 50] * 5
        },
        "Image": "test.png",  # 假路径演示
        "Complex List": [{"id": i, "val": i * 2} for i in range(5)],
    }

    # 尝试加入 Pandas/Numpy 数据
    try:
        import pandas as pd

        df = pd.DataFrame(np.random.randn(100, 4), columns=list('ABCD'))
        data["DataFrame"] = df
        data["Numpy Array"] = np.random.rand(50, 50)
    except:
        pass

    w = QWidget()
    w.setStyleSheet("background-color: #202020;")  # 模拟深色背景容器
    layout = QVBoxLayout(w)
    layout.setContentsMargins(10, 10, 10, 10)

    # 添加标题
    lbl = BodyLabel("Variable Explorer (Optimized)")
    lbl.setStyleSheet("color: white; font-size: 16px; margin-bottom: 5px;")
    layout.addWidget(lbl)

    tree = VariableTreeWidget(w)
    tree.set_data(data, "root")

    # 模拟外部容器样式
    tree_container = QFrame()
    tree_container.setStyleSheet("""
        QFrame {
            border: 1px solid #3e3e42;
            border-radius: 8px;
            background-color: #2d2d30;
        }
    """)
    tc_layout = QVBoxLayout(tree_container)
    tc_layout.setContentsMargins(0, 5, 0, 5)
    tc_layout.addWidget(tree)

    layout.addWidget(tree_container)

    w.resize(600, 800)
    w.show()

    sys.exit(app.exec_())