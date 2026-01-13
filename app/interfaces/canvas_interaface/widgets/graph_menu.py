# -*- coding: utf-8 -*-
import time
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from app.utils.utils import get_pinyin_search_keys

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
            # 悬浮时的背景色（稍微浅一点的灰色）
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
        # 稍微收缩矩形，产生间距感
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
        return QtCore.QSize(0, 40)  # 稍微增加高度，点击感更好


class CustomGraphMenu(QtWidgets.QWidget):
    """自定义画布菜单"""

    def __init__(self, graph, left_panel, parent):
        super(CustomGraphMenu, self).__init__(parent)
        self._graph = graph
        self._left_panel = left_panel
        self.parent = parent
        self._cached_data = []  # 核心：缓存所有节点数据

        # 1. 窗口属性设置
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 2. 布局与样式
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        self.container = QtWidgets.QFrame()
        self.container.setObjectName("SearchContainer")
        self.container.setStyleSheet("""
            #SearchContainer {
                background: #252526;
                border: 1px solid #454545;
                border-radius: 8px;
            }
        """)
        # 添加阴影效果
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(5)
        shadow.setColor(QtGui.QColor(0, 0, 0, 150))
        self.container.setGraphicsEffect(shadow)

        container_layout = QtWidgets.QVBoxLayout(self.container)
        container_layout.setContentsMargins(8, 8, 8, 8)
        container_layout.setSpacing(8)

        # 搜索框
        self.search_line = QtWidgets.QLineEdit()
        self.search_line.setPlaceholderText("🔍 输入搜索 (拼音/简称/类别)...")
        self.search_line.setStyleSheet("""
            QLineEdit {
                background: #323233; color: #FFFFFF;
                border: 1px solid #3C3C3C; border-radius: 4px;
                padding: 8px 12px; font-size: 14px; selection-background-color: #007ACC;
            }
            QLineEdit:focus { border: 1px solid #007ACC; }
        """)
        container_layout.addWidget(self.search_line)

        # 列表
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setItemDelegate(NodeItemDelegate())
        self.list_widget.setMouseTracking(True)
        # 确保鼠标移动时立即重绘项
        self.list_widget.setAttribute(QtCore.Qt.WA_Hover)
        self.list_widget.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background: transparent; border: none; outline: none;
            }
        """)
        # 自定义滚动条
        self.list_widget.verticalScrollBar().setStyleSheet("""
            QScrollBar:vertical { background: transparent; width: 8px; }
            QScrollBar::handle:vertical { background: #4F4F4F; border-radius: 4px; min-height: 20px; }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0px; }
        """)
        container_layout.addWidget(self.list_widget)

        self.main_layout.addWidget(self.container)

        # 事件绑定
        self.search_line.textChanged.connect(self.filter_list)
        self.list_widget.itemClicked.connect(self.on_item_confirmed)
        self.search_line.returnPressed.connect(self.on_return_pressed)

        self.setFixedSize(420, 450)
        self.search_line.installEventFilter(self)

    def set_category_filter(self, categories):
        self._selected_categories = set(categories)
        # 立即更新缓存并重新填充UI，保证下次打开菜单时是最新的
        self.update_cache()
        self.populate_ui()

    def update_cache(self):
        """仅在节点定义发生变化或初始化时调用一次，大幅提升响应速度"""
        self._cached_data = []
        tree_widget = self._left_panel.draggable_tree.tree
        root = tree_widget.invisibleRootItem()

        # 遍历节点
        for i in range(root.childCount()):
            cat_item = root.child(i)
            cat_name = cat_item.text(0)
            cat_pinyin = get_pinyin_search_keys(cat_name)

            for j in range(cat_item.childCount()):
                node_item = cat_item.child(j)
                node_name = node_item.text(0)
                node_id = node_item.data(0, Qt.UserRole + 1)
                node_type = self._graph.parent().node_type_map.get(node_id)  # 这里的映射路径根据你实际调整

                py_keys = get_pinyin_search_keys(node_name)

                self._cached_data.append({
                    "type": "node",
                    "id": node_type,
                    "name": node_name,
                    "category": cat_name,
                    "search_keys": f"{node_name} {cat_name} {node_id} {py_keys} {cat_pinyin}".lower()
                })

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
        """根据缓存填充 UI"""
        self.list_widget.clear()
        self.list_widget.setUpdatesEnabled(False)  # 批量更新优化
        for data in self._cached_data:
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
            # 简单的匹配逻辑
            is_visible = search_text in data["search_keys"]
            item.setHidden(not is_visible)
            if is_visible and first_visible == -1:
                first_visible = i

        self.list_widget.setUpdatesEnabled(True)
        if first_visible != -1:
            self.list_widget.setCurrentRow(first_visible)

    def show_at_cursor(self, pos):
        # 1. 如果缓存为空则更新（通常只在第一次或刷新时执行）
        if not self._cached_data:
            self.update_cache()
            self.populate_ui()

        # 2. 坐标转换
        viewer = self._graph.viewer()
        scene_viewer = viewer.get_scene_viewer() if hasattr(viewer, 'get_scene_viewer') else viewer
        self._spawn_pos = scene_viewer.mapFromGlobal(pos)

        # 3. 重置 UI 状态
        self.search_line.setText("")
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setHidden(False)
        self.list_widget.setCurrentRow(0)

        # 4. 窗口定位
        self.move(pos - QtCore.QPoint(20, 20))  # 稍微偏移让光标处于搜索框内
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
                # 这里根据你实际的 create_node 签名修改，有些需要 node_type 字符串
                node = self._graph.create_node(data["id"], pos=[scene_pos.x(), scene_pos.y()])
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
                if event.key() == Qt.Key_Down:
                    self.list_widget.setFocus()
                    self.list_widget.setCurrentRow(self.list_widget.currentRow())
                    return True
                elif event.key() == Qt.Key_Up:
                    # 如果在最顶端按上，可以保持在搜索框
                    if self.list_widget.currentRow() <= 0:
                        return False
                    self.list_widget.setFocus()
                    return True
        return super(CustomGraphMenu, self).eventFilter(source, event)