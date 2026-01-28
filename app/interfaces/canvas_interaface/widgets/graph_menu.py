# -- coding: utf-8 --
import time
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QTimer
from qfluentwidgets import TransparentToolButton, FluentIcon

from app.utils.utils import get_pinyin_search_keys, get_icon
from app.widgets.basic_widget.style_sheet import StyleSheet


class MenuMode:
    CREATE = 0
    NAVIGATE = 1


class NodeItemDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        data = index.data(Qt.UserRole)
        if not data or data.get("_is_placeholder", False):
            # 占位 item：不绘制任何内容
            return

        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        display_text = index.data(Qt.DisplayRole)
        category = data.get("category", "")
        item_type = data.get("type", "")

        is_selected = option.state & QtWidgets.QStyle.State_Selected
        is_hovered = option.state & QtWidgets.QStyle.State_MouseOver

        if is_selected:
            bg_color = QtGui.QColor("#007ACC")
            text_color = QtGui.QColor("#FFFFFF")
            sub_text_color = QtGui.QColor("#A0CFFF")
        elif is_hovered:
            bg_color = QtGui.QColor(255, 255, 255, 20)
            text_color = QtGui.QColor("#FFFFFF")
            sub_text_color = QtGui.QColor("#999999")
        else:
            bg_color = QtGui.QColor("transparent")
            text_color = QtGui.QColor("#CCCCCC")
            sub_text_color = QtGui.QColor("#666666")

        painter.setPen(Qt.NoPen)
        painter.setBrush(bg_color)
        rect = option.rect.adjusted(4, 2, -4, -2)
        painter.drawRoundedRect(rect, 8, 8)

        if is_selected and item_type == "instance":
            painter.setBrush(QtGui.QColor("#4EC9B0"))
            painter.drawRoundedRect(rect.left(), rect.top() + 8, 3, rect.height() - 16, 1, 1)

        font = painter.font()
        font.setPointSize(10)
        font.setBold(is_selected)
        painter.setFont(font)
        painter.setPen(text_color)
        title_rect = option.rect.adjusted(15, 0, -140, 0)
        painter.drawText(title_rect, Qt.AlignVCenter | Qt.AlignLeft, display_text)

        font.setPointSize(8)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(sub_text_color)
        cat_rect = option.rect.adjusted(10, 0, -15, 0)
        painter.drawText(cat_rect, Qt.AlignVCenter | Qt.AlignRight, category)

        painter.restore()

    def sizeHint(self, option, index):
        return QtCore.QSize(0, 42)


class CustomGraphMenu(QtWidgets.QWidget):
    def __init__(self, graph, left_panel, parent):
        super(CustomGraphMenu, self).__init__(parent)
        self._graph = graph
        self._left_panel = left_panel
        self.parent = parent
        self._cached_data = []
        self._selected_categories = set()
        self._current_mode = MenuMode.CREATE
        self._is_upward_mode = False
        self._spawn_pos = QtCore.QPoint(0, 0)
        self._visible_items = []  # 存储过滤后的有效数据

        # 窗口属性
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        self.container = QtWidgets.QFrame()
        self.container.setObjectName("SearchContainer")
        self.container.setStyleSheet("""
            #SearchContainer { 
                background: #252526; 
                border: 1px solid #454545; 
                border-radius: 12px; 
            }
        """)

        self.shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(25)
        self.shadow.setXOffset(0)
        self.shadow.setYOffset(8)
        self.shadow.setColor(QtGui.QColor(0, 0, 0, 180))
        self.container.setGraphicsEffect(self.shadow)

        self.container_layout = QtWidgets.QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(10, 10, 10, 10)
        self.container_layout.setSpacing(8)

        # Header
        self.header_widget = QtWidgets.QWidget()
        self.header_layout = QtWidgets.QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setSpacing(6)

        self.filter_button = TransparentToolButton(FluentIcon.FILTER, self)
        self.filter_button.clicked.connect(self.show_category_filter)

        self.mode_button = TransparentToolButton(get_icon("节点库"), self)
        self.mode_button.setToolTip("切换搜索模式 (Tab)")
        self.mode_button.clicked.connect(self.toggle_mode)

        self.search_line = QtWidgets.QLineEdit()
        self.search_line.setPlaceholderText("🔍 搜索库节点...")
        self.search_line.setStyleSheet("""
            QLineEdit {
                background: #323233; color: #FFFFFF;
                border: 1px solid #3C3C3C; border-radius: 6px;
                padding: 8px 12px; font-size: 13px;
            }
            QLineEdit:focus { border: 1px solid #007ACC; background: #3c3c3c; }
        """)

        self.header_layout.addWidget(self.mode_button)
        self.header_layout.addWidget(self.filter_button)
        self.header_layout.addWidget(self.search_line)

        # ListWidget（恢复使用）
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setItemDelegate(NodeItemDelegate())
        self.list_widget.setMouseTracking(True)
        self.list_widget.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        StyleSheet.QLIST.apply(self.list_widget)

        self.container_layout.addWidget(self.header_widget)
        self.container_layout.addWidget(self.list_widget)
        self.main_layout.addWidget(self.container)

        self.search_line.textChanged.connect(self.filter_list)
        self.list_widget.itemClicked.connect(self.on_item_confirmed)
        self.search_line.returnPressed.connect(self.on_return_pressed)
        self.search_line.installEventFilter(self)

        self.setFixedSize(440, 480)

    def toggle_mode(self):
        self._current_mode = MenuMode.NAVIGATE if self._current_mode == MenuMode.CREATE else MenuMode.CREATE
        if self._current_mode == MenuMode.NAVIGATE:
            self.search_line.setPlaceholderText("📍 定位当前图中节点...")
            self.filter_button.setEnabled(False)
            self.mode_button.setIcon(get_icon("location"))
        else:
            self.search_line.setPlaceholderText("🔍 搜索库节点...")
            self.filter_button.setEnabled(True)
            self.mode_button.setIcon(get_icon("节点库"))
        self.update_cache()
        self.populate_ui()
        self.search_line.setText("")
        self.search_line.setFocus()

    def update_cache(self):
        if self._current_mode == MenuMode.CREATE:
            self._update_create_cache()
        else:
            self._update_navigate_cache()

    def _update_navigate_cache(self):
        self._cached_data = []
        all_nodes = self._graph.all_nodes()
        for node in all_nodes:
            name = node.name()
            node_type = "/".join(getattr(node, 'FULL_PATH', "Node").split("/")[:-1])
            py_keys = get_pinyin_search_keys(name)
            self._cached_data.append({
                "type": "instance",
                "node_ptr": node,
                "name": name,
                "category": f"{node_type}",
                "search_keys": f"{name} {node_type} {py_keys}".lower()
            })

    def _update_create_cache(self):
        self._cached_data = []
        tree_widget = self._left_panel.draggable_tree.tree
        root = tree_widget.invisibleRootItem()
        def collect_nodes(parent_item):
            for i in range(parent_item.childCount()):
                item = parent_item.child(i)
                node_id = item.data(0, Qt.UserRole + 1)
                if node_id:
                    node_type = self._graph.parent().node_type_map.get(node_id)
                    path_parts = []
                    p = item.parent()
                    while p and p != root:
                        path_parts.insert(0, p.text(0))
                        p = p.parent()
                    cat_full_str = "/".join(path_parts)
                    node_name = item.text(0).replace("★ ", "")
                    py_keys = get_pinyin_search_keys(node_name)
                    self._cached_data.append({
                        "type": "node",
                        "id": node_type,
                        "name": node_name,
                        "category": cat_full_str,
                        "search_keys": f"{node_name} {cat_full_str} {node_id} {py_keys}".lower()
                    })
                else:
                    collect_nodes(item)
        collect_nodes(root)

    def _get_max_visible_items(self):
        # 列表区域高度 ≈ 480 - header(≈40) - margins(20) - spacing(8) ≈ 412px
        # 每项 42px → 最多 9~10 项
        return 9

    def populate_ui(self):
        # 先过滤
        self._visible_items = []
        for data in self._cached_data:
            if self._current_mode == MenuMode.CREATE and self._selected_categories:
                root_cat = data["category"].split("/")[0]
                if root_cat not in self._selected_categories:
                    continue
            self._visible_items.append(data)

        self._update_list_widget()

    def _update_list_widget(self):
        self.list_widget.clear()
        items_to_show = self._visible_items.copy()

        if self._is_upward_mode:
            max_items = self._get_max_visible_items()
            actual_count = len(items_to_show)
            if actual_count < max_items:
                placeholder_count = max_items - actual_count
                # 插入占位 item（不可见、不可交互）
                for _ in range(placeholder_count):
                    placeholder = QtWidgets.QListWidgetItem()
                    placeholder.setData(Qt.UserRole, {"_is_placeholder": True})
                    self.list_widget.addItem(placeholder)

        # 添加真实 item
        for data in items_to_show:
            item = QtWidgets.QListWidgetItem(data["name"])
            item.setData(Qt.UserRole, data)
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            # 向下模式：选中第一个
            # 向上模式：选中第一个真实 item（跳过占位）
            first_real_index = 0
            if self._is_upward_mode:
                first_real_index = max(0, self.list_widget.count() - len(self._visible_items))
            self.list_widget.setCurrentRow(first_real_index)

    def set_category_filter(self, categories):
        self._selected_categories = set(categories)
        if self._current_mode == MenuMode.CREATE:
            self.update_cache()
            self.populate_ui()

    def set_graph(self, graph):
        self._graph = graph

    def filter_list(self, text):
        search_text = text.lower().strip()
        self._visible_items = []
        for data in self._cached_data:
            if self._current_mode == MenuMode.CREATE and self._selected_categories:
                root_cat = data["category"].split("/")[0]
                if root_cat not in self._selected_categories:
                    continue
            if search_text in data["search_keys"]:
                self._visible_items.append(data)
        self._update_list_widget()

    def on_item_confirmed(self, item):
        data = item.data(Qt.UserRole)
        if not data or data.get("_is_placeholder"):
            return  # 忽略占位项

        viewer = self._graph.viewer()
        if self._current_mode == MenuMode.CREATE:
            scene_viewer = viewer.get_scene_viewer() if hasattr(viewer, 'get_scene_viewer') else viewer
            scene_pos = scene_viewer.mapToScene(self._spawn_pos)
            self._graph.begin_undo("Create Node")
            new_node = self._graph.create_node(data["id"], pos=[scene_pos.x(), scene_pos.y()])
            # 处理自动连接逻辑，从节点端口拉出连线松开后弹出框，点击组件触发自动连接
            viewer = self._graph.viewer()  # 根据你的结构获取 viewer
            if hasattr(viewer, '_temp_connection_source') and viewer._temp_connection_source:
                source_port_item = viewer._temp_connection_source
                source_node = source_port_item.original_node
                viewer._temp_connection_source = None  # 用完立即清空

                if source_port_item.port_type == 'out':
                    source_port = source_node._outputs[
                        [p.name() for p in source_node._outputs].index(source_port_item.name)
                    ]
                    # 找新节点的第一个输入口
                    QTimer.singleShot(0, lambda: new_node.set_input(0, source_port))

                else:
                    port_index = [p.name() for p in source_node._inputs].index(source_port_item.name)
                    QTimer.singleShot(0, lambda: source_node.set_input(port_index, new_node.output_ports()[0]))

            self.parent.on_selection_changed()
            self._graph.end_undo()
        else:
            node = data.get("node_ptr")
            if node:
                self._graph.clear_selection()
                node.set_selected(True)
                self._graph.fit_to_selection()
        self.close()

    def show_at_cursor(self, pos):
        # 先更新缓存（不依赖方向）
        self.update_cache()

        # === 第一步：确定弹出方向 ===
        screen_rect = QtWidgets.QApplication.desktop().availableGeometry(pos)
        menu_width = self.width()
        menu_height = self.height()

        target_x = pos.x() - 20
        target_y = pos.y() + 10

        if target_y - menu_height < screen_rect.top():
            self._is_upward_mode = False
        else:
            self._is_upward_mode = True
            target_y = pos.y() - menu_height - 10

        # 边界保护
        if target_x + menu_width > screen_rect.right():
            target_x = screen_rect.right() - menu_width
        if target_x < screen_rect.left():
            target_x = screen_rect.left()

        # === 第二步：根据新方向重建 UI ===
        self.populate_ui()  # populate_ui 会读取 self._is_upward_mode

        # === 第三步：设置位置和 focus ===
        viewer = self._graph.viewer()
        scene_viewer = viewer.get_scene_viewer() if hasattr(viewer, 'get_scene_viewer') else viewer
        self._spawn_pos = scene_viewer.mapFromGlobal(pos)
        self.search_line.setText("")

        # 调整 header 和 list 顺序
        self.container_layout.removeWidget(self.header_widget)
        self.container_layout.removeWidget(self.list_widget)

        if self._is_upward_mode:
            self.container_layout.addWidget(self.list_widget)
            self.container_layout.addWidget(self.header_widget)
        else:
            self.container_layout.addWidget(self.header_widget)
            self.container_layout.addWidget(self.list_widget)

        self.move(target_x, target_y)
        self.show()
        self.search_line.setFocus()

    def on_return_pressed(self):
        current_item = self.list_widget.currentItem()
        if current_item and not current_item.isHidden():
            self.on_item_confirmed(current_item)

    def show_category_filter(self):
        pos = self.filter_button.mapToGlobal(self.filter_button.rect().bottomLeft())
        self._left_panel.draggable_tree.category_filter_dialog.show_at(pos)

    def eventFilter(self, source, event):
        if event.type() == QtCore.QEvent.KeyPress:
            if event.key() == Qt.Key_Tab:
                self.toggle_mode()
                return True
            if event.key() == Qt.Key_Escape:
                self.close()
                return True
            if source is self.search_line:
                if event.key() in [Qt.Key_Down, Qt.Key_Up]:
                    self.list_widget.setFocus()
                    return True
        return super(CustomGraphMenu, self).eventFilter(source, event)