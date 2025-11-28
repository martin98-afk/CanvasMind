# -*- coding: utf-8 -*-
import json
import re

from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QStackedWidget, QApplication, \
    QListWidgetItem, QSizePolicy
from loguru import logger
from qfluentwidgets import CardWidget, BodyLabel, PushButton, ListWidget, SegmentedWidget, \
    FluentIcon, InfoBar, InfoBarPosition, TransparentToolButton, RoundMenu, Action, TransparentPushButton, \
    TransparentDropDownToolButton, SubtitleLabel, BodyLabel, LineEdit, \
    ToggleToolButton, SearchLineEdit, SmoothScrollArea, StrongBodyLabel
from qfluentwidgets.components.widgets.card_widget import CardSeparator, SimpleCardWidget

from app.templates.global_custom_var_template import PARAMETER_TEMPLATE
from app.utils.utils import get_icon, serialize_for_json
from app.widgets.dialog_widget.custom_messagebox import CustomTwoInputDialog
from app.widgets.dialog_widget.step_messageboxbase import StepMessageBoxBase
from app.widgets.tree_widget.variable_tree import VariableTreeWidget


class ParameterGroupDialog(StepMessageBoxBase):
    """参数组编辑对话框 - 使用 StepMessageBoxBase"""

    def __init__(self, parent=None, group_name="", group_data=None, is_new=True, templates=None):
        # 定义步骤
        steps = [
            {"name": "template_selection", "title": "选择模板"},
            {"name": "parameter_edit", "title": "编辑参数"}
        ]
        super().__init__(parent=parent, steps=steps)

        self.group_name = group_name
        self.group_data = group_data or {}
        self.is_new = is_new
        self.templates = templates or {}
        self.selected_template_name = None

        # 设置对话框大小
        self.widget.setFixedSize(700, 600)

        # --- 页面1: 模板选择 ---
        self.template_selection_page = QWidget()
        self._setup_template_selection_page()

        # --- 页面2: 参数编辑 ---
        self.param_edit_page = QWidget()
        self._setup_param_edit_page()

        # 添加页面到堆叠布局
        self.add_page(self.template_selection_page)
        self.add_page(self.param_edit_page)

        # 根据 is_new 决定起始页面
        if not is_new:
            # 如果是编辑现有组，则跳到参数编辑页
            self._current_step_index = 1
            self.page_stack.setCurrentIndex(1)
            # 加载现有数据
            self._load_parameters_for_edit(group_name, group_data)

        # 更新按钮状态
        self._update_button_states()

        # 隐藏不需要的按钮（根据第一步的逻辑）
        if self.is_new:
            self.backButton.hide()
        else:
            # 编辑模式下，第一步是参数编辑
            self.backButton.hide()
            self.nextButton.hide()  # 或者可以隐藏 next，只显示 ok
            # 为了保持一致性，我们保留 next/ok 切换逻辑
            self._update_button_states()  # 这会根据 _current_step_index (1) 隐藏 next，显示 ok

    def _setup_template_selection_page(self):
        """设置模板选择界面"""
        layout = QVBoxLayout(self.template_selection_page)
        # 搜索框
        self.search_box = SearchLineEdit(self.template_selection_page)
        self.search_box.setPlaceholderText("搜索模板...")
        self.search_box.textChanged.connect(self._filter_templates)
        layout.addWidget(self.search_box)

        # 模板列表
        self.template_list = ListWidget(self.template_selection_page)
        self.template_list.setMinimumHeight(200)

        # 填充模板列表
        self.all_template_items = []
        for template_name in self.templates.keys():
            item = QListWidgetItem(template_name)
            self.template_list.addItem(item)
            self.all_template_items.append(item)

        # 添加自定义项
        custom_item = QListWidgetItem("自定义参数组")
        self.template_list.addItem(custom_item)
        self.all_template_items.append(custom_item)

        # 设置点击事件
        self.template_list.itemClicked.connect(self._on_template_selected)
        layout.addWidget(self.template_list)

    def _setup_param_edit_page(self):
        """设置参数编辑界面"""
        layout = QVBoxLayout(self.param_edit_page)

        # 参数组名称输入
        self.hbox_layout = QHBoxLayout()
        self.hbox_layout.setContentsMargins(0, 0, 30, 0)
        self.name_edit = LineEdit()
        self.name_edit.setPlaceholderText("请输入参数组名称")
        if self.group_name:
            self.name_edit.setText(self.group_name)
        self.hbox_layout.addWidget(BodyLabel("参数组名称：", self.param_edit_page))
        self.hbox_layout.addWidget(self.name_edit, 1)

        self.save_as_template = ToggleToolButton(FluentIcon.SAVE_AS, self.param_edit_page)
        self.save_as_template.setChecked(False)
        self.save_as_template.setToolTip("是否保存为参数模板")
        self.hbox_layout.addStretch()
        self.hbox_layout.addWidget(self.save_as_template)

        layout.addLayout(self.hbox_layout)

        # 参数编辑区域
        self.params_list = ListWidget()
        self.params_list.setMinimumHeight(200)
        layout.addWidget(self.params_list)

        # 添加参数按钮
        self.add_param_btn = PushButton("添加参数", self.param_edit_page)
        self.add_param_btn.clicked.connect(self.add_parameter_row)
        layout.addWidget(self.add_param_btn)

    def _filter_templates(self, text):
        """过滤模板列表"""
        for item in self.all_template_items:
            item.setHidden(text.lower() not in item.text().lower())

    def _on_template_selected(self, item):
        """模板选择响应"""
        self.selected_template_name = item.text()

    def validate_current_step(self) -> bool:
        """重写父类方法，验证当前步骤"""
        current_index = self.current_step_index()
        if current_index == 0:  # 模板选择步骤
            # 验证是否已选择模板
            if self.selected_template_name is None:
                InfoBar.warning("未选择模板", "请选择一个模板或选择自定义", parent=self, duration=2000)
                return False
            return True
        # 其他步骤的验证可以在这里添加
        return super().validate_current_step()

    def validate_final_data(self) -> bool:
        """重写父类方法，验证最终数据"""
        # 验证参数组名称
        name = self.name_edit.text().strip()
        if not name:
            InfoBar.warning("无效名称", "参数组名称不能为空", parent=self, duration=2000)
            return False
        # 验证参数列表不为空
        params = self.get_parameters()
        if not params:
            InfoBar.warning("无效参数", "参数组至少需要一个参数", parent=self, duration=2000)
            return False
        return True

    def _load_parameters_for_edit(self, name, data):
        """加载参数数据到编辑界面"""
        # 清空现有参数
        while self.params_list.count():
            item = self.params_list.takeItem(0)
            widget = self.params_list.itemWidget(item)
            if widget:
                widget.deleteLater()

        # 设置名称（如果是模板，则使用模板名作为默认名称）
        if name and not self.name_edit.text():
            self.name_edit.setText(name)

        # 添加参数行
        if data:
            for key, value in data.items():
                self.add_parameter_row(key, str(value))
        else:
            # 如果没有数据（自定义），添加一个空行
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

        delete_btn = TransparentToolButton(FluentIcon.DELETE, self.param_edit_page)
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

    # 重写 _on_next_clicked 以处理模板选择后的数据加载
    def _on_next_clicked(self):
        if self.current_step_index() == 0:  # 从模板选择页到参数编辑页
            if self.selected_template_name == "自定义参数组":
                self._load_parameters_for_edit("", {})
            elif self.selected_template_name in self.templates:
                self._load_parameters_for_edit(self.selected_template_name, self.templates[self.selected_template_name])
        super()._on_next_clicked()


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
            self._refresh_content()
            return

        title = SubtitleLabel("🌍 全局变量")
        self.parent_layout.addWidget(title)

        segment_layout = QHBoxLayout(self.parent_panel)
        segment_layout.setContentsMargins(5, 5, 5, 5)
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
        self.main_window.global_variables_changed.emit(var_type, var_name, action)
        # 重新获取 global_vars 对象，以防信号处理延迟导致的数据不一致
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            logger.warning(
                f"Global variables object not found in main_window when handling {action} for {var_type}.{var_name}")
            return

        if var_type == "node_vars":
            if action == "clear":
                global_vars.clear_node_vars(var_name)
            self._refresh_node_vars_page()
        elif var_type == "custom":
            if action == "update":
                # 处理更新：删除旧卡片，根据新值类型创建新卡片并放入对应布局
                if var_name in self._custom_var_cards:
                    old_card = self._custom_var_cards.pop(var_name)
                    old_card.deleteLater()
                    # 现在当作新增来处理
                    if hasattr(global_vars, 'custom') and var_name in global_vars.custom:
                        new_value = global_vars.custom[var_name].value
                        if isinstance(new_value, dict):
                            new_card = self._create_parameter_group_row(var_name, new_value)
                            layout_to_use = self.custom_params_layout
                        else:
                            new_card = self._create_dict_row(var_name, new_value)
                            layout_to_use = self.custom_kvs_layout
                        layout_to_use.addWidget(new_card)
                        self._custom_var_cards[var_name] = new_card
                        # 更新分割线可见性
                        has_params = self.custom_params_layout.count() > 0
                        has_kvs = self.custom_kvs_layout.count() > 0
                        self.custom_separator.setVisible(has_params and has_kvs)
                    else:
                        logger.warning(f"Variable {var_name} not found in global_vars.custom during update.")
            else:
                self._refresh_custom_vars_page()
        elif var_type == "env":
            self._refresh_env_page()

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

        # --- 分类容器 ---
        self.custom_container = QWidget()
        self.custom_container.setStyleSheet("background: transparent; border: none;")
        self.custom_layout = QVBoxLayout(self.custom_container)
        self.custom_layout.setContentsMargins(5, 5, 5, 5)

        self.custom_params_container = QWidget()  # 参数组容器
        self.custom_params_layout = QVBoxLayout(self.custom_params_container)
        self.custom_params_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_params_layout.setSpacing(6)

        self.custom_kvs_container = QWidget()  # KV变量容器
        self.custom_kvs_layout = QVBoxLayout(self.custom_kvs_container)
        self.custom_kvs_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_kvs_layout.setSpacing(6)

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
        title = TransparentPushButton(text="节点输出变量 (node_vars)", icon=get_icon("节点变量"),
                                      parent=self.parent_panel)
        layout.addWidget(title)
        self.node_vars_container = QWidget()
        self.node_vars_container.setStyleSheet("background: transparent; border: none;")
        self.node_vars_layout = QVBoxLayout(self.node_vars_container)
        self.node_vars_layout.setContentsMargins(10, 10, 10, 10)
        self.node_vars_layout.setSpacing(8)
        node_scroll = self.parent_panel.set_scrollbar(self.node_vars_container)
        layout.addWidget(node_scroll, 1)
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
        self.env_vars_container.setStyleSheet("background: transparent; border: none;")
        self.env_vars_layout = QVBoxLayout(self.env_vars_container)
        self.env_vars_layout.setContentsMargins(5, 5, 5, 5)
        self.env_vars_layout.setSpacing(6)
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
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return

        current_node_vars = set(global_vars.node_vars.keys()) if hasattr(global_vars, 'node_vars') else set()
        existing_node_vars = set(self._node_var_cards.keys())

        # 重构逻辑：按节点分组
        current_node_groups = {}
        for var_name in current_node_vars:
            node_name = self._extract_node_name(var_name)  # 使用辅助函数提取节点名
            if node_name not in current_node_groups:
                current_node_groups[node_name] = []
            current_node_groups[node_name].append((var_name, global_vars.node_vars[var_name]))

        # 清空现有布局
        while self.node_vars_layout.count():
            child = self.node_vars_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # 重新创建并排序分组
        sorted_node_names = sorted(current_node_groups.keys())
        for node_name in sorted_node_names:
            group_items = sorted(current_node_groups[node_name], key=lambda x: x[0])  # 按 var_name 排序端口
            group_card = self._create_node_group_card(node_name, group_items)
            self.node_vars_layout.addWidget(group_card)
        self.node_vars_layout.addStretch(1)
        # 由于完全重建，现有卡片缓存也需要更新
        for card in self._node_var_cards.values():
            card.deleteLater()
        self._node_var_cards.clear()

    def _extract_node_name(self, var_name: str):
        """从 var_name 提取节点名，与 locate_node_by_name 逻辑一致"""
        parts = var_name.split("_")
        if len(parts) == 2:
            safe_node_name_candidate = parts[0]
        else:
            if re.match(r'\d+', parts[1]):
                safe_node_name_candidate = "_".join(parts[:2])
            else:
                safe_node_name_candidate = parts[0]
        original_name_candidate = re.sub(r'_(?=\d+$)', " ", safe_node_name_candidate)
        return original_name_candidate

    def _create_node_group_card(self, node_name: str, node_var_items: list):
        """创建一个包含该节点所有端口变量的分组卡片"""
        group_card = CardWidget(self.parent_panel)
        group_layout = QVBoxLayout(group_card)
        group_layout.setContentsMargins(8, 8, 8, 8)
        group_layout.setSpacing(4)

        # 节点标题
        node_title_layout = QHBoxLayout()
        node_title = StrongBodyLabel(node_name)
        node_title_layout.addWidget(node_title)

        group_layout.addLayout(node_title_layout)

        group_layout.addWidget(CardSeparator(group_card))

        # 添加该节点的所有端口变量卡片
        for var_name, node_var_obj in node_var_items:
            port_card = self._create_variable_card(var_name, node_var_obj)
            group_layout.addWidget(port_card)

        # 为分组卡片添加跳转功能
        def on_group_card_double_clicked(event):
            if event.button() == Qt.LeftButton:
                self.zoom_to_node_by_name(node_name)

        group_card.mouseDoubleClickEvent = on_group_card_double_clicked
        group_card.setCursor(Qt.PointingHandCursor)
        group_layout.addStretch()
        return group_card

    def zoom_to_node_by_name(self, node_name: str):
        """根据节点名称跳转到节点"""
        node_graph = self.main_window.graph
        if not node_graph:
            logger.warning("无法获取节点图实例")
            return None
        found_node = node_graph.get_node_by_name(node_name)
        if not found_node:
            logger.warning(f"未找到节点: '{node_name}'")
            InfoBar.warning(
                title="未找到节点",
                content=f"无法定位到节点 '{node_name}'。",
                parent=self.main_window,
                position=InfoBarPosition.TOP_RIGHT
            )
            return None
        self.main_window.canvas_widget.zoom_to_nodes([found_node._view])

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
        card = SimpleCardWidget(self.parent_panel)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(3)
        title_layout = QHBoxLayout()
        title = BodyLabel(f"端口: {port_name}")
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
        layout.addWidget(CardSeparator(self.parent_panel))
        tree = VariableTreeWidget(node_var_obj.value, parent=self.main_window)
        tree.setMinimumHeight(80)
        tree.setMaximumHeight(120)
        layout.addWidget(tree, 1)
        layout.addWidget(CardSeparator(self.parent_panel))

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
            current_val = self.main_window.global_variables.get(f"env.{key}")
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
        dialog = ParameterGroupDialog(
            parent=self.main_window,
            templates=self.parameter_group_templates
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
                if new_name in global_vars.custom:
                    InfoBar.warning("已存在", f"参数组 {new_name} 已存在", parent=self.main_window)
                    return
                # 设置新的参数组
                global_vars.set(new_name, parameters)
                self._handle_global_variable_change("custom", new_name, "add")

                # 如果用户选择了保存为模板
                if dialog.should_save_as_template():
                    self.parameter_group_templates[new_name] = parameters.copy()
                    InfoBar.success("已保存", f"参数组 {new_name} 已保存为模板", parent=self.main_window)
                else:
                    InfoBar.success("已保存", f"参数组 {new_name}", parent=self.main_window)

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

        # 显示合并后的参数组编辑对话框，传入现有数据
        dialog = ParameterGroupDialog(
            parent=self.main_window,
            group_name=var_name,
            group_data=current_value,
            is_new=False,
            templates=self.parameter_group_templates
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
            node_id=safe_node_name, output_name=port_name, output_value=value
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