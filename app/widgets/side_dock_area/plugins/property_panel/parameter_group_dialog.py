from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QListWidgetItem
from qfluentwidgets import PushButton, ListWidget, FluentIcon, InfoBar, TransparentToolButton, BodyLabel, LineEdit, \
    ToggleToolButton, SearchLineEdit

from app.widgets.dialog_widget.step_messageboxbase import StepMessageBoxBase


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
