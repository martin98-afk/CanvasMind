# -*- coding: utf-8 -*-
import time
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
from qfluentwidgets import TransparentToolButton, FluentIcon

from app.utils.utils import get_pinyin_search_keys
from app.widgets.basic_widget.style_sheet import StyleSheet

try:
    from pypinyin import pinyin, Style
except ImportError:
    pinyin = None


class NodeItemDelegate(QtWidgets.QStyledItemDelegate):
    """优化后的绘制器：支持平滑悬浮效果"""

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        data = index.data(Qt.UserRole)
        display_text = index.data(Qt.DisplayRole)
        category = data.get("category", "")

        # 核心逻辑：判断当前状态
        is_selected = option.state & QtWidgets.QStyle.State_Selected
        is_hovered = option.state & QtWidgets.QStyle.State_MouseOver

        # 颜色配置
        if is_selected:
            bg_color = QtGui.QColor("#007ACC")
            text_color = QtGui.QColor("#FFFFFF")
            sub_text_color = QtGui.QColor("#A0CFFF")
        elif is_hovered:
            # 悬浮时的背景色
            bg_color = QtGui.QColor("#3E3E42")
            text_color = QtGui.QColor("#FFFFFF")
            sub_text_color = QtGui.QColor("#999999")
        else:
            bg_color = QtGui.QColor("transparent")
            text_color = QtGui.QColor("#CCCCCC")
            sub_text_color = QtGui.QColor("#666666")

        # 绘制圆角背景
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg_color)
        margin = 4
        rect = option.rect.adjusted(margin, 2, -margin, -2)
        painter.drawRoundedRect(rect, 6, 6)

        # 绘制主文字（节点名）
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True if is_selected else False)
        painter.setFont(font)
        painter.setPen(text_color)

        # 计算文字绘制区域
        title_rect = option.rect.adjusted(15, 0, -120, 0)
        painter.drawText(title_rect, Qt.AlignVCenter | Qt.AlignLeft, display_text)

        # 绘制副文字（类别）
        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(sub_text_color)

        cat_rect = option.rect.adjusted(10, 0, -15, 0)
        painter.drawText(cat_rect, Qt.AlignVCenter | Qt.AlignRight, category)

        painter.restore()

    def sizeHint(self, option, index):
        return QtCore.QSize(0, 40)


class CustomGraphMenu(QtWidgets.QWidget):
    """自定义画布菜单"""

    def __init__(self, graph, left_panel, parent):
        super(CustomGraphMenu, self).__init__(parent)
        self._graph = graph
        self._left_panel = left_panel
        self.parent = parent
        self._cached_data = []
        self._selected_categories = set()

        # 1. 窗口属性
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 2. 主布局
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        self.container = QtWidgets.QFrame()
        self.container.setObjectName("SearchContainer")
        self.container.setStyleSheet("""
            #SearchContainer { background: #252526; border: 1px solid #454545; border-radius: 8px; }
        """)

        # 阴影
        self.shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(20)
        self.shadow.setXOffset(0)
        self.shadow.setYOffset(5)
        self.shadow.setColor(QtGui.QColor(0, 0, 0, 150))
        self.container.setGraphicsEffect(self.shadow)

        # 容器布局
        self.container_layout = QtWidgets.QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(8, 8, 8, 8)
        self.container_layout.setSpacing(8)

        # --- 3. 搜索栏 Header ---
        self.header_widget = QtWidgets.QWidget()
        self.header_layout = QtWidgets.QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setSpacing(2)

        self.filter_button = TransparentToolButton(FluentIcon.FILTER, self)
        self.filter_button.clicked.connect(self.show_category_filter)

        self.search_line = QtWidgets.QLineEdit()
        self.search_line.setPlaceholderText("🔍 输入搜索 (拼音/简称/类别)...")
        self.search_line.setStyleSheet("""
            QLineEdit {
                background: #323233; color: #FFFFFF;
                border: 1px solid #3C3C3C; border-radius: 4px;
                padding: 8px 12px; font-size: 14px;
            }
            QLineEdit:focus { border: 1px solid #007ACC; }
        """)

        self.header_layout.addWidget(self.filter_button)
        self.header_layout.addWidget(self.search_line)

        # --- 4. 列表组件 ---
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setItemDelegate(NodeItemDelegate())
        self.list_widget.setMouseTracking(True)
        self.list_widget.setAttribute(QtCore.Qt.WA_Hover)
        self.list_widget.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.list_widget.setStyleSheet("QListWidget { background: transparent; border: none; outline: none; }")
        StyleSheet.QLIST.apply(self.list_widget)

        # 默认布局
        self.container_layout.addWidget(self.header_widget)
        self.container_layout.addWidget(self.list_widget)

        self.main_layout.addWidget(self.container)

        # 事件绑定
        self.search_line.textChanged.connect(self.filter_list)
        self.list_widget.itemClicked.connect(self.on_item_confirmed)
        self.search_line.returnPressed.connect(self.on_return_pressed)

        self.setFixedSize(420, 450)
        self.search_line.installEventFilter(self)

    def show_category_filter(self):
        pos = self.filter_button.mapToGlobal(self.filter_button.rect().bottomLeft())
        self._left_panel.draggable_tree.category_filter_dialog.show_at(pos)

    def set_category_filter(self, categories):
        self._selected_categories = set(categories)
        self.update_cache()
        self.populate_ui()

    def update_cache(self):
        """递归遍历所有层级，并确保使用正确的 node_type 标识符"""
        self._cached_data = []
        tree_widget = self._left_panel.draggable_tree.tree
        root = tree_widget.invisibleRootItem()

        def collect_nodes(parent_item):
            for i in range(parent_item.childCount()):
                item = parent_item.child(i)
                node_id = item.data(0, Qt.UserRole + 1)  # 这是 full_path

                if node_id:  # 说明是真正的组件节点
                    # --- 完全照搬你原来的建点逻辑来获取 ID ---
                    node_type = self._graph.parent().node_type_map.get(node_id)

                    # 递归获取完整分类路径字符串
                    path_parts = []
                    p = item.parent()
                    while p and p != root:
                        path_parts.insert(0, p.text(0))
                        p = p.parent()
                    cat_full_str = "/".join(path_parts)

                    node_name = item.text(0).replace("★ ", "")
                    py_keys = get_pinyin_search_keys(node_name)
                    cat_py = get_pinyin_search_keys(cat_full_str)

                    self._cached_data.append({
                        "type": "node",
                        "id": node_type,  # <--- 存入真正的 node_type
                        "name": node_name,
                        "category": cat_full_str,
                        "search_keys": f"{node_name} {cat_full_str} {node_id} {py_keys} {cat_py}".lower()
                    })
                else:  # 说明是中间目录，继续递归
                    collect_nodes(item)

        collect_nodes(root)

        # 遍历模板
        if hasattr(self._left_panel.template_container, 'get_templates'):
            for t_name in self._left_panel.template_container.get_templates():
                self._cached_data.append({
                    "type": "template",
                    "id": t_name,
                    "name": t_name,
                    "category": "Template 模板",
                    "search_keys": f"{t_name} 模板 {get_pinyin_search_keys(t_name)}".lower()
                })

    def populate_ui(self):
        self.list_widget.clear()
        self.list_widget.setUpdatesEnabled(False)
        for data in self._cached_data:
            if self._selected_categories:
                root_cat = data["category"].split("/")[0]
                if root_cat not in self._selected_categories:
                    continue
            item = QtWidgets.QListWidgetItem(data["name"])
            item.setData(Qt.UserRole, data)
            self.list_widget.addItem(item)
        self.list_widget.setUpdatesEnabled(True)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def filter_list(self, text):
        search_text = text.lower().strip()
        self.list_widget.setUpdatesEnabled(False)
        first_visible = -1
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            data = item.data(Qt.UserRole)
            is_visible = search_text in data["search_keys"]
            item.setHidden(not is_visible)
            if is_visible and first_visible == -1:
                first_visible = i
        self.list_widget.setUpdatesEnabled(True)
        if first_visible != -1:
            self.list_widget.setCurrentRow(first_visible)

    def show_at_cursor(self, pos):
        self.update_cache()
        self.populate_ui()
        viewer = self._graph.viewer()
        scene_viewer = viewer.get_scene_viewer() if hasattr(viewer, 'get_scene_viewer') else viewer
        self._spawn_pos = scene_viewer.mapFromGlobal(pos)
        self.search_line.setText("")
        self.list_widget.setCurrentRow(0)

        menu_w, menu_h = self.width(), self.height()
        screen_rect = QtWidgets.QApplication.desktop().availableGeometry(pos)
        target_x, target_y = pos.x() - 20, pos.y() - 20

        if target_y + menu_h > screen_rect.bottom():
            target_y = pos.y() - menu_h + 20
            self.shadow.setYOffset(-5)
            self.container_layout.insertWidget(0, self.list_widget)
            self.container_layout.insertWidget(1, self.header_widget)
        else:
            self.shadow.setYOffset(5)
            self.container_layout.insertWidget(0, self.header_widget)
            self.container_layout.insertWidget(1, self.list_widget)

        target_x = max(screen_rect.left() + 5, min(target_x, screen_rect.right() - menu_w - 5))
        self.move(QtCore.QPoint(target_x, target_y))
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_line.setFocus()

    def on_item_confirmed(self, item):
        data = item.data(Qt.UserRole)
        viewer = self._graph.viewer()
        scene_viewer = viewer.get_scene_viewer() if hasattr(viewer, 'get_scene_viewer') else viewer
        scene_pos = scene_viewer.mapToScene(self._spawn_pos)

        try:
            if data["type"] == "node":
                self._graph.begin_undo("Create Node")
                # 这里 data["id"] 现在是真正的 node_type 字符串了
                self._graph.create_node(data["id"], pos=[scene_pos.x(), scene_pos.y()])
                self.parent.on_selection_changed()
                self._graph.end_undo()
            elif data["type"] == "template":
                self._left_panel.template_container.load_template(
                    data["id"], pos=[scene_pos.x(), scene_pos.y()]
                )
        except Exception as e:
            print(f"Error creating node: {e}")
        self.close()

    def on_return_pressed(self):
        current_item = self.list_widget.currentItem()
        if current_item and not current_item.isHidden():
            self.on_item_confirmed(current_item)

    def eventFilter(self, source, event):
        if event.type() == QtCore.QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.close()
                return True
            if source is self.search_line:
                is_bottom = self.container_layout.indexOf(self.header_widget) == 1
                if event.key() == Qt.Key_Down:
                    if is_bottom: return False
                    self.list_widget.setFocus();
                    return True
                elif event.key() == Qt.Key_Up:
                    if not is_bottom: return False
                    self.list_widget.setFocus();
                    return True
        return super(CustomGraphMenu, self).eventFilter(source, event)