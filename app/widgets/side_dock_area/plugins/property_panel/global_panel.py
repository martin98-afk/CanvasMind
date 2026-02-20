# -*- coding: utf-8 -*-
import json
import re

from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QStackedWidget, QApplication
from loguru import logger
from qfluentwidgets import SimpleCardWidget, SegmentedWidget, \
    FluentIcon, InfoBar, InfoBarPosition, TransparentToolButton, RoundMenu, Action, TransparentPushButton, \
    TransparentDropDownToolButton, BodyLabel, StrongBodyLabel, CaptionLabel, ToolButton
from qfluentwidgets.components.widgets.card_widget import CardSeparator

from app.utils.utils import get_icon
from app.widgets.dialog_widget.custom_messagebox import CustomTwoInputDialog
from app.widgets.side_dock_area.plugins.property_panel.draggable_variable_card import DraggableVariableCard
from app.widgets.side_dock_area.plugins.property_panel.parameter_group import ParameterGroupDialog
from app.widgets.side_dock_area.plugins.property_panel.variable_tree import VariableTreeWidget


class GlobalPanelWidget:
    """处理全局变量UI的子模块"""

    def __init__(self, main_window, parent_panel, parent_layout):
        self.main_window = main_window
        self.parent_panel = parent_panel  # PropertyPanel 的实例
        self.parent_layout = parent_layout  # PropertyPanel 中的 global_vbox

        # 缓存字典
        self._custom_var_cards = {}
        self._node_var_cards = {}
        self._env_var_cards = {}
        self._built = False

        # UI组件引用
        self.global_segmented = None
        self.global_stacked = None
        self.env_page = None
        self.node_page = None
        self.custom_page = None
        self._current_global_tab = 'custom'
        # --- 新增：存储布局引用 ---
        self.custom_vars_layout = None
        self.node_vars_layout = None
        self.env_vars_layout = None

    def build_ui(self):
        """构建全局变量UI"""
        if self._built:
            self._refresh_content()
            return
        segment_layout = QHBoxLayout(self.parent_panel)
        segment_layout.setContentsMargins(5, 5, 5, 0)
        self.global_segmented = SegmentedWidget(self.parent_panel)
        self.global_segmented.addItem('env', '环境变量')
        self.global_segmented.addItem('node', '节点变量')
        self.global_segmented.addItem('custom', '自定义变量')
        self.global_segmented.setCurrentItem('node')
        segment_layout.addWidget(self.global_segmented)
        self.global_stacked = QStackedWidget(self.parent_panel)

        self.env_page = self._create_env_page()
        self.node_page = self._create_node_vars_page()
        self.custom_page = self._create_custom_vars_page()

        self.global_stacked.addWidget(self.env_page)
        self.global_stacked.addWidget(self.node_page)
        self.global_stacked.addWidget(self.custom_page)
        self.global_stacked.setCurrentIndex(1)

        self.global_segmented.currentItemChanged.connect(self._on_global_tab_changed)
        self.parent_layout.addLayout(segment_layout)
        self.parent_layout.addWidget(self.global_stacked)
        self._built = True

    def _refresh_content(self):
        """仅刷新所有页面的内容，不重建控件结构"""
        self._refresh_custom_vars_page()
        self._refresh_node_vars_page()
        self._refresh_env_page()

    def on_global_variables_changed(self, var_type: str, var_name: str, action: str):
        """
        接收全局变量变化信号，并进行增量更新。
        这个方法是 PropertyPanel 转发信号的入口。
        """
        if not self._built:
            # 如果全般面板尚未构建，直接返回，不处理信号
            return

        # 调用内部处理逻辑
        self._handle_global_variable_change(var_type, var_name, action)

    def _handle_global_variable_change(self, var_type: str, var_name: str, action: str):
        """
        内部处理逻辑，根据 var_type, var_name, action 更新UI。
        """
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return

        if var_type == "node_vars":
            if action == "clear":
                global_vars.clear_node_vars(var_name)
            # 调用优化后的刷新方法
            self._refresh_node_vars_page()

        elif var_type == "custom":
            if action == "update":
                if var_name in self._custom_var_cards:
                    card = self._custom_var_cards[var_name]
                    new_val_obj = global_vars.custom.get(var_name)
                    if not new_val_obj: return  # 异常保护

                    new_value = new_val_obj.value

                    # 检查类型是否变更 (KV <-> Group)
                    is_group_card = card.objectName() == "kvGroupCard"
                    is_new_value_group = isinstance(new_value, dict)

                    if is_group_card != is_new_value_group:
                        # 类型变了，只能重建
                        card.deleteLater()
                        del self._custom_var_cards[var_name]
                        self._refresh_custom_vars_page()  # 走全量添加逻辑
                    else:
                        # 类型没变，原地更新 UI
                        if is_new_value_group:
                            # 更新 Group
                            self._update_parameter_group_card(card, new_value)
                        else:
                            # 更新 KV
                            self._update_kv_card(card, new_value)
                else:
                    # 没找到卡片，当作新增
                    self._refresh_custom_vars_page()
            else:
                self._refresh_custom_vars_page()
        elif var_type == "env":
            self._refresh_env_page()

        self.main_window.global_variables_changed.emit(f"{var_type}.{var_name}", action)

    # [新增] 辅助更新 KV 卡片
    def _update_kv_card(self, card, new_value):
        layout = card.layout()
        if layout.count() > 1:
            value_label = layout.itemAt(1).widget()
            if isinstance(value_label, BodyLabel):
                try:
                    preview = json.dumps(new_value, ensure_ascii=False, default=str)[:40] + "..." \
                        if isinstance(new_value, (dict, list)) else str(new_value)[:40]
                except:
                    preview = "<无法预览>"

                # 只有文字变了才 set，避免闪烁
                if value_label.text() != preview:
                    value_label.setText(preview)

    # [新增] 辅助更新 Group 卡片
    def _update_parameter_group_card(self, card, new_value):
        # 1. 更新标题栏的计数
        layout = card.layout()  # VBox
        title_layout = layout.itemAt(0).layout()  # HBox
        count_label = title_layout.itemAt(1).widget()
        new_count_text = f"[参数x{len(new_value)}]"
        if count_label.text() != new_count_text:
            count_label.setText(new_count_text)

        # 2. 更新详情区域 (简单起见，这里可以重建详情区，或者遍历更新)
        # 详情区通常是隐藏的，重建开销不大
        detail_container = layout.itemAt(1).widget()
        detail_layout = detail_container.layout()

        # 清空详情
        while detail_layout.count():
            item = detail_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            if item.layout():
                # 递归清理layout比较麻烦，这里详情结构简单，都是 HBox
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget(): sub.widget().deleteLater()
                item.layout().deleteLater()

        # 重新填充
        for key, val in new_value.items():
            param_row = QHBoxLayout()
            param_key = BodyLabel(f"{key}:")
            param_value_text = str(val)
            if len(param_value_text) > 50:
                param_value_text = param_value_text[:50] + "..."
            param_value = BodyLabel(param_value_text)
            param_value.setStyleSheet("color: #888888;")
            param_value.setWordWrap(True)
            param_row.addWidget(param_key)
            param_row.addWidget(param_value, 1)
            detail_layout.addLayout(param_row)

    def _on_global_tab_changed(self, key):
        if key == 'env':
            index = 0
        elif key == 'node':
            index = 1
        else:
            index = 2
        self.global_stacked.setCurrentIndex(index)

    def _create_custom_vars_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = TransparentPushButton(text="自定义变量 (custom)", icon=get_icon("自定义变量"), parent=self.parent_panel)
        layout.addWidget(title)

        # 创建一个水平布局来放置两个按钮
        btn_layout = QHBoxLayout()
        add_custom_btn = TransparentPushButton(text="新增KV变量", parent=self.parent_panel, icon=FluentIcon.ADD)
        add_custom_btn.clicked.connect(self.add_new_custom_variable)
        add_group_btn = TransparentPushButton(text="新增参数组", parent=self.parent_panel, icon=FluentIcon.ADD)
        add_group_btn.clicked.connect(self.add_new_parameter_group)
        btn_layout.addWidget(add_custom_btn)
        btn_layout.addWidget(add_group_btn)
        layout.addLayout(btn_layout)

        # --- 分类容器 ---
        self.custom_container = QWidget()
        self.custom_container.setStyleSheet("background: transparent; border: none;")
        self.custom_layout = QVBoxLayout(self.custom_container)
        self.custom_layout.setContentsMargins(5, 2, 5, 5)

        self.custom_params_container = QWidget()  # 参数组容器
        self.custom_params_layout = QVBoxLayout(self.custom_params_container)
        self.custom_params_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_params_layout.setSpacing(3)

        self.custom_kvs_container = QWidget()  # KV变量容器
        self.custom_kvs_layout = QVBoxLayout(self.custom_kvs_container)
        self.custom_kvs_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_kvs_layout.setSpacing(3)

        # 添加容器到主布局
        self.custom_layout.addWidget(self.custom_params_container)
        # 分割线
        self.custom_separator = CardSeparator()
        self.custom_layout.addWidget(self.custom_separator)
        self.custom_layout.addWidget(self.custom_kvs_container)
        self.custom_layout.addStretch()
        scroll = self.parent_panel.set_scrollbar(self.custom_container)
        layout.addWidget(scroll, 1)
        self._refresh_custom_vars_page()
        return widget

    def _create_node_vars_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题
        title_layout = QHBoxLayout()
        title = TransparentPushButton(text="节点变量 (node_vars)", icon=get_icon("节点变量"),
                                      parent=self.parent_panel)
        title_layout.addWidget(title, 1)

        expand_all_btn = TransparentToolButton(get_icon("expand_all"))
        expand_all_btn.setFixedSize(25, 32)
        collapse_all_btn = TransparentToolButton(get_icon("collapse_all"))
        collapse_all_btn.setFixedSize(25, 32)

        expand_all_btn.clicked.connect(lambda: self._set_all_nodes_expanded(True))
        collapse_all_btn.clicked.connect(lambda: self._set_all_nodes_expanded(False))

        title_layout.addWidget(expand_all_btn)
        title_layout.addWidget(collapse_all_btn)
        layout.addLayout(title_layout)
        layout.addStretch()
        # --------------------------

        self.node_vars_container = QWidget()
        self.node_vars_container.setStyleSheet("background: transparent; border: none;")
        self.node_vars_layout = QVBoxLayout(self.node_vars_container)
        self.node_vars_layout.setContentsMargins(10, 10, 10, 10)
        self.node_vars_layout.setSpacing(3)
        node_scroll = self.parent_panel.set_scrollbar(self.node_vars_container)
        layout.addWidget(node_scroll, 1)
        self._refresh_node_vars_page()
        return widget

    def _create_env_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        title = TransparentPushButton(text="环境变量 (env)", icon=get_icon("环境变量"), parent=self.parent_panel)
        layout.addWidget(title)
        add_env_btn = TransparentPushButton(text="新增环境变量", parent=self.parent_panel, icon=FluentIcon.ADD)
        add_env_btn.clicked.connect(self.add_new_env_variable)
        layout.addWidget(add_env_btn)
        self.env_vars_container = QWidget()
        self.env_vars_container.setStyleSheet("background: transparent; border: none;")
        self.env_vars_layout = QVBoxLayout(self.env_vars_container)
        self.env_vars_layout.setContentsMargins(5, 5, 5, 5)
        self.env_vars_layout.setSpacing(3)
        env_scroll = self.parent_panel.set_scrollbar(self.env_vars_container)
        layout.addWidget(env_scroll, 1)
        self._refresh_env_page()
        return widget

    # ========================
    # 全局变量 UI 构建（增量更新）
    # ========================
    def _refresh_custom_vars_page(self):
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return

        # 获取当前所有自定义变量
        existing_custom = set(self._custom_var_cards.keys())

        # 分类当前变量
        current_params = {name: global_vars.custom[name].value for name, obj in global_vars.custom.items() if
                          isinstance(obj.value, dict)}
        current_kvs = {name: global_vars.custom[name].value for name, obj in global_vars.custom.items() if
                       not isinstance(obj.value, dict)}

        # --- 处理参数组 (Params) ---
        current_param_names = set(current_params.keys())
        existing_param_names = {name for name in existing_custom if name in self._custom_var_cards and isinstance(
            global_vars.custom.get(name, type('obj', (), {'value': None})()).value, dict)}
        # Note: 上面这行 existing_param_names 的判断逻辑依赖于 global_vars.custom 的实时性

        # 添加新参数组
        for name in current_param_names - existing_param_names:
            card = self._create_parameter_group_row(name, current_params[name])
            self.custom_params_layout.addWidget(card)
            self._custom_var_cards[name] = card

        # 删除旧参数组
        for name in existing_param_names - current_param_names:
            if name in self._custom_var_cards:
                card = self._custom_var_cards.pop(name)
                card.deleteLater()

        # --- 处理KV变量 (KVs) ---
        current_kv_names = set(current_kvs.keys())
        existing_kv_names = {name for name in existing_custom if name in self._custom_var_cards and not isinstance(
            global_vars.custom.get(name, type('obj', (), {'value': None})()).value, dict)}

        # 添加新KV变量
        for name in current_kv_names - existing_kv_names:
            card = self._create_dict_row(name, current_kvs[name])
            self.custom_kvs_layout.addWidget(card)
            self._custom_var_cards[name] = card

        # 删除旧KV变量
        for name in existing_kv_names - current_kv_names:
            if name in self._custom_var_cards:
                card = self._custom_var_cards.pop(name)
                card.deleteLater()

        # --- 控制分割线可见性 ---
        has_params = self.custom_params_layout.count() > 0
        has_kvs = self.custom_kvs_layout.count() > 0
        self.custom_separator.setVisible(has_params and has_kvs)

    def _refresh_node_vars_page(self):
        """优化后的节点变量刷新逻辑：增量更新 + 布局修复"""
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return

        # 1. 关键修复：先移除布局最底部的 Stretch (如果有)
        # 防止多次刷新导致底部堆积多个弹簧，或者卡片被插到弹簧之间
        cnt = self.node_vars_layout.count()
        if cnt > 0:
            last_item = self.node_vars_layout.itemAt(cnt - 1)
            # 检查是否是 SpacerItem (addStretch 产生的就是 SpacerItem)
            if last_item.spacerItem():
                self.node_vars_layout.removeItem(last_item)
                # 注意：removeItem 不会销毁对象，建议显式删除以防内存泄漏（虽 Python 有 GC）
                del last_item

                # 2. 获取当前数据状态
        current_node_vars = getattr(global_vars, 'node_vars', {})
        current_node_groups = {}
        for var_name, var_obj in current_node_vars.items():
            node_name = var_name.split("__")[0]
            if node_name not in current_node_groups:
                current_node_groups[node_name] = []
            current_node_groups[node_name].append((var_name, var_obj))

        # 3. 处理空状态
        if not current_node_vars:
            # 清理所有现有卡片
            for name in list(self._node_var_cards.keys()):
                self._node_var_cards.pop(name).deleteLater()

            # 显示空提示（如果还没有的话）
            has_hint = False
            for i in range(self.node_vars_layout.count()):
                w = self.node_vars_layout.itemAt(i).widget()
                if w and w.objectName() == "empty_hint":
                    has_hint = True
                    break

            if not has_hint:
                empty_label = BodyLabel("变量池中暂无节点输出\n在节点输出菜单中添加")
                empty_label.setAlignment(Qt.AlignCenter)
                empty_label.setObjectName("empty_hint")
                empty_label.setStyleSheet("color: #888888; margin-top: 50px;")
                self.node_vars_layout.addWidget(empty_label)
            return
        else:
            # 如果有数据，移除可能存在的空提示
            for i in reversed(range(self.node_vars_layout.count())):
                item = self.node_vars_layout.itemAt(i)
                if item.widget() and item.widget().objectName() == "empty_hint":
                    item.widget().deleteLater()

        # 4. 增删卡片
        existing_nodes = set(self._node_var_cards.keys())
        target_nodes = set(current_node_groups.keys())

        # 删除不存在的节点组
        for node_name in existing_nodes - target_nodes:
            card = self._node_var_cards.pop(node_name)
            card.deleteLater()

        # 5. 排序并更新布局顺序
        sorted_node_names = sorted(target_nodes)

        # 使用 layout_index 确保卡片在布局中严格按顺序排列
        layout_index = 0

        for node_name in sorted_node_names:
            group_items = sorted(current_node_groups[node_name], key=lambda x: x[0])

            if node_name in self._node_var_cards:
                # 已存在：更新内容
                card = self._node_var_cards[node_name]
                self._sync_node_group_content(card, group_items)
            else:
                # 新增：创建卡片
                card = self._create_node_group_card_enhanced(node_name, group_items)
                self._node_var_cards[node_name] = card
                # 先简单添加，后面统一调整位置
                self.node_vars_layout.addWidget(card)

                # --- 强制布局顺序调整 ---
            # 检查当前 layout_index 位置的组件是否是目标 card
            current_item = self.node_vars_layout.itemAt(layout_index)

            if current_item is None or current_item.widget() != card:
                # 如果位置不对（例如新插入了节点，或者顺序变了），将卡片挪到正确位置
                self.node_vars_layout.removeWidget(card)
                self.node_vars_layout.insertWidget(layout_index, card)

            layout_index += 1

        # 6. 最后添加 Stretch，确保所有卡片顶端对齐
        self.node_vars_layout.addStretch(1)

    def _sync_node_group_content(self, card, group_items):
        """同步单个节点卡片内的变量行"""
        # card.row_cache 结构: { full_var_name: {'widget': row_widget, 'data_id': id(val), 'policy': str} }
        if not hasattr(card, 'row_cache'):
            card.row_cache = {}

        target_vars = {item[0]: item[1] for item in group_items}
        existing_vars = set(card.row_cache.keys())
        current_vars = set(target_vars.keys())

        layout = card.content_layout  # 需要在 _create_node_group_card_enhanced 中暴露这个属性

        # 1. 删除多余的行
        for var_name in existing_vars - current_vars:
            cache_item = card.row_cache.pop(var_name)
            cache_item['widget'].deleteLater()

        # 2. 新增或更新行
        # 为了保持顺序，最好是清空 layout 重新 add？不，这样闪烁。
        # 我们按 items 顺序遍历，对比 check

        # 获取当前的 widget 列表顺序（略微复杂，这里简化处理：直接 append 新的，不强制重排顺序）

        for var_name, var_obj in group_items:
            val_id = id(var_obj.value)
            policy = var_obj.update_policy

            if var_name not in card.row_cache:
                # 新增
                row_widget = self._create_compact_port_row(var_name, var_obj)
                layout.addWidget(row_widget)
                card.row_cache[var_name] = {
                    'widget': row_widget,
                    'data_id': val_id,
                    'policy': policy
                }
            else:
                # 更新检查
                cache = card.row_cache[var_name]
                row_widget = cache['widget']

                # 检查策略是否变化 (更新 UI)
                if cache['policy'] != policy:
                    # 找到下拉框控件并更新
                    btn = row_widget.findChild(TransparentDropDownToolButton)
                    if btn:
                        btn.setIcon(get_icon(policy))
                        btn.setProperty("policy", policy)
                    cache['policy'] = policy

                # 检查数据是否变化 (更新 Tree)
                # 注意：如果是 None 变 None，id 是一样的。
                # 如果是可变对象(dict/list)内容变了但 id 没变（原地修改），这里可能检测不到。
                # 但在数据流图中，通常输出是新生成的对象。如果需要深度检测，代价太大。
                # 折中方案：比对 id，以及如果是基础类型比对值。
                should_update_data = (cache['data_id'] != val_id)

                if should_update_data:
                    # 找到 Tree 组件
                    tree = row_widget.findChild(VariableTreeWidget)
                    if tree:
                        if var_obj.value is not None:
                            tree.set_data(var_obj.value, var_name.split("__")[-1])
                            tree.show()
                        else:
                            # 如果变成了 None，可能需要隐藏 tree 或显示 label？
                            # 原逻辑 _create_compact_port_row 是 create 时决定的。
                            # 如果结构需要动态变（有数据 <-> 无数据），最好是重新生成 row
                            pass
                    else:
                        # 原来没 tree (即原来是 None)，现在有值了 -> 简单起见，重建 row
                        if var_obj.value is not None:
                            layout.removeWidget(row_widget)
                            row_widget.deleteLater()
                            new_row = self._create_compact_port_row(var_name, var_obj)
                            layout.addWidget(new_row)
                            card.row_cache[var_name]['widget'] = new_row

                    cache['data_id'] = val_id

    def _create_node_group_card_enhanced(self, node_name: str, node_var_items: list):
        """增强版节点组卡片：支持折叠、定位、计数"""
        card = SimpleCardWidget(self.parent_panel)
        card.row_cache = {}
        outer_layout = QVBoxLayout(card)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # --- 头部区域 ---
        header_widget = QWidget()
        header_widget.setFixedHeight(45)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(6, 0, 6, 0)

        # 节点图标和名称
        node = self.locate_node_by_name(node_name)
        node_icon = TransparentToolButton((node and node.icon()) or FluentIcon.TILES, header_widget)
        node_icon.setFixedSize(24, 24)

        display_name = node_name.replace("_", " ")
        name_label = StrongBodyLabel(display_name)
        name_label.setWordWrap(True)

        locate_btn = TransparentToolButton(get_icon("location"), header_widget)
        locate_btn.setToolTip("在画布中定位节点")
        locate_btn.setFixedSize(24, 24)
        locate_btn.clicked.connect(lambda: self.zoom_to_node_by_name(node_name))

        toggle_btn = ToolButton(FluentIcon.CHEVRON_DOWN_MED, header_widget)
        toggle_btn.setFixedSize(24, 24)

        header_layout.addWidget(node_icon)
        header_layout.addWidget(name_label, 1)
        header_layout.addStretch()
        header_layout.addWidget(locate_btn)
        header_layout.addWidget(toggle_btn)

        outer_layout.addWidget(header_widget)

        # --- 内容区域 ---
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(3, 3, 3, 3)
        content_layout.setSpacing(3)

        # [新增] 暴露 layout 给 sync 方法使用
        card.content_layout = content_layout

        for var_name, node_var_obj in node_var_items:
            port_row = self._create_compact_port_row(var_name, node_var_obj)
            content_layout.addWidget(port_row)

            # [新增] 初始填充缓存
            card.row_cache[var_name] = {
                'widget': port_row,
                'data_id': id(node_var_obj.value),
                'policy': node_var_obj.update_policy
            }

        outer_layout.addWidget(content_container)

        # --- 修改部分：定义显式的展开/折叠方法 ---
        def set_expanded(expanded: bool):
            content_container.setVisible(expanded)
            toggle_btn.setIcon(FluentIcon.CHEVRON_DOWN_MED if expanded else FluentIcon.CHEVRON_RIGHT)

        # 将方法挂载到 card 对象上，方便外部调用
        card.set_expanded = set_expanded

        def toggle():
            is_visible = content_container.isVisible()
            set_expanded(not is_visible)

        header_widget.mousePressEvent = lambda e: toggle() if e.button() == Qt.LeftButton else None
        toggle_btn.clicked.connect(toggle)

        return card

    def _create_compact_port_row(self, full_var_name: str, node_var_obj):
        """更紧凑的端口行，而不是嵌套卡片"""
        row_widget = DraggableVariableCard(
            self.parent_panel,
            "node_vars",
            full_var_name,
            node_var_obj.value
        )
        row_widget.setObjectName("portRow")
        row_widget.setStyleSheet("""
            #portRow {
                background: rgba(0, 0, 0, 0.05);
                border-radius: 4px;
            }
            #portRow:hover {
                background: rgba(0, 0, 0, 0.08);
                border-left: 3px solid #2ecc71;  /* 拖拽提示 */
            }
            """)

        layout = QVBoxLayout(row_widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 端口标题行
        title_layout = QHBoxLayout()
        port_name = full_var_name.split("__")[-1]

        port_icon = CaptionLabel("端口")
        port_icon.setStyleSheet("background: #0078d4; color: white; padding: 1px 4px; border-radius: 2px;")

        port_label = BodyLabel(port_name)
        port_label.setWordWrap(True)
        # 策略图标预览
        strategy_combo = TransparentDropDownToolButton(icon=get_icon(node_var_obj.update_policy),
                                                       parent=self.parent_panel)
        strategy_combo.setFixedSize(52, 24)
        strategy_combo.setProperty("policy", node_var_obj.update_policy)
        strategy_combo.setProperty("node_var_name", full_var_name)
        menu = RoundMenu(parent=strategy_combo)
        menu.addAction(
            Action(get_icon("固定"), '固定',
                   triggered=lambda checked=False, btn=strategy_combo: self.change_node_var_strategy("固定", btn))
        )
        menu.addAction(
            Action(get_icon("更新"), '更新',
                   triggered=lambda checked=False, btn=strategy_combo: self.change_node_var_strategy("更新", btn))
        )
        menu.addAction(
            Action(get_icon("追加"), '追加',
                   triggered=lambda checked=False, btn=strategy_combo: self.change_node_var_strategy("追加", btn))
        )
        strategy_combo.setMenu(menu)

        del_btn = TransparentToolButton(FluentIcon.CLOSE)
        del_btn.setFixedSize(20, 20)
        del_btn.clicked.connect(lambda: self.delete_variable('node_vars', full_var_name))

        title_layout.addWidget(port_icon)
        title_layout.addWidget(port_label, 1)
        title_layout.addStretch()
        title_layout.addWidget(strategy_combo)
        title_layout.addWidget(del_btn)

        layout.addLayout(title_layout)

        # 数据预览区域（只有在有数据时才显示一部分）
        if node_var_obj.value is not None:
            tree = VariableTreeWidget(parent=self.main_window)
            tree.set_data(node_var_obj.value, port_name)
            tree.setMinimumHeight(60)
            tree.setMaximumHeight(100)
            layout.addWidget(tree)
        else:
            layout.addWidget(CaptionLabel("等待执行产生数据..."))

        # 右键菜单保持不变
        row_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        row_widget.customContextMenuRequested.connect(
            lambda pos: self._show_port_context_menu(pos, row_widget, full_var_name))

        return row_widget

    def _set_all_nodes_expanded(self, expanded: bool):
        """批量设置所有节点卡片的展开状态"""
        for card in self._node_var_cards.values():
            if hasattr(card, 'set_expanded'):
                card.set_expanded(expanded)

    def _show_port_context_menu(self, pos, widget, name):
        """提取出的右键菜单逻辑"""
        menu = RoundMenu(parent=self.parent_panel)
        menu.addActions([
            Action(FluentIcon.COPY, "复制表达式", triggered=lambda: self.copy_as_expression("node_vars", name)),
            Action(FluentIcon.DELETE, "清空数据",
                   triggered=lambda: self._handle_global_variable_change("node_vars", name, "clear")),
            Action(get_icon("追踪"), "追踪变量", parent=self.parent_panel,
                   triggered=lambda: self.track_variable_usages("node_vars", name))
        ])
        menu.exec_(widget.mapToGlobal(pos))

    def zoom_to_node_by_name(self, node_name):
        """根据节点名称跳转到节点"""
        found_node = self.locate_node_by_name(node_name)
        return self.main_window.graph.viewer().zoom_to_nodes([found_node._view])

    def _refresh_env_page(self):
        # 去除最后strech
        self.env_vars_layout.removeItem(self.env_vars_layout.itemAt(self.env_vars_layout.count() - 1))
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars or not hasattr(global_vars, 'env'):
            return
        all_env_vars = global_vars.env.get_all_env_vars()
        current_env = {k: v for k, v in all_env_vars.items() if k != 'start_time'}
        existing_env = set(self._env_var_cards.keys())
        for key in current_env.keys() - existing_env:
            card = self._create_env_var_row(key, current_env[key])
            self.env_vars_layout.addWidget(card)
            self._env_var_cards[key] = card
        for key in existing_env - current_env.keys():
            card = self._env_var_cards.pop(key)
            card.deleteLater()
        for key in current_env.keys() & existing_env:
            card = self._env_var_cards[key]
            value = current_env[key]
            if card.layout().count() >= 2:
                value_label = card.layout().itemAt(1).widget()
                if isinstance(value_label, BodyLabel):
                    try:
                        preview = json.dumps(value, ensure_ascii=False, default=str)[:40] + "..." \
                            if isinstance(value, (dict, list)) else str(value)[:40]
                    except:
                        preview = "<无法预览>"
                    value_label.setText(preview)
        if not current_env and self.env_vars_layout.count() == 0:
            self.env_vars_layout.addWidget(BodyLabel("暂无环境变量"))
        self.env_vars_layout.addStretch(1)

    def _create_dict_row(self, name: str, value):
        """创建普通的KV变量卡片"""
        card = DraggableVariableCard(self.parent_panel, "custom", name, value)
        card.setObjectName("kvCard")
        card.setStyleSheet("""#kvCard:hover {
            background: rgba(0, 0, 0, 0.08);
            border-left: 3px solid #3498db;  /* 拖拽提示 */
        }""")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        name_label = BodyLabel(f"{name}:")
        try:
            preview = json.dumps(value, ensure_ascii=False, default=str)[:40] + "..." \
                if isinstance(value, (dict, list)) else str(value)[:40]
        except:
            preview = "<无法预览>"
        value_label = BodyLabel(preview)
        value_label.setWordWrap(True)
        value_label.setStyleSheet("color: #888888;")
        del_btn = TransparentToolButton(FluentIcon.CLOSE, self.parent_panel)
        del_btn.setIconSize(QSize(12, 12))
        del_btn.setFixedSize(16, 16)
        del_btn.clicked.connect(lambda _, n=name: self.delete_variable('custom', n))
        layout.addWidget(name_label)
        layout.addWidget(value_label, 1)
        layout.addStretch()
        layout.addWidget(del_btn)

        def show_context_menu(pos):
            current_val = self.main_window.global_variables.custom.get(name)
            current_val = current_val.value if current_val is not None else "<已删除>"
            menu = RoundMenu(parent=self.parent_panel)
            menu.addActions(
                [
                    Action(
                        FluentIcon.COPY, "复制为表达式", parent=self.parent_panel,
                        triggered=lambda: self.copy_as_expression("custom", name)
                    ),
                    Action(
                        FluentIcon.EDIT, "编辑变量", parent=self.parent_panel,
                        triggered=lambda: self.edit_custom_variable(name, current_val)
                    ),
                    # 追踪变量
                    Action(
                        get_icon("追踪"), "追踪变量", parent=self.parent_panel,
                        triggered=lambda: self.track_variable_usages("custom", name)
                    )
                ]
            )
            menu.exec_(card.mapToGlobal(pos))

        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(show_context_menu)
        return card

    def _create_parameter_group_row(self, name: str, value):
        """创建参数组卡片"""
        card = DraggableVariableCard(self.parent_panel, "custom", name, value)
        card.setObjectName("kvGroupCard")
        card.setStyleSheet("""#kvGroupCard:hover {
                    background: rgba(0, 0, 0, 0.08);
                    border-left: 3px solid #3498db;  /* 拖拽提示 */
                }""")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # 标题行
        title_layout = QHBoxLayout()
        name_label = BodyLabel(f"{name}:")
        title_layout.addWidget(name_label)

        # 参数组信息
        param_count = len(value) if isinstance(value, dict) else 0
        value_label = BodyLabel(f"[参数x{param_count}]")
        value_label.setStyleSheet("color: #888888;")
        title_layout.addWidget(value_label)
        title_layout.addStretch()

        # 删除按钮
        del_btn = TransparentToolButton(FluentIcon.CLOSE, self.parent_panel)
        del_btn.setIconSize(QSize(12, 12))
        del_btn.setFixedSize(16, 16)
        del_btn.clicked.connect(lambda _, n=name: self.delete_variable('custom', n))
        title_layout.addWidget(del_btn)
        layout.addLayout(title_layout)

        # 参数详情展开区域
        detail_container = QWidget()
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(8, 4, 8, 4)
        detail_layout.setSpacing(2)

        # 显示参数详情
        if isinstance(value, dict):
            for key, val in value.items():
                param_row = QHBoxLayout()
                param_key = BodyLabel(f"{key}:")
                # 限制预览长度并启用换行
                param_value_text = str(val)
                if len(param_value_text) > 50:
                    param_value_text = param_value_text[:50] + "..."
                param_value = BodyLabel(param_value_text)
                param_value.setStyleSheet("color: #888888;")
                param_value.setWordWrap(True)  # 启用换行
                param_row.addWidget(param_key)
                param_row.addWidget(param_value, 1)
                detail_layout.addLayout(param_row)

        # 默认折叠参数详情
        detail_container.setVisible(False)
        layout.addWidget(detail_container)

        # 添加展开/折叠按钮
        toggle_btn = TransparentPushButton(text="展开", parent=self.parent_panel)
        toggle_btn.clicked.connect(lambda: self._toggle_parameter_group_detail(detail_container, toggle_btn))
        layout.addWidget(toggle_btn)

        def show_context_menu(pos):
            current_val = self.main_window.global_variables.custom.get(name)
            current_val = current_val.value if current_val is not None else "<已删除>"
            menu = RoundMenu(parent=self.parent_panel)
            menu.addActions(
                [
                    Action(
                        FluentIcon.COPY, "复制为表达式", parent=self.parent_panel,
                        triggered=lambda: self.copy_as_expression("custom", name)
                    ),
                    Action(
                        FluentIcon.EDIT, "编辑参数组", parent=self.parent_panel,
                        triggered=lambda: self.edit_parameter_group(name, current_val)
                    ),
                    # 追踪变量
                    Action(get_icon("追踪"), "追踪变量", parent=self.parent_panel,
                           triggered=lambda: self.track_variable_usages("custom", key))
                ]
            )
            menu.exec_(card.mapToGlobal(pos))

        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(show_context_menu)
        return card

    def _toggle_parameter_group_detail(self, detail_container, toggle_btn):
        """切换参数组详情的显示/隐藏"""
        is_visible = detail_container.isVisible()
        detail_container.setVisible(not is_visible)
        toggle_btn.setText("收起" if not is_visible else "展开")

    def _create_env_var_row(self, key: str, value):
        card = DraggableVariableCard(self.parent_panel, "env", key, value)
        card.setObjectName("envCard")
        card.setStyleSheet("""#envCard:hover {
                    background: rgba(0, 0, 0, 0.08);
                    border-left: 3px solid #9b59b6;  /* 拖拽提示 */
                }""")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        name_label = BodyLabel(f"{key} : ")
        try:
            preview = json.dumps(value, ensure_ascii=False, default=str)[:40] + "..." \
                if isinstance(value, (dict, list)) else str(value)[:40]
        except:
            preview = "<无法预览>"
        value_label = BodyLabel(preview)
        value_label.setWordWrap(True)
        value_label.setStyleSheet("color: #888888;")
        del_btn = TransparentToolButton(FluentIcon.CLOSE, self.parent_panel)
        del_btn.setIconSize(QSize(12, 12))
        del_btn.setFixedSize(16, 16)
        del_btn.clicked.connect(lambda _, k=key: self.delete_env_variable(k))
        layout.addWidget(name_label)
        layout.addWidget(value_label, 1)
        layout.addStretch()
        layout.addWidget(del_btn)

        def show_context_menu(pos):
            current_val = self.main_window.global_variables.get(f"env.{key}")
            menu = RoundMenu(parent=self.parent_panel)
            menu.addAction(Action(FluentIcon.COPY, "复制为表达式", parent=self.parent_panel,
                                  triggered=lambda: self.copy_as_expression("env", key)))
            menu.addAction(Action(FluentIcon.EDIT, "编辑变量", parent=self.parent_panel,
                                  triggered=lambda: self.edit_env_variable(key, current_val)))
            # 追踪变量
            menu.addAction(
                Action(get_icon("追踪"), "追踪变量", parent=self.parent_panel,
                       triggered=lambda: self.track_variable_usages("env", key))
            )
            menu.exec_(card.mapToGlobal(pos))

        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(show_context_menu)
        return card

    # ========================
    # 全局变量操作
    # ========================
    def delete_variable(self, var_type: str, var_name: str):
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return
        try:
            if var_type == 'custom' and hasattr(global_vars, 'custom') and var_name in global_vars.custom:
                del global_vars.custom[var_name]
            elif var_type == 'node_vars' and hasattr(global_vars, 'node_vars') and var_name in global_vars.node_vars:
                global_vars.node_vars.pop(var_name, None)
                node = self.locate_node_by_name(var_name.split("__")[0])
                if node:
                    if hasattr(node, "refresh_node_outports"):
                        QtCore.QTimer.singleShot(0, node.refresh_node_outports)
                    if hasattr(node, "_sync_outputs_ports"):
                        QtCore.QTimer.singleShot(0, node._sync_outputs_ports)
            self._handle_global_variable_change(var_type, var_name, "delete")
            InfoBar.success("已删除", f"变量 '{var_name}' 已移除", parent=self.main_window, duration=1500)
        except Exception as e:
            InfoBar.error("删除失败", str(e), parent=self.main_window)

    def change_node_var_strategy(self, text: str, button: TransparentDropDownToolButton):
        button.setIcon(get_icon(text))
        var_name = button.property('node_var_name')
        if not var_name:
            return
        button.setProperty("policy", text)
        global_vars = getattr(self.main_window, 'global_variables', None)
        if global_vars and hasattr(global_vars, 'node_vars') and var_name in global_vars.node_vars:
            global_vars.node_vars[var_name].update_policy = text

    def add_new_custom_variable(self):
        dialog = CustomTwoInputDialog(
            title1="变量名",
            title2="变量值",
            placeholder1="变量名（如 threshold）",
            placeholder2="变量值（如 0.5）",
            parent=self.main_window
        )
        if dialog.exec():
            name, value_str = dialog.get_text()
            if not name:
                InfoBar.warning("无效名称", "变量名不能为空", parent=self.main_window)
                return
            try:
                if value_str.lower() in ('true', 'false'):
                    value = value_str.lower() == 'true'
                elif '.' in value_str:
                    value = float(value_str)
                else:
                    value = int(value_str)
            except ValueError:
                value = value_str
            global_vars = getattr(self.main_window, 'global_variables', None)
            if global_vars:
                global_vars.set(name, value)
                self._handle_global_variable_change("custom", name, "add")
                InfoBar.success("已添加", f"自定义变量 {name}", parent=self.main_window)

    def add_new_parameter_group(self):
        """添加新的参数组"""
        # 显示合并后的参数组编辑对话框
        dialog = ParameterGroupDialog(parent=self.main_window)

        if dialog.exec():
            new_name = dialog.get_group_name()
            parameters = dialog.get_parameters()

            if not new_name:
                InfoBar.warning("无效名称", "参数组名称不能为空", parent=self.main_window)
                return

            if not parameters:
                InfoBar.warning("无效参数", "参数组至少需要一个参数", parent=self.main_window)
                return

            global_vars = getattr(self.main_window, 'global_variables', None)
            if global_vars:
                if new_name in global_vars.custom:
                    InfoBar.warning("已存在", f"参数组 {new_name} 已存在", parent=self.main_window)
                    return
                # 设置新的参数组
                global_vars.set(new_name, parameters)
                self._handle_global_variable_change("custom", new_name, "add")

    def add_new_env_variable(self):
        dialog = CustomTwoInputDialog(
            title1="环境变量名",
            title2="环境变量值",
            placeholder1="变量名（如 API_KEY）",
            placeholder2="变量值",
            parent=self.main_window
        )
        if dialog.exec():
            name, value = dialog.get_text()
            if not name:
                InfoBar.warning("无效名称", "变量名不能为空", parent=self.main_window)
                return
            global_vars = getattr(self.main_window, 'global_variables', None)
            if global_vars:
                global_vars.env.set_env_var(name, value)
                self._handle_global_variable_change("env", name, "add")
                InfoBar.success("已添加", f"环境变量 {name}", parent=self.main_window)

    def delete_env_variable(self, key: str):
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return
        global_vars.env.delete_env_var(key)
        self._refresh_env_page()
        self._handle_global_variable_change("env", key, "delete")
        InfoBar.success("已删除", f"环境变量 {key}", parent=self.main_window, duration=1500)

    def copy_as_expression(self, prefix: str, var_name: str):
        var_name = re.sub(r'\s+', '_', var_name)
        expr = f"${prefix}.{var_name}$"
        clipboard = QApplication.clipboard()
        clipboard.setText(expr)
        InfoBar.success(
            title="已复制",
            content=f"表达式已复制：{expr}",
            parent=self.main_window,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=1500
        )

    def edit_custom_variable(self, var_name: str, current_value):
        dialog = CustomTwoInputDialog(
            title1="变量名",
            title2="变量值",
            placeholder1="变量名（如 threshold）",
            placeholder2="变量值（如 0.5）",
            text1=var_name,
            text2=str(current_value),
            parent=self.main_window
        )
        if dialog.exec():
            new_name, new_value_str = dialog.get_text()
            if not new_name:
                InfoBar.warning("无效名称", "变量名不能为空", parent=self.main_window)
                return
            if new_name == var_name and new_value_str == str(current_value):
                return
            try:
                if new_value_str.lower() in ('true', 'false'):
                    new_value = new_value_str.lower() == 'true'
                elif '.' in new_value_str:
                    new_value = float(new_value_str)
                else:
                    new_value = int(new_value_str)
            except ValueError:
                new_value = new_value_str
            global_vars = getattr(self.main_window, 'global_variables', None)
            if not global_vars:
                return
            if new_name != var_name and var_name in global_vars.custom:
                del global_vars.custom[var_name]
                self._handle_global_variable_change("custom", var_name, "delete")
                global_vars.set(new_name, new_value)
                self._handle_global_variable_change("custom", new_name, "add")
            else:
                # 仅更新值，名称不变
                global_vars.set(new_name, new_value)
                # 发送更新信号
                self._handle_global_variable_change("custom", new_name, "update")
            InfoBar.success("已更新", f"变量 {new_name}", parent=self.main_window)

    def edit_parameter_group(self, var_name: str, current_value):
        """编辑参数组"""
        if not isinstance(current_value, dict):
            InfoBar.error("编辑失败", "该变量不是参数组", parent=self.main_window)
            return

        # 显示合并后的参数组编辑对话框，传入现有数据
        dialog = ParameterGroupDialog(
            parent=self.main_window,
            group_name=var_name,
            group_data=current_value,
            is_new=False
        )

        if dialog.exec():
            new_name = dialog.get_group_name()
            parameters = dialog.get_parameters()

            if not new_name:
                InfoBar.warning("无效名称", "参数组名称不能为空", parent=self.main_window)
                return

            if not parameters:
                InfoBar.warning("无效参数", "参数组至少需要一个参数", parent=self.main_window)
                return

            global_vars = getattr(self.main_window, 'global_variables', None)
            if global_vars:
                # 如果名称改变，先删除旧的
                if var_name != new_name:
                    if hasattr(global_vars, 'custom') and var_name in global_vars.custom:
                        del global_vars.custom[var_name]
                        self._handle_global_variable_change("custom", var_name, "delete")

                # 设置新的参数组
                global_vars.set(new_name, parameters)

                # 发送更新信号，而不是直接刷新整个页面
                if new_name != var_name:
                    self._handle_global_variable_change("custom", new_name, "add")
                else:
                    self._handle_global_variable_change("custom", new_name, "update")

    def edit_env_variable(self, key: str, current_value):
        dialog = CustomTwoInputDialog(
            title1="环境变量名",
            title2="环境变量值",
            placeholder1="变量名（如 API_KEY）",
            placeholder2="变量值",
            text1=key,
            text2=str(current_value) if current_value is not None else "",
            parent=self.main_window
        )
        if dialog.exec():
            new_key, new_value = dialog.get_text()
            if not new_key:
                InfoBar.warning("无效名称", "变量名不能为空", parent=self.main_window)
                return
            if new_key == key and new_value == current_value:
                return
            global_vars = getattr(self.main_window, 'global_variables', None)
            if not global_vars:
                return
            if new_key != key:
                global_vars.env.delete_env_var(key)
                self._handle_global_variable_change("env", key, "delete")
                self._handle_global_variable_change("env", new_key, "add")
            try:
                global_vars.env.set_env_var(new_key, new_value)
            except Exception as e:
                InfoBar.error("设置环境变量失败", f"错误信息：{e.__str__()}", parent=self.main_window)
                return
            self._refresh_env_page()
            InfoBar.success("已更新", f"环境变量 {new_key}", parent=self.main_window)

    def locate_node_by_name(self, node_name: str):
        """根据全局变量名定位到对应的节点"""
        node_graph = self.main_window.graph
        found_node = node_graph.get_node_by_name(node_name)
        # 如果 base 本身就在组里，直接返回
        if found_node:
            return found_node
        parts = node_name.split('_')
        n = len(parts)

        # 从最细粒度（全拆成空格）到最粗（保留所有下划线）尝试
        for i in range(n - 1, 0, -1):  # i 是保留原始下划线的起始索引（右侧 i 个部分保持原样）
            candidate = ' '.join(parts[:n - i]) + '_' + '_'.join(parts[n - i:]) if n - i > 0 else '_'.join(parts)
            found_node = node_graph.get_node_by_name(candidate)
            if found_node:
                return found_node

        # 如果上面都失败，尝试直接用空格替换所有下划线
        fallback = ' '.join(parts)
        found_node = node_graph.get_node_by_name(fallback)
        if found_node:
            return found_node

        logger.warning(f"未找到节点: '{node_name}'")
        InfoBar.warning(
            title="未找到节点",
            content=f"无法定位到节点 '{node_name}'。",
            parent=self.main_window,
            position=InfoBarPosition.BOTTOM_RIGHT
        )
        self.main_window.global_variables.delete_output(node_name=node_name)

    def add_output_to_global_var(self, main_window, node, port_name: str):
        """将输出添加到全局变量"""
        value = node._output_values.get(port_name)
        safe_node_name = re.sub(r'\s+', '_', node.name())
        safe_port_name = re.sub(r'\s+', '_', port_name)
        safe_port_name = re.sub(r'\.+', '_', safe_port_name)
        var_name = f"{safe_node_name}__{safe_port_name}"
        main_window.global_variables.set_output(
            node_name=safe_node_name, output_name=safe_port_name, output_value=value
        )
        if hasattr(node, "refresh_node_outports"):
            QtCore.QTimer.singleShot(100, node.refresh_node_outports)
        if hasattr(node, "_sync_outputs_ports"):
            QtCore.QTimer.singleShot(100, node._sync_outputs_ports)
        self._handle_global_variable_change("node_vars", var_name, "add")
        InfoBar.success(
            title="成功",
            content=f"已添加全局变量：{var_name}",
            parent=main_window,
            position=InfoBarPosition.BOTTOM_RIGHT
        )

    def delete_output_from_global_var(self, main_window, node, port_name: str=None):
        """从全局变量中删除输出"""
        safe_node_name = re.sub(r'\s+', '_', node.name())
        if port_name is not None:
            safe_port_name = re.sub(r'\s+', '_', port_name)
            safe_port_name = re.sub(r'\.+', '_', safe_port_name)
        else:
            safe_port_name = None
        main_window.global_variables.delete_output(
            node_name=safe_node_name, output_name=safe_port_name
        )
        if hasattr(node, "refresh_node_outports"):
            QtCore.QTimer.singleShot(100, node.refresh_node_outports)
        if hasattr(node, "_sync_outputs_ports"):
            QtCore.QTimer.singleShot(100, node._sync_outputs_ports)
        self._handle_global_variable_change("node_vars", f"{safe_node_name}__{safe_port_name}", "delete")
        InfoBar.success(
            title="成功",
            content=f"已删除全局变量：{safe_node_name}__{safe_port_name}",
            parent=main_window,
            position=InfoBarPosition.BOTTOM_RIGHT
        )

    def is_output_in_global_var(self, main_window, node, port_name: str):
        """判断输出是否在全局变量中"""
        safe_node_name = re.sub(r'\s+', '_', node.name())
        safe_port_name = re.sub(r'\s+', '_', port_name)
        safe_port_name = re.sub(r'\.+', '_', safe_port_name)
        return main_window.global_variables.is_output_in_node_vars(safe_node_name, safe_port_name)

    def track_variable_usages(self, prefix: str, var_name: str):
        """追踪所有使用该变量的节点"""
        target_expr = f"{prefix}.{var_name}"
        nodes_found = []

        # 获取画布上所有节点
        all_nodes = self.main_window.graph.all_nodes()

        for node in all_nodes:
            # 获取节点上的所有自定义控件
            for widget_name, widget in node.widgets().items():
                # 检查是否是我们的 CustomNodeBaseWidget
                if hasattr(widget, "get_value"):
                    if widget.get_value() == target_expr:
                        # widget.widget().toggle_highlight()
                        nodes_found.append(node)
                        break  # 一个节点找到一个匹配即可

        if not nodes_found:
            InfoBar.info("引用追踪", f"未找到使用变量 {target_expr} 的节点", parent=self.main_window)
            return

        # 交互优化：如果有多个引用，可以弹出一个列表，或者直接全部选中并缩放
        self.main_window.graph.viewer().zoom_to_nodes([n._view for n in nodes_found])

        # 视觉反馈：让这些节点“闪烁”一下
        for node in nodes_found:
            # 假设你的 StatusNode 有 highlight 方法，或者直接用选择状态
            node.set_selected(True)

        InfoBar.success("引用追踪", f"找到 {len(nodes_found)} 处引用并已在画布中选中", parent=self.main_window)