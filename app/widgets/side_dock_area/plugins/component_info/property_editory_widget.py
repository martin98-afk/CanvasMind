# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTableWidgetItem, QHeaderView,
    QFormLayout, QDialog
)
from qfluentwidgets import (
    BodyLabel, LineEdit, PushButton,
    TableWidget, ComboBox, InfoBar, FluentIcon, MessageBoxBase, SubtitleLabel,
    DoubleSpinBox, TransparentToolButton, SimpleCardWidget
)

from app.components.base import PropertyType, PropertyDefinition
from app.widgets.node_widget.longtext_dialog import LongTextEditorDialog


class PropertyEditorWidget(SimpleCardWidget):
    """属性编辑器 - 支持动态添加删除"""
    properties_changed = pyqtSignal()  # 属性改变信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self._dynamic_form_schemas = {}  # 新增：存储每个动态表单的 schema
        self._choice_configs = {}
        self._range_configs = {}
        layout = QVBoxLayout(self)
        # 属性表格
        self.table = TableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["属性名", "标签", "类型", "默认值", "选项"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # 连接itemChanged信号，区分是否是第一列（属性名）的修改
        self.table.itemChanged.connect(self._on_item_changed)
        button_layout = QHBoxLayout()
        button_layout.addWidget(BodyLabel("参数设置:"))
        add_btn = TransparentToolButton(FluentIcon.ADD, parent=self)
        add_btn.setToolTip("添加参数")
        add_btn.setFixedSize(25, 25)
        add_btn.clicked.connect(lambda: self._add_property())
        remove_btn = TransparentToolButton(FluentIcon.DELETE, parent=self)
        remove_btn.setToolTip("删除添加参数")
        remove_btn.setFixedSize(25, 25)
        remove_btn.clicked.connect(self._remove_property)
        button_layout.addWidget(add_btn)
        button_layout.addWidget(remove_btn)
        layout.addLayout(button_layout)
        layout.addWidget(self.table)

    def _on_item_changed(self, item):
        """处理表格项改变事件"""
        row = self.table.row(item)
        col = item.column()

        if col == 0:  # 属性名列被修改
            old_name = item.data(Qt.UserRole)  # 获取旧的属性名（存储在userData中）
            new_name = item.text().strip()

            if old_name and old_name != new_name:
                # 同步更新所有相关的配置字典
                self._update_config_keys(old_name, new_name)

                # 更新item的userData，记录当前属性名
                item.setData(Qt.UserRole, new_name)

        self.properties_changed.emit()

    def _update_config_keys(self, old_name, new_name):
        """当属性名改变时，更新所有相关的配置字典"""
        # 更新 choice 配置
        if old_name in self._choice_configs:
            choices = self._choice_configs.pop(old_name)
            self._choice_configs[new_name] = choices

        # 更新 range 配置
        if old_name in self._range_configs:
            range_config = self._range_configs.pop(old_name)
            self._range_configs[new_name] = range_config

        # 更新 dynamic form schema
        if old_name in self._dynamic_form_schemas:
            schema = self._dynamic_form_schemas.pop(old_name)
            self._dynamic_form_schemas[new_name] = schema

    def _remove_property(self):
        """删除选中属性"""
        selected_ranges = self.table.selectedRanges()
        if selected_ranges:
            rows = []
            for range_ in selected_ranges:
                rows.extend(range(range_.topRow(), range_.bottomRow() + 1))
            rows = sorted(set(rows), reverse=True)
            for row in rows:
                # 删除行时，同步删除相关配置
                name_item = self.table.item(row, 0)
                if name_item:
                    prop_name = name_item.text()
                    # 清除相关配置
                    self._choice_configs.pop(prop_name, None)
                    self._range_configs.pop(prop_name, None)
                    self._dynamic_form_schemas.pop(prop_name, None)
                self.table.removeRow(row)
            self.properties_changed.emit()

    def _add_property(self, prop_name: str = None, prop_def: PropertyType = None):
        """添加属性"""
        row = self.table.rowCount()
        self.table.insertRow(row)
        # 属性名
        name_item = QTableWidgetItem(prop_name if prop_name else f"prop{row + 1}")
        # 设置userData记录属性名，用于后续对比
        name_item.setData(Qt.UserRole, prop_name if prop_name else f"prop{row + 1}")
        self.table.setItem(row, 0, name_item)
        # 标签
        label_item = QTableWidgetItem(getattr(prop_def, 'label', f"属性{row + 1}"))
        self.table.setItem(row, 1, label_item)
        # 类型
        type_combo = ComboBox()
        type_combo.setStyleSheet("border: none;background: transparent; color: white;")
        type_combo.setMaxVisibleItems(6)
        for item in PropertyType:
            type_combo.addItem(item.value, userData=item)
        type_combo.setCurrentText(getattr(prop_def, 'type', 'text'))
        self.table.setCellWidget(row, 2, type_combo)
        type_combo.currentTextChanged.connect(
            lambda text: self._on_type_changed(row)
        )
        # 默认值
        default_item = QTableWidgetItem(str(getattr(prop_def, 'default', '')))
        self.table.setItem(row, 3, default_item)
        # 替换原来的"选项"列：改为"操作"列
        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)
        if getattr(prop_def, 'type', PropertyType.TEXT) == PropertyType.DYNAMICFORM:
            edit_btn = PushButton("编辑表单")
            edit_btn.clicked.connect(lambda _, r=row: self._edit_dynamic_form(r))
            action_layout.addWidget(edit_btn)
            self.table.setCellWidget(row, 4, action_widget)
        elif getattr(prop_def, 'type', PropertyType.TEXT) == PropertyType.RANGE:
            edit_btn = PushButton("配置范围")
            # 从 prop_def 获取当前值并存储
            min_val = getattr(prop_def, 'min', 0)
            max_val = getattr(prop_def, 'max', 100)
            step_val = getattr(prop_def, 'step', 1)
            # 存储到内部字典
            if prop_name:
                self._range_configs[prop_name] = {'min': min_val, 'max': max_val, 'step': step_val}
            edit_btn.clicked.connect(lambda _, r=row: self._edit_range(r))
            action_layout.addWidget(edit_btn)
            self.table.setCellWidget(row, 4, action_widget)
        elif getattr(prop_def, 'type', PropertyType.TEXT) == PropertyType.LONGTEXT:
            btn = PushButton("编辑文本")
            btn.clicked.connect(lambda _, r=row: self._edit_long_text(r))
            self.table.setCellWidget(row, 4, btn)
        elif getattr(prop_def, 'type', PropertyType.TEXT) == PropertyType.CHOICE:
            edit_btn = PushButton("配置选项")
            choices = getattr(prop_def, 'choices', [])
            # 存储到内部字典
            if prop_name:
                self._choice_configs[prop_name] = choices
            edit_btn.clicked.connect(lambda _, r=row: self._edit_choice(r))
            action_layout.addWidget(edit_btn)
            self.table.setCellWidget(row, 4, action_widget)
        else:
            options_item = QTableWidgetItem("")
            options_item.setFlags(options_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 4, options_item)

    def _on_type_changed(self, row):
        type_widget = self.table.cellWidget(row, 2)
        if not type_widget:
            return
        prop_type = type_widget.currentData() or PropertyType.TEXT
        # ✅ 关键修复：同时清除 item 和 cell widget
        self.table.setItem(row, 4, None)  # 清除文本项
        self.table.setCellWidget(row, 4, None)  # 清除按钮等 widget
        if prop_type == PropertyType.CHOICE:
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            btn = PushButton("配置选项")
            btn.clicked.connect(lambda _, r=row: self._edit_choice(r))
            action_layout.addWidget(btn)
            self.table.setCellWidget(row, 4, action_widget)
        elif prop_type == PropertyType.RANGE:
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            btn = PushButton("配置范围")
            btn.clicked.connect(lambda _, r=row: self._edit_range(r))
            action_layout.addWidget(btn)
            self.table.setCellWidget(row, 4, action_widget)
        elif prop_type == PropertyType.LONGTEXT:
            btn = PushButton("编辑文本")
            btn.clicked.connect(lambda _, r=row: self._edit_long_text(r))
            self.table.setCellWidget(row, 4, btn)
        elif prop_type == PropertyType.DYNAMICFORM:
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            btn = PushButton("编辑表单")
            btn.clicked.connect(lambda _, r=row: self._edit_dynamic_form(r))
            action_layout.addWidget(btn)
            self.table.setCellWidget(row, 4, action_widget)
        else:
            options_item = QTableWidgetItem("")
            options_item.setFlags(options_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 4, options_item)
        self.properties_changed.emit()

    def _edit_range(self, row):
        """编辑范围参数"""
        try:
            name_item = self.table.item(row, 0)
            if not name_item or not name_item.text().strip():
                InfoBar.warning("警告", "请先填写属性名", parent=self.parent, duration=2000)
                return
            prop_name = name_item.text()
            # 从内部存储获取当前值
            current_values = self._range_configs.get(prop_name, {'min': 0, 'max': 100, 'step': 1})
            dialog = RangeConfigDialog(
                current_values['min'],
                current_values['max'],
                current_values['step'],
                self.window()
            )
            if dialog.exec() == QDialog.Accepted:
                new_values = dialog.get_values()
                # 更新内部存储
                self._range_configs[prop_name] = new_values
                self.properties_changed.emit()
                InfoBar.success("成功", f"已保存范围配置: {prop_name}", parent=self.parent, duration=1500)
        except Exception as e:
            import traceback
            traceback.print_exc()
            InfoBar.error("错误", f"编辑失败: {str(e)}", parent=self.parent, duration=3000)

    def _edit_choice(self, row):
        """编辑下拉选项"""
        try:
            name_item = self.table.item(row, 0)
            if not name_item or not name_item.text().strip():
                InfoBar.warning("警告", "请先填写属性名", parent=self.parent, duration=2000)
                return
            prop_name = name_item.text()
            # 从内部存储获取当前值
            current_choices = self._choice_configs.get(prop_name, [])
            dialog = ChoiceConfigDialog(current_choices, self.window())
            if dialog.exec() == QDialog.Accepted:
                new_choices = dialog.get_choices()
                # 更新内部存储
                self._choice_configs[prop_name] = new_choices
                self.properties_changed.emit()
                InfoBar.success("成功", f"已保存下拉选项: {prop_name}", parent=self.parent, duration=1500)
        except Exception as e:
            import traceback
            traceback.print_exc()
            InfoBar.error("错误", f"编辑失败: {str(e)}", parent=self.parent, duration=3000)

    def get_properties(self, serialize=False):
        """获取属性数据（支持 DYNAMICFORM）"""
        properties = {}
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            label_item = self.table.item(row, 1)
            type_widget = self.table.cellWidget(row, 2)
            default_item = self.table.item(row, 3)
            if not (name_item and type_widget):
                continue
            prop_name = name_item.text()
            prop_type = type_widget.currentData() or PropertyType.TEXT
            default_value = default_item.text() if default_item else ""
            prop_dict = {
                "type": prop_type,
                "default": default_value,
                "label": label_item.text() if label_item else prop_name
            }
            if prop_type == PropertyType.CHOICE:
                # 从内部存储获取选项
                if prop_name in self._choice_configs:
                    prop_dict["choices"] = self._choice_configs[prop_name]
            elif prop_type == PropertyType.RANGE:
                # 从内部存储获取范围值
                if prop_name in self._range_configs:
                    prop_dict.update(self._range_configs[prop_name])
            elif prop_type == PropertyType.DYNAMICFORM:
                # 从内部存储读取 schema
                if prop_name in self._dynamic_form_schemas:
                    prop_dict["schema"] = self._dynamic_form_schemas[prop_name]
            if serialize:
                prop_dict["type"] = prop_type.value
                prop_dict = {key: value for key, value in prop_dict.items() if key in ["type", "name", "value"]}
            properties[prop_name] = prop_dict
        return properties

    def set_properties(self, properties):
        """设置属性数据（支持 DYNAMICFORM）"""
        self.table.setRowCount(0)
        self._dynamic_form_schemas.clear()  # 清空旧 schema
        self._range_configs.clear()  # 清空范围配置
        self._choice_configs.clear()  # 清空下拉选项配置
        for prop_name, prop_def in properties.items():
            if isinstance(prop_def, dict):
                prop_def = PropertyDefinition(**prop_def)
            prop_type = getattr(prop_def, 'type', PropertyType.TEXT)
            if prop_type == PropertyType.DYNAMICFORM:
                # 保存 schema 到内部存储
                self._dynamic_form_schemas[prop_name] = getattr(prop_def, 'schema', {})
            elif prop_type == PropertyType.RANGE:
                # 保存范围配置到内部存储
                self._range_configs[prop_name] = {
                    'min': getattr(prop_def, 'min', 0),
                    'max': getattr(prop_def, 'max', 100),
                    'step': getattr(prop_def, 'step', 1)
                }
            elif prop_type == PropertyType.CHOICE:
                # 保存下拉选项到内部存储
                self._choice_configs[prop_name] = getattr(prop_def, 'choices', [])
            # 调用 _add_property（它会根据类型显示"编辑表单"按钮）
            self._add_property(prop_name, prop_def)

    def _edit_dynamic_form(self, row):
        """编辑动态表单结构"""
        try:
            name_item = self.table.item(row, 0)
            if not name_item or not name_item.text().strip():
                InfoBar.warning("警告", "请先填写属性名", parent=self.parent, duration=2000)
                return
            prop_name = name_item.text()
            current_schema = self._dynamic_form_schemas.get(prop_name, {})
            dialog = DynamicFormEditorDialog(current_schema, self.window())
            if dialog.exec() == QDialog.Accepted:
                new_schema = dialog.get_schema()
                self._dynamic_form_schemas[prop_name] = new_schema
                self.properties_changed.emit()
                InfoBar.success("成功", f"已保存表单结构: {prop_name}", parent=self.parent, duration=1500)
        except Exception as e:
            import traceback
            traceback.print_exc()
            InfoBar.error("错误", f"编辑失败: {str(e)}", parent=self.parent, duration=3000)

    def _edit_long_text(self, row):
        """编辑长文本"""
        try:
            name_item = self.table.item(row, 0)
            if not name_item or not name_item.text().strip():
                InfoBar.warning("警告", "请先填写属性名", parent=self.parent, duration=2000)
                return
            default_item = self.table.item(row, 3)
            current_text = default_item.text() if default_item else ""
            dialog = LongTextEditorDialog(current_text, self.window(), self.parent)
            if dialog.exec() == QDialog.Accepted:
                new_text = dialog.text_edit.toPlainText()
                if default_item:
                    default_item.setText(new_text)
                self.properties_changed.emit()
                InfoBar.success("成功", "长文本已更新", parent=self.parent, duration=1500)
        except Exception as e:
            import traceback
            traceback.print_exc()
            InfoBar.error("错误", f"编辑失败: {str(e)}", parent=self.parent, duration=3000)


class DynamicFormEditorDialog(MessageBoxBase):
    """动态表单编辑器对话框"""

    def __init__(self, schema: dict, parent=None):
        super().__init__(parent)
        self.widget.setMinimumSize(600, 400)
        self.schema = schema or {}
        self.editor = PropertyEditorWidget(self)
        self.editor.set_properties(self.schema)
        # 标题
        self.titleLabel = SubtitleLabel("编辑动态表单结构")
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.editor)

    def get_schema(self):
        """获取编辑后的 schema"""
        return self.editor.get_properties()


class RangeConfigDialog(MessageBoxBase):
    """范围配置对话框"""

    def __init__(self, min_val=0, max_val=100, step_val=1, parent=None):
        super().__init__(parent)
        self.widget.setMinimumSize(400, 200)
        # 标题
        self.titleLabel = SubtitleLabel("配置范围参数")
        self.viewLayout.addWidget(self.titleLabel)
        # 表单布局
        form_layout = QFormLayout()
        self.min_spin = DoubleSpinBox()
        self.min_spin.setRange(-999999, 999999)
        self.min_spin.setValue(min_val)
        form_layout.addRow("最小值:", self.min_spin)
        self.max_spin = DoubleSpinBox()
        self.max_spin.setRange(-999999, 999999)
        self.max_spin.setValue(max_val)
        form_layout.addRow("最大值:", self.max_spin)
        self.step_spin = DoubleSpinBox()
        self.step_spin.setRange(0.001, 999999)
        self.step_spin.setValue(step_val)
        self.step_spin.setDecimals(3)
        form_layout.addRow("步长:", self.step_spin)
        self.viewLayout.addLayout(form_layout)

    def get_values(self):
        return {
            'min': self.min_spin.value(),
            'max': self.max_spin.value(),
            'step': self.step_spin.value()
        }


class ChoiceConfigDialog(MessageBoxBase):
    """下拉框选项配置对话框（优化版：内联输入，不弹新窗）"""

    def __init__(self, choices=None, parent=None):
        super().__init__(parent)
        self.widget.setMinimumSize(500, 350)  # 稍微增加高度以容纳输入框
        self.choices = choices or []
        # 标题
        self.titleLabel = SubtitleLabel("配置下拉选项")
        self.viewLayout.addWidget(self.titleLabel)
        # 选项列表
        self.list_widget = TableWidget()  # 使用 TableWidget (虽然名字是list，但为了保持一致)
        self.list_widget.setColumnCount(1)
        self.list_widget.setHorizontalHeaderLabels(["选项"])
        self.list_widget.setRowCount(len(self.choices))
        for i, choice in enumerate(self.choices):
            self.list_widget.setItem(i, 0, QTableWidgetItem(choice))
        self.list_widget.verticalHeader().hide()
        self.list_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.viewLayout.addWidget(self.list_widget)
        # 输入框 + 按钮布局
        input_layout = QHBoxLayout()
        self.input_line = LineEdit()
        self.input_line.setPlaceholderText("输入新选项后点击“添加”")
        self.input_line.returnPressed.connect(self._add_choice)  # 回车也可添加
        input_layout.addWidget(self.input_line)
        self.add_btn = PushButton("添加")
        self.add_btn.clicked.connect(self._add_choice)
        input_layout.addWidget(self.add_btn)
        self.viewLayout.addLayout(input_layout)
        # 删除按钮（可单独一行或与添加同行，这里单独放更清晰）
        self.remove_btn = PushButton("删除选中")
        self.remove_btn.clicked.connect(self._remove_choice)
        self.viewLayout.addWidget(self.remove_btn)

    def _add_choice(self):
        text = self.input_line.text().strip()
        if text:
            row = self.list_widget.rowCount()
            self.list_widget.insertRow(row)
            self.list_widget.setItem(row, 0, QTableWidgetItem(text))
            self.input_line.clear()
            self.input_line.setFocus()  # 保持焦点，方便连续输入

    def _remove_choice(self):
        current_row = self.list_widget.currentRow()
        if current_row >= 0:
            self.list_widget.removeRow(current_row)

    def get_choices(self):
        choices = []
        for i in range(self.list_widget.rowCount()):
            item = self.list_widget.item(i, 0)
            if item:
                choices.append(item.text())
        return choices
