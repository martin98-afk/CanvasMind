# -*- coding: utf-8 -*-
from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, QStackedWidget, QApplication, \
    QLineEdit, QLabel, QFormLayout, QScrollArea, QDialog, QButtonGroup, QListWidgetItem, QFrame, QPushButton
from qfluentwidgets import CardWidget, BodyLabel, PushButton, ListWidget, SegmentedWidget, \
    FluentIcon, InfoBar, InfoBarPosition, TransparentToolButton, RoundMenu, Action, TransparentPushButton, \
    TransparentDropDownToolButton, SubtitleLabel, CaptionLabel, ComboBox, MessageBoxBase, MessageBox, LineEdit, \
    ScrollArea, PrimaryPushButton, ToggleToolButton

from app.templates.global_custom_var_template import PARAMETER_TEMPLATE
from app.utils.utils import get_icon, serialize_for_json
from app.widgets.dialog_widget.custom_messagebox import CustomTwoInputDialog
from app.widgets.tree_widget.variable_tree import VariableTreeWidget
import json
import re
from pathlib import Path
from loguru import logger


class ParameterGroupDialog(MessageBoxBase):
    """参数组编辑对话框"""

    def __init__(self, parent=None, group_name="", group_data=None, is_new=True):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("编辑参数组" if not is_new else "新建参数组", self)
        self.group_name = group_name
        self.group_data = group_data or {}
        self.is_new = is_new

        # 设置对话框大小
        self.widget.setFixedSize(600, 500)

        # 创建表单布局
        self.hbox_layout = QHBoxLayout()
        self.hbox_layout.setContentsMargins(10, 5, 10, 5)
        # 参数组名称输入
        self.name_edit = LineEdit()
        self.name_edit.setPlaceholderText("请输入参数组名称")
        if group_name:
            self.name_edit.setText(group_name)
        self.hbox_layout.addWidget(BodyLabel("参数组名称：", self))
        self.hbox_layout.addWidget(self.name_edit, 1)

        self.save_as_template = ToggleToolButton(FluentIcon.SAVE_AS, self)
        self.save_as_template.setChecked(False)
        self.save_as_template.setToolTip("是否保存为参数模板")
        self.hbox_layout.addStretch()
        self.hbox_layout.addWidget(self.save_as_template)

        # 参数编辑区域
        self.params_list = ListWidget()
        self.params_list.setMinimumHeight(200)

        # 添加参数按钮
        self.add_param_btn = PushButton("添加参数", self)
        self.add_param_btn.clicked.connect(self.add_parameter_row)

        # 将表单和滚动区域添加到主布局
        self.viewLayout.setSpacing(5)
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addLayout(self.hbox_layout)
        self.viewLayout.addWidget(self.params_list)
        self.viewLayout.addWidget(self.add_param_btn)

        # 初始化已有参数
        if group_data:
            for key, value in group_data.items():
                self.add_parameter_row(key, str(value))

        # 如果没有参数，添加一个空行
        if not group_data:
            self.add_parameter_row()

    def add_parameter_row(self, key="", value=""):
        """添加参数行"""
        # 创建参数项容器
        item_widget = QWidget()
        item_layout = QHBoxLayout(item_widget)
        item_layout.setContentsMargins(4, 2, 4, 2)

        key_edit = LineEdit()
        key_edit.setPlaceholderText("参数名")
        if key:
            key_edit.setText(key)

        value_edit = LineEdit()
        value_edit.setPlaceholderText("参数值")
        if value:
            value_edit.setText(value)

        delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
        delete_btn.clicked.connect(lambda: self.remove_parameter_row(item_widget))

        item_layout.addWidget(key_edit)
        item_layout.addWidget(value_edit)
        item_layout.addWidget(delete_btn)

        # 创建ListWidgetItem并设置为自定义widget
        list_item = QListWidgetItem(self.params_list)
        list_item.setSizeHint(item_widget.sizeHint())
        self.params_list.setItemWidget(list_item, item_widget)

        # 更新item大小
        item_widget.adjustSize()
        list_item.setSizeHint(item_widget.sizeHint())

    def remove_parameter_row(self, item_widget):
        """移除参数行"""
        for i in range(self.params_list.count()):
            item = self.params_list.item(i)
            if self.params_list.itemWidget(item) == item_widget:
                self.params_list.takeItem(i)
                item_widget.deleteLater()
                break

    def get_parameters(self):
        """获取参数字典"""
        params = {}
        for i in range(self.params_list.count()):
            item = self.params_list.item(i)
            item_widget = self.params_list.itemWidget(item)
            if item_widget:
                layout = item_widget.layout()
                if layout and layout.count() >= 2:
                    key_widget = layout.itemAt(0).widget()
                    value_widget = layout.itemAt(1).widget()
                    if isinstance(key_widget, LineEdit) and isinstance(value_widget, LineEdit):
                        key = key_widget.text().strip()
                        value = value_widget.text().strip()
                        if key:  # 只有当key不为空时才添加
                            try:
                                # 尝试转换为合适的数据类型
                                if value.lower() in ('true', 'false'):
                                    value = value.lower() == 'true'
                                elif '.' in value:
                                    value = float(value)
                                elif value.isdigit():
                                    value = int(value)
                            except:
                                pass  # 保持字符串
                            params[key] = value
        return params

    def get_group_name(self):
        """获取参数组名称"""
        return self.name_edit.text().strip()

    def should_save_as_template(self):
        """是否保存为模板"""
        return self.save_as_template.isChecked()


class TemplateSelectionDialog(MessageBoxBase):
    """参数组模板选择对话框"""

    def __init__(self, parent=None, templates=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("选择参数组类型", self)
        self.selected_template = None
        self.templates = templates or {}

        # 设置对话框大小
        self.widget.setFixedSize(600, 500)

        # 创建布局
        self.viewLayout.addWidget(self.titleLabel)

        # 创建模板列表
        self.template_list = ListWidget()
        self.template_list.setMinimumHeight(150)

        # 添加自定义项
        custom_item = QListWidgetItem("自定义参数组")
        self.template_list.addItem(custom_item)

        # 添加模板项
        for template_name in self.templates.keys():
            item = QListWidgetItem(template_name)
            self.template_list.addItem(item)

        # 设置点击事件
        self.template_list.itemClicked.connect(self.select_template_item)
        self.viewLayout.addWidget(self.template_list)

    def select_template_item(self, item):
        """选择模板项"""
        self.selected_template = item.text()
        self.accept()


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

        # 预定义的参数组模板
        self.parameter_group_templates = PARAMETER_TEMPLATE

    def build_ui(self):
        """构建全局变量UI"""
        if self._built:
            return

        title = SubtitleLabel("🌍 全局变量")
        self.parent_layout.addWidget(title)

        self.global_segmented = SegmentedWidget(self.parent_panel)
        self.global_segmented.addItem('env', '环境变量')
        self.global_segmented.addItem('node', '节点变量')
        self.global_segmented.addItem('custom', '自定义变量')
        self.global_segmented.setCurrentItem('node')

        self.global_stacked = QStackedWidget(self.parent_panel)

        self.env_page = self._create_env_page()
        self.node_page = self._create_node_vars_page()
        self.custom_page = self._create_custom_vars_page()

        self.global_stacked.addWidget(self.env_page)
        self.global_stacked.addWidget(self.node_page)
        self.global_stacked.addWidget(self.custom_page)
        self.global_stacked.setCurrentIndex(1)

        self.global_segmented.currentItemChanged.connect(self._on_global_tab_changed)
        self.parent_layout.addWidget(self.global_segmented)
        self.parent_layout.addWidget(self.global_stacked)
        self._built = True

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
        self.main_window.global_variables_changed.emit(var_type, var_name, action)
        # 重新获取 global_vars 对象，以防信号处理延迟导致的数据不一致
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            logger.warning(
                f"Global variables object not found in main_window when handling {action} for {var_type}.{var_name}")
            return

        if var_type == "node_vars":
            if action == "add" or action == "update":
                if var_name not in self._node_var_cards:
                    if hasattr(global_vars, 'node_vars') and var_name in global_vars.node_vars:
                        card = self._create_variable_card(var_name, global_vars.node_vars[var_name])
                        # 确保 node_vars_layout 存在且有效
                        if self.node_vars_layout:
                            self.node_vars_layout.addWidget(card)
                            self._node_var_cards[var_name] = card
                        else:
                            logger.warning("node_vars_layout not found, cannot add card.")
            elif action == "delete":
                if var_name in self._node_var_cards:
                    card = self._node_var_cards.pop(var_name)
                    card.deleteLater()
            elif action == "clear":
                global_vars.clear_node_vars(var_name)
        elif var_type == "custom":
            if action == "add":
                # 仅处理新增
                if var_name not in self._custom_var_cards:
                    if hasattr(global_vars, 'custom') and var_name in global_vars.custom:
                        value = global_vars.custom[var_name].value
                        # 检查是否是字典类型，决定创建哪种卡片
                        if isinstance(value, dict):
                            card = self._create_parameter_group_row(var_name, value)
                        else:
                            card = self._create_dict_row(var_name, value)
                        if self.custom_vars_layout:
                            self.custom_vars_layout.addWidget(card)
                            self._custom_var_cards[var_name] = card
                        else:
                            logger.warning("custom_vars_layout not found, cannot add card.")
            elif action == "update":
                # 处理更新：删除旧卡片，创建新卡片
                if var_name in self._custom_var_cards:
                    old_card = self._custom_var_cards.pop(var_name)
                    old_card.deleteLater()
                    # 现在当作新增来处理
                    if hasattr(global_vars, 'custom') and var_name in global_vars.custom:
                        value = global_vars.custom[var_name].value
                        if isinstance(value, dict):
                            card = self._create_parameter_group_row(var_name, value)
                        else:
                            card = self._create_dict_row(var_name, value)
                        if self.custom_vars_layout:
                            self.custom_vars_layout.addWidget(card)
                            self._custom_var_cards[var_name] = card
                        else:
                            logger.warning("custom_vars_layout not found, cannot update card.")
            elif action == "delete":
                if var_name in self._custom_var_cards:
                    card = self._custom_var_cards.pop(var_name)
                    card.deleteLater()
        elif var_type == "env":
            if action == "add" or action == "update":
                if var_name not in self._env_var_cards:
                    if hasattr(global_vars, 'env'):
                        value = getattr(global_vars.env, var_name, None)
                        if value is not None:
                            card = self._create_env_var_row(var_name, value)
                            if self.env_vars_layout:
                                self.env_vars_layout.addWidget(card)
                                self._env_var_cards[var_name] = card
                            else:
                                logger.warning("env_vars_layout not found, cannot add card.")
            elif action == "delete":
                if var_name in self._env_var_cards:
                    card = self._env_var_cards.pop(var_name)
                    card.deleteLater()
        self._refresh_node_vars_page()

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
        layout.setSpacing(8)
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

        self.custom_vars_container = QWidget()
        self.custom_vars_layout = QVBoxLayout(self.custom_vars_container)
        self.custom_vars_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_vars_layout.setSpacing(6)
        layout.addWidget(self.custom_vars_container)
        layout.addStretch()
        self._refresh_custom_vars_page()
        return widget

    def _create_node_vars_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        title = TransparentPushButton(text="节点输出变量 (node_vars)", icon=get_icon("节点变量"),
                                      parent=self.parent_panel)
        layout.addWidget(title)
        self.node_vars_container = QWidget()
        self.node_vars_layout = QVBoxLayout(self.node_vars_container)
        self.node_vars_layout.setContentsMargins(0, 0, 0, 0)
        self.node_vars_layout.setSpacing(8)
        layout.addWidget(self.node_vars_container)
        layout.addStretch(1)
        self._refresh_node_vars_page()
        return widget

    def _create_env_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        title = TransparentPushButton(text="环境变量 (env)", icon=get_icon("环境变量"), parent=self.parent_panel)
        layout.addWidget(title)
        add_env_btn = TransparentPushButton(text="新增环境变量", parent=self.parent_panel, icon=FluentIcon.ADD)
        add_env_btn.clicked.connect(self.add_new_env_variable)
        layout.addWidget(add_env_btn)
        self.env_vars_container = QWidget()
        self.env_vars_layout = QVBoxLayout(self.env_vars_container)
        self.env_vars_layout.setContentsMargins(0, 0, 0, 0)
        self.env_vars_layout.setSpacing(6)
        layout.addWidget(self.env_vars_container)
        self._refresh_env_page()
        layout.addStretch()
        return widget

    # ========================
    # 全局变量 UI 构建（增量更新）
    # ========================
    def _refresh_custom_vars_page(self):
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return
        current_custom = set(global_vars.custom.keys()) if hasattr(global_vars, 'custom') else set()
        existing_custom = set(self._custom_var_cards.keys())
        for name in current_custom - existing_custom:
            var_obj = global_vars.custom[name]
            # 根据值的类型决定创建哪种卡片
            if isinstance(var_obj.value, dict):
                card = self._create_parameter_group_row(name, var_obj.value)
            else:
                card = self._create_dict_row(name, var_obj.value)
            self.custom_vars_layout.addWidget(card)
            self._custom_var_cards[name] = card
        for name in existing_custom - current_custom:
            card = self._custom_var_cards.pop(name)
            card.deleteLater()

    def _refresh_node_vars_page(self):
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return
        current_node_vars = set(global_vars.node_vars.keys()) if hasattr(global_vars, 'node_vars') else set()
        existing_node_vars = set(self._node_var_cards.keys())
        for name in current_node_vars - existing_node_vars:
            node_var_obj = global_vars.node_vars[name]
            card = self._create_variable_card(name, node_var_obj)
            self.node_vars_layout.addWidget(card)
            self._node_var_cards[name] = card
        for name in existing_node_vars - current_node_vars:
            card = self._node_var_cards.pop(name)
            card.deleteLater()
        for name in current_node_vars & existing_node_vars:
            node_var_obj = global_vars.node_vars[name]
            card = self._node_var_cards[name]
            if hasattr(card, 'strategy_combo'):
                combo = card.strategy_combo
                if combo.property("policy") != node_var_obj.update_policy:
                    combo.blockSignals(True)
                    combo.setProperty("policy", node_var_obj.update_policy)
                    combo.blockSignals(False)
            if hasattr(card, 'tree_widget'):
                card.tree_widget.set_data(node_var_obj.value)

    def _refresh_env_page(self):
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

    def _create_dict_row(self, name: str, value):
        """创建普通的KV变量卡片"""
        card = CardWidget(self.parent_panel)
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
                    )
                ]
            )
            menu.exec_(card.mapToGlobal(pos))

        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(show_context_menu)
        return card

    def _create_parameter_group_row(self, name: str, value):
        """创建参数组卡片"""
        card = CardWidget(self.parent_panel)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # 标题行
        title_layout = QHBoxLayout()
        name_label = BodyLabel(f"{name}:")
        title_layout.addWidget(name_label)

        # 参数组信息
        param_count = len(value) if isinstance(value, dict) else 0
        value_label = BodyLabel(f"[参数组: {param_count}个参数]")
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
                    )
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

    def _create_variable_card(self, name: str, node_var_obj):
        parts = name.split("_")
        if len(parts) == 2:
            node_name = parts[0]
            port_name = parts[1]
        else:
            if re.match(r'\d+', parts[1]):
                node_name = "_".join(parts[:2])
                port_name = "_".join(parts[2:])
            else:
                node_name = parts[0]
                port_name = "_".join(parts[1:])
        node_name = re.sub(r'_(?=\d+$)', " ", node_name)
        card = CardWidget(self.parent_panel)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(3)
        title_layout = QHBoxLayout()
        title = CaptionLabel(f"{node_name}\n{port_name}")
        title_layout.addWidget(title)
        strategy_combo = TransparentDropDownToolButton(icon=get_icon(node_var_obj.update_policy),
                                                       parent=self.parent_panel)
        strategy_combo.setProperty("policy", node_var_obj.update_policy)
        strategy_combo.setProperty("node_var_name", name)
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
        title_layout.addStretch()
        title_layout.addWidget(strategy_combo)
        del_btn = TransparentToolButton(FluentIcon.CLOSE, self.parent_panel)
        del_btn.clicked.connect(lambda _, n=name: self.delete_variable('node_vars', n))
        title_layout.addWidget(del_btn)
        layout.addLayout(title_layout)
        tree = VariableTreeWidget(node_var_obj.value, parent=self.main_window)
        tree.setMinimumHeight(80)
        tree.setMaximumHeight(120)
        layout.addWidget(tree)

        def show_context_menu(pos):
            menu = RoundMenu(parent=self.parent_panel)
            menu.addActions(
                [
                    Action(
                        FluentIcon.COPY, "复制为表达式", parent=self.parent_panel,
                        triggered=lambda: self.copy_as_expression("node_vars", name)
                    ),
                    Action(
                        FluentIcon.DELETE, "清空变量结果", parent=self.parent_panel,
                        triggered=lambda:
                        self._handle_global_variable_change("node_vars", name, "clear")
                    ),
                    Action(
                        FluentIcon.FIT_PAGE, "跳转到该节点", parent=self.parent_panel,
                        triggered=lambda: self.zoom_to_node(name)
                    )
                ]
            )
            menu.exec_(card.mapToGlobal(pos))

        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(show_context_menu)

        card.strategy_combo = strategy_combo

        def on_card_double_clicked(event):
            if event.button() == Qt.LeftButton:
                self.zoom_to_node(name)

        card.mouseDoubleClickEvent = on_card_double_clicked
        card.setCursor(Qt.PointingHandCursor)
        card.tree_widget = tree
        card.node_var_name = name
        return card

    def _create_env_var_row(self, key: str, value):
        card = CardWidget(self.parent_panel)
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
            current_val = getattr(self.main_window.global_variables.env, key, None)
            menu = RoundMenu(parent=self.parent_panel)
            menu.addAction(Action(FluentIcon.COPY, "复制为表达式", parent=self.parent_panel,
                                  triggered=lambda: self.copy_as_expression("env", key)))
            menu.addAction(Action(FluentIcon.EDIT, "编辑变量", parent=self.parent_panel,
                                  triggered=lambda: self.edit_env_variable(key, current_val)))
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
                node = self.locate_node_by_name(var_name)
                if node:
                    if hasattr(node, "refresh_node_outports"):
                        QtCore.QTimer.singleShot(0, node.refresh_node_outports)
                    if hasattr(node, "_sync_outputs_ports"):
                        QtCore.QTimer.singleShot(0, node._sync_outputs_ports)
            self._refresh_custom_vars_page()
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
                self._refresh_custom_vars_page()
                self._handle_global_variable_change("custom", name, "add")
                InfoBar.success("已添加", f"自定义变量 {name}", parent=self.main_window)

    def add_new_parameter_group(self):
        """添加新的参数组"""
        # 显示模板选择对话框
        template_dialog = TemplateSelectionDialog(
            parent=self.main_window,
            templates=self.parameter_group_templates
        )

        if template_dialog.exec():
            selected_template = template_dialog.selected_template

            if selected_template == "自定义参数组":
                # 创建自定义参数组
                self._open_parameter_group_editor("", {}, True)
            elif selected_template in self.parameter_group_templates:
                # 使用模板创建参数组
                template_data = self.parameter_group_templates[selected_template]
                group_name = selected_template
                self._open_parameter_group_editor(group_name, template_data, True)

    def _open_parameter_group_editor(self, group_name, group_data, is_new=True):
        """打开参数组编辑器"""
        dialog = ParameterGroupDialog(
            parent=self.main_window,
            group_name=group_name,
            group_data=group_data,
            is_new=is_new
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
                # 如果是编辑现有参数组且名称改变，先删除旧的
                if not is_new and group_name != new_name:
                    if hasattr(global_vars, 'custom') and group_name in global_vars.custom:
                        del global_vars.custom[group_name]
                        self._handle_global_variable_change("custom", group_name, "delete")

                # 设置新的参数组
                global_vars.set(new_name, parameters)
                self._handle_global_variable_change("custom", new_name, "add")

                # 如果用户选择了保存为模板
                if dialog.should_save_as_template():
                    self.parameter_group_templates[new_name] = parameters.copy()
                    InfoBar.success("已保存", f"参数组 {new_name} 已保存为模板", parent=self.main_window)
                else:
                    InfoBar.success("已保存", f"参数组 {new_name}", parent=self.main_window)

                # 强制刷新自定义变量页面以更新显示
                self._refresh_custom_vars_page()

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
                self._refresh_env_page()
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
            position=InfoBarPosition.TOP_RIGHT,
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
                # 如果名称改变，则发送 add 信号给新名称，否则发送 update 信号
                if new_name != var_name:
                    self._handle_global_variable_change("custom", new_name, "add")
                else:
                    self._handle_global_variable_change("custom", new_name, "update")

                InfoBar.success("已更新", f"参数组 {new_name}", parent=self.main_window)

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

    def zoom_to_node(self, var_name: str):
        found_node = self.locate_node_by_name(var_name)
        self.main_window.canvas_widget.zoom_to_nodes([found_node._view])

    def locate_node_by_name(self, var_name: str):
        """根据全局变量名定位到对应的节点"""
        parts = var_name.split("_")
        if len(parts) < 2:
            logger.warning(f"无法从变量名 '{var_name}' 解析出节点名称")
            return None
        elif len(parts) == 2:
            safe_node_name_candidate = parts[0]
        else:
            if re.match(r'\d+', parts[1]):
                safe_node_name_candidate = "_".join(parts[:2])
            else:
                safe_node_name_candidate = parts[0]
        original_name_candidate = re.sub(r'_(?=\d+$)', " ", safe_node_name_candidate)
        node_graph = self.main_window.graph
        if not node_graph:
            logger.warning("无法获取节点图实例")
            return None
        found_node = node_graph.get_node_by_name(original_name_candidate)
        if not found_node:
            logger.warning(f"未找到与变量名 '{var_name}' 对应的节点 "
                           f"(尝试名称: '{original_name_candidate}', '{safe_node_name_candidate}')")
            InfoBar.warning(
                title="未找到节点",
                content=f"无法定位到变量 '{var_name}' 对应的节点。",
                parent=self.main_window,
                position=InfoBarPosition.TOP_RIGHT
            )
            return None

        return found_node

    def handle_global_variable_change(self, var_type: str, var_name: str, action: str):
        """处理全局变量变化的信号"""
        if var_type == "node_vars":
            if action == "add" or action == "update":
                if var_name not in self._node_var_cards:
                    global_vars = self.main_window.global_variables
                    if hasattr(global_vars, 'node_vars') and var_name in global_vars.node_vars:
                        card = self._create_variable_card(var_name, global_vars.node_vars[var_name])
                        self.node_vars_layout.addWidget(card)
                        self._node_var_cards[var_name] = card
            elif action == "delete":
                if var_name in self._node_var_cards:
                    card = self._node_var_cards.pop(var_name)
                    card.deleteLater()
            elif action == "clear":
                global_vars = self.main_window.global_variables
                global_vars.clear_node_vars(var_name)
                self._refresh_node_vars_page()
        elif var_type == "custom":
            if action == "add" or action == "update":
                if var_name not in self._custom_var_cards:
                    global_vars = self.main_window.global_variables
                    if hasattr(global_vars, 'custom') and var_name in global_vars.custom:
                        value = global_vars.custom[var_name].value
                        # 检查是否是字典类型，决定创建哪种卡片
                        if isinstance(value, dict):
                            card = self._create_parameter_group_row(var_name, value)
                        else:
                            card = self._create_dict_row(var_name, value)
                        self.custom_vars_layout.addWidget(card)
                        self._custom_var_cards[var_name] = card
            elif action == "delete":
                if var_name in self._custom_var_cards:
                    card = self._custom_var_cards.pop(var_name)
                    card.deleteLater()
        elif var_type == "env":
            if action == "add" or action == "update":
                if var_name not in self._env_var_cards:
                    global_vars = self.main_window.global_variables
                    if hasattr(global_vars, 'env'):
                        value = getattr(global_vars.env, var_name, None)
                        if value is not None:
                            card = self._create_env_var_row(var_name, value)
                            self.env_vars_layout.addWidget(card)
                            self._env_var_cards[var_name] = card
            elif action == "delete":
                if var_name in self._env_var_cards:
                    card = self._env_var_cards.pop(var_name)
                    card.deleteLater()

    def add_output_to_global_var(self, main_window, node, port_name: str):
        """将输出添加到全局变量"""
        value = node._output_values.get(port_name)
        if value is None:
            InfoBar.warning(
                title="警告",
                content=f"端口 {port_name} 当前无有效输出值",
                parent=main_window,
                position=InfoBarPosition.TOP_RIGHT
            )
            return
        safe_node_name = re.sub(r'\s+', '_', node.name())
        var_name = f"{safe_node_name}_{port_name}"
        main_window.global_variables.set_output(
            node_id=safe_node_name, output_name=port_name, output_value=serialize_for_json(value)
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
            position=InfoBarPosition.TOP_RIGHT
        )

    def delete_output_from_global_var(self, main_window, node, port_name: str):
        """从全局变量中删除输出"""
        safe_node_name = re.sub(r'\s+', '_', node.name())
        main_window.global_variables.delete_output(
            node_id=safe_node_name, output_name=port_name
        )
        if hasattr(node, "refresh_node_outports"):
            QtCore.QTimer.singleShot(100, node.refresh_node_outports)
        if hasattr(node, "_sync_outputs_ports"):
            QtCore.QTimer.singleShot(100, node._sync_outputs_ports)
        self._handle_global_variable_change("node_vars", f"{safe_node_name}_{port_name}", "delete")
        InfoBar.success(
            title="成功",
            content=f"已删除全局变量：{safe_node_name}_{port_name}",
            parent=main_window,
            position=InfoBarPosition.TOP_RIGHT
        )

    def is_output_in_global_var(self, main_window, node, port_name: str):
        """判断输出是否在全局变量中"""
        safe_node_name = re.sub(r'\s+', '_', node.name())
        return main_window.global_variables.is_output_in_node_vars(safe_node_name, port_name)
