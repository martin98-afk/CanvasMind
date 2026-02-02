# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout, QTableWidgetItem, QHeaderView,
    QFormLayout, QDialog, QSizePolicy, QWidget
)
from qfluentwidgets import (
    LineEdit, PushButton,
    TableWidget, ComboBox, InfoBar, FluentIcon, MessageBoxBase, SubtitleLabel,
    DoubleSpinBox, TransparentToolButton, SwitchButton, EditableComboBox, Slider, CompactSpinBox,
    CompactDoubleSpinBox
)

from app.components.base import PropertyType, PropertyDefinition
from app.widgets.node_widget.propeprty_widgets.longtext_dialog import LongTextEditorDialog
from app.widgets.side_dock_area.plugins.component_info.config_table import ConfigTableSpace


class PropertyEditorWidget(ConfigTableSpace):
    properties_changed = pyqtSignal()

    def __init__(self, parent=None):
        self.parent = parent
        self.property_descriptions = {}
        self._dynamic_form_schemas = {}
        self._choice_configs = {}
        self._range_configs = {}
        # 6 列：属性名、标签、类型、默认值、选项、操作（删除由基类处理）
        labels = ["属性名", "标签", "类型", "默认值", "选项"]
        super().__init__(column_labels=labels, parent=parent)

        # 覆盖基类信号
        self.dataChanged.connect(self.properties_changed)

        # 标志：抑制中间变更
        self._batch_updating = False

    def _generate_unique_key(self, base: str = "prop") -> str:
        existing = self._get_existing_keys()
        if base not in existing:
            return base
        i = 1
        while f"{base}{i}" in existing:
            i += 1
        return f"{base}{i}"

    def _fill_row_content(self, row: int):
        # 此方法用于 add_property() 无参数时
        self._add_property_row(row, prop_name=f"prop{row + 1}")

    def _add_property_row(self, row: int, prop_name: str, prop_def=None):
        # 第0列已在基类设置为 prop_name，我们覆盖它并加 UserRole
        name_item = self.table.item(row, 0)
        name_item.setText(prop_name)
        name_item.setData(Qt.UserRole, prop_name)
        name_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        # 第1列：标签
        label = getattr(prop_def, 'label', f"属性{row + 1}")
        label_item = self.table.item(row, 1)
        if label_item:
            label_item.setText(label)
        else:
            label_item = QTableWidgetItem(label)
            label_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.table.setItem(row, 1, label_item)

        # 第2列：类型 ComboBox
        type_combo = ComboBox()
        type_combo.setStyleSheet("border: none; background: transparent; color: white;")
        type_combo.setFixedHeight(28)
        for item in PropertyType:
            type_combo.addItem(item.value, userData=item)
        current_type = getattr(prop_def, 'type', PropertyType.TEXT)
        type_combo.setCurrentText(current_type.value)
        self.table.setCellWidget(row, 2, type_combo)
        type_combo.currentTextChanged.connect(
            lambda: self._on_type_changed(row)
        )

        # 第3列：默认值
        default_val = getattr(prop_def, 'default', '')
        self._update_default_value_widget(row, current_type, prop_name, default_val)

        # 第4列：操作（配置按钮）
        self._update_action_widget(row, current_type, prop_name)

    def _add_property(self, prop_name: str = None, prop_def=None):
        self._batch_updating = True

        row = self.table.rowCount()
        self.table.insertRow(row)

        # 第0列：名称（带 UserRole）
        name = prop_name if prop_name else self._generate_unique_key()
        name_item = QTableWidgetItem(name)
        name_item.setData(Qt.UserRole, name)
        name_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.table.setItem(row, 0, name_item)

        # 构造其余列
        self._add_property_row(row, name, prop_def)

        # 删除按钮（由基类处理，但我们需重新设置，因为基类只放按钮）
        delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
        delete_btn.setFixedSize(24, 24)
        delete_btn.setToolTip("删除此属性")
        delete_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        delete_btn.clicked.connect(self._on_delete_button_clicked)
        self.table.setCellWidget(row, self.table.columnCount() - 1, delete_btn)

        self._batch_updating = False
        self.properties_changed.emit()

    def _on_delete_button_clicked(self):
        btn = self.sender()
        if not btn:
            return
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, self.table.columnCount() - 1) is btn:
                name_item = self.table.item(row, 0)
                if name_item:
                    prop_name = name_item.text()
                    self._choice_configs.pop(prop_name, None)
                    self._range_configs.pop(prop_name, None)
                    self._dynamic_form_schemas.pop(prop_name, None)
                self.table.removeRow(row)
                self.properties_changed.emit()
                return

    def _on_item_changed_guarded(self, item):
        if self._batch_updating:
            return
        self._on_item_changed(item)

    def _on_item_changed(self, item):
        row = self.table.row(item)
        col = item.column()
        if col == 0:
            old_name = item.data(Qt.UserRole)
            new_name = item.text().strip()
            if old_name and old_name != new_name:
                self._update_config_keys(old_name, new_name)
                item.setData(Qt.UserRole, new_name)
        self.properties_changed.emit()

    def _update_config_keys(self, old_name, new_name):
        if old_name in self._choice_configs:
            self._choice_configs[new_name] = self._choice_configs.pop(old_name)
        if old_name in self._range_configs:
            self._range_configs[new_name] = self._range_configs.pop(old_name)
        if old_name in self._dynamic_form_schemas:
            self._dynamic_form_schemas[new_name] = self._dynamic_form_schemas.pop(old_name)

    # === 以下方法保持不变（从你原代码复制）===
    def _get_default_value_from_widget(self, row: int):
        widget = self.table.cellWidget(row, 3)
        if isinstance(widget, (EditableComboBox, ComboBox)):
            return widget.currentText()
        elif isinstance(widget, (CompactSpinBox, CompactDoubleSpinBox)):
            return str(widget.value())
        elif hasattr(widget, 'switch'):
            return str(widget.switch.isChecked())
        elif isinstance(widget, LineEdit):
            return widget.text()
        elif hasattr(widget, 'slider') and hasattr(widget, 'value_edit'):
            try:
                return widget.value_edit.text()
            except:
                val = widget.slider.value()
                float_val = val / widget.factor
                if widget.max_dec > 0:
                    float_val = round(float_val, widget.max_dec)
                return str(float_val)
        else:
            item = self.table.item(row, 3)
            return item.text() if item else ""

    def _adjust_line_edit_width(self, line_edit, max_width=120, min_width=50):
        text = line_edit.text() or "0"
        fm = line_edit.fontMetrics()
        text_width = fm.horizontalAdvance(text) + 10
        width = max(min_width, min(max_width, text_width))
        line_edit.setFixedWidth(width)

    def _update_default_value_widget(self, row: int, prop_type: PropertyType, prop_name: str = None, default_value=''):
        self.table.setCellWidget(row, 3, None)
        if prop_type == PropertyType.CHOICE:
            combo = EditableComboBox()
            combo.setStyleSheet("color: white; background: transparent; border: none;")
            choices = self._choice_configs.get(prop_name, [])
            combo.addItems(choices)
            combo.setCurrentText(default_value)
            combo.setFixedHeight(28)
            combo.currentTextChanged.connect(self.properties_changed.emit)
            self.table.setCellWidget(row, 3, combo)
        elif prop_type == PropertyType.VARIABLE:
            combo = ComboBox()
            combo.setFixedHeight(28)
            combo.setStyleSheet("color: white; background: transparent; border: none;")
            combo.addItems(["全局变量", "画布节点", "导出项目", "MCP工具", "HTTP服务"])
            combo.setCurrentText(default_value)
            combo.currentTextChanged.connect(self.properties_changed.emit)
            self.table.setCellWidget(row, 3, combo)
        elif prop_type == PropertyType.RANGE:
            config = self._range_configs.get(prop_name, {'min': 0, 'max': 100, 'step': 1})
            min_val = config.get('min', 0)
            max_val = config.get('max', 100)
            step = config.get('step', 1)

            def _decimals(x):
                s = str(x)
                if '.' in s:
                    return len(s.split('.')[-1])
                return 0

            max_dec = max(_decimals(min_val), _decimals(max_val), _decimals(step))
            factor = 10 ** max_dec if max_dec > 0 else 1
            int_min = int(round(min_val * factor))
            int_max = int(round(max_val * factor))
            int_step = max(1, int(round(step * factor)))

            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            slider = Slider(Qt.Horizontal)
            slider.setRange(int_min, int_max)
            slider.setSingleStep(int_step)
            value_edit = LineEdit()
            value_edit.setFixedHeight(28)
            value_edit.setStyleSheet("color: white; background: transparent; border: 1px solid #555555; border-radius: 4px")
            layout.addWidget(slider, 1)
            layout.addWidget(value_edit)
            try:
                current_float = float(default_value) if default_value not in (None, '') else min_val
                current_float = max(min_val, min(max_val, current_float))
                current_int = int(round(current_float * factor))
                slider.setValue(current_int)
                display_str = f"{current_float:.{max_dec}f}" if max_dec > 0 else str(int(current_float))
                value_edit.setText(display_str)
            except (ValueError, TypeError):
                slider.setValue(int_min)
                display_str = f"{min_val:.{max_dec}f}" if max_dec > 0 else str(int(min_val))
                value_edit.setText(display_str)
            # 居中对齐
            value_edit.setAlignment(Qt.AlignCenter)
            self._adjust_line_edit_width(value_edit, max_width=100, min_width=40)
            value_edit.textChanged.connect(
                lambda: self._adjust_line_edit_width(value_edit, max_width=100, min_width=40)
            )

            def on_slider_changed(val):
                float_val = val / factor
                display_str = f"{float_val:.{max_dec}f}" if max_dec > 0 else str(int(float_val))
                value_edit.setText(display_str)
                self.properties_changed.emit()
            slider.valueChanged.connect(on_slider_changed)

            def on_line_edit_finished():
                text = value_edit.text().strip()
                if not text:
                    return
                try:
                    user_val = float(text)
                    user_val = max(min_val, min(max_val, user_val))
                    int_val = int(round(user_val * factor))
                    slider.setValue(int_val)
                    display_str = f"{user_val:.{max_dec}f}" if max_dec > 0 else str(int(user_val))
                    value_edit.setText(display_str)
                    self.properties_changed.emit()
                except ValueError:
                    current_float = slider.value() / factor
                    display_str = f"{current_float:.{max_dec}f}" if max_dec > 0 else str(int(current_float))
                    value_edit.setText(display_str)
            value_edit.editingFinished.connect(on_line_edit_finished)

            container.setFixedHeight(28)
            self.table.setCellWidget(row, 3, container)
            container.slider = slider
            container.factor = factor
            container.max_dec = max_dec
            container.value_edit = value_edit
        elif prop_type == PropertyType.BOOL:
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            switch = SwitchButton(parent=container)
            switch._offText = switch.tr("False")
            switch._onText = switch.tr("True")
            checked = default_value if isinstance(default_value, bool) else str(default_value).lower() in ("true", "1", "yes", "on")
            switch.setChecked(checked)
            switch.checkedChanged.connect(self.properties_changed.emit)
            layout.addStretch()
            layout.addWidget(switch)
            layout.addStretch()
            container.setFixedHeight(28)
            self.table.setCellWidget(row, 3, container)
            container.switch = switch
        elif prop_type == PropertyType.INT:
            spinBox = CompactSpinBox()
            spinBox.setFixedHeight(28)
            spinBox.setStyleSheet("color: white; background: transparent; border: none;")
            spinBox.setRange(-10000000, 10000000)
            spinBox.setValue(int(float(default_value)) if default_value not in (None, '') else 0)
            spinBox.valueChanged.connect(self.properties_changed.emit)
            self.table.setCellWidget(row, 3, spinBox)
        elif prop_type == PropertyType.FLOAT:
            spinBox = CompactDoubleSpinBox()
            spinBox.setFixedHeight(28)
            spinBox.setStyleSheet("color: white; background: transparent; border: none;")
            spinBox.setRange(-10000000, 10000000)
            spinBox.setValue(float(default_value) if default_value not in (None, '') else 0.0)
            spinBox.valueChanged.connect(self.properties_changed.emit)
            self.table.setCellWidget(row, 3, spinBox)
        elif prop_type == PropertyType.DYNAMICFORM:
            pass
        else:
            edit = LineEdit()
            edit.setStyleSheet("color: white; background: transparent; border: none;")
            edit.setText(str(default_value) if default_value not in (None, '') else "")
            edit.textChanged.connect(self.properties_changed.emit)
            edit.setFixedHeight(28)
            self.table.setCellWidget(row, 3, edit)

    def _update_action_widget(self, row, prop_type, prop_name=None):
        self.table.setCellWidget(row, 4, None)
        if prop_type == PropertyType.CHOICE:
            btn = PushButton("配置选项")
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _, r=row: self._edit_choice(r))
            self.table.setCellWidget(row, 4, btn)
        elif prop_type == PropertyType.RANGE:
            btn = PushButton("配置范围")
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _, r=row: self._edit_range(r))
            self.table.setCellWidget(row, 4, btn)
        elif prop_type == PropertyType.LONGTEXT:
            btn = PushButton("编辑文本")
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _, r=row: self._edit_long_text(r))
            self.table.setCellWidget(row, 4, btn)
        elif prop_type == PropertyType.DYNAMICFORM:
            btn = PushButton("编辑表单")
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _, r=row: self._edit_dynamic_form(r))
            self.table.setCellWidget(row, 4, btn)
        else:
            empty_item = QTableWidgetItem("")
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemIsEditable)
            empty_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.table.setItem(row, 4, empty_item)

    def _on_type_changed(self, row):
        type_widget = self.table.cellWidget(row, 2)
        if not type_widget:
            return
        prop_type = type_widget.currentData() or PropertyType.TEXT
        name_item = self.table.item(row, 0)
        prop_name = name_item.text() if name_item else None
        current_default = self._get_default_value_from_widget(row)
        self._update_action_widget(row, prop_type, prop_name)
        self._update_default_value_widget(row, prop_type, prop_name, current_default)
        self.properties_changed.emit()

    def _edit_range(self, row):
        try:
            name_item = self.table.item(row, 0)
            if not name_item or not name_item.text().strip():
                InfoBar.warning("警告", "请先填写属性名", parent=self.parent, duration=2000)
                return
            prop_name = name_item.text()
            current_values = self._range_configs.get(prop_name, {'min': 0, 'max': 100, 'step': 1})
            dialog = RangeConfigDialog(
                current_values['min'],
                current_values['max'],
                current_values['step'],
                self.window()
            )
            if dialog.exec() == QDialog.Accepted:
                new_values = dialog.get_values()
                self._range_configs[prop_name] = new_values
                if self.table.cellWidget(row, 2).currentData() == PropertyType.RANGE:
                    self._update_default_value_widget(row, PropertyType.RANGE, prop_name,
                                                      self._get_default_value_from_widget(row))
                self.properties_changed.emit()
                InfoBar.success("成功", f"已保存范围配置: {prop_name}", parent=self.parent, duration=1500)
        except Exception as e:
            import traceback
            traceback.print_exc()
            InfoBar.error("错误", f"编辑失败: {str(e)}", parent=self.parent, duration=3000)

    def _edit_choice(self, row):
        try:
            name_item = self.table.item(row, 0)
            if not name_item or not name_item.text().strip():
                InfoBar.warning("警告", "请先填写属性名", parent=self.parent, duration=2000)
                return
            prop_name = name_item.text()
            current_choices = self._choice_configs.get(prop_name, [])
            dialog = ChoiceConfigDialog(current_choices, self.window())
            if dialog.exec() == QDialog.Accepted:
                new_choices = dialog.get_choices()
                self._choice_configs[prop_name] = new_choices
                if self.table.cellWidget(row, 2).currentData() == PropertyType.CHOICE:
                    self._update_default_value_widget(row, PropertyType.CHOICE, prop_name,
                                                      self._get_default_value_from_widget(row))
                self.properties_changed.emit()
                InfoBar.success("成功", f"已保存下拉选项: {prop_name}", parent=self.parent, duration=1500)
        except Exception as e:
            import traceback
            traceback.print_exc()
            InfoBar.error("错误", f"编辑失败: {str(e)}", parent=self.parent, duration=3000)

    def _edit_dynamic_form(self, row):
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
        try:
            name_item = self.table.item(row, 0)
            if not name_item or not name_item.text().strip():
                InfoBar.warning("警告", "请先填写属性名", parent=self.parent, duration=2000)
                return
            current_text = self._get_default_value_from_widget(row)
            dialog = LongTextEditorDialog(current_text, self.window(), self.parent)
            if dialog.exec() == QDialog.Accepted:
                new_text = dialog.text_edit.toPlainText()
                widget = self.table.cellWidget(row, 3)
                if isinstance(widget, LineEdit):
                    widget.setText(new_text)
                self.properties_changed.emit()
                InfoBar.success("成功", "长文本已更新", parent=self.parent, duration=1500)
        except Exception as e:
            import traceback
            traceback.print_exc()
            InfoBar.error("错误", f"编辑失败: {str(e)}", parent=self.parent, duration=3000)

    def get_properties(self, serialize=False):
        properties = {}
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            label_item = self.table.item(row, 1)
            type_widget = self.table.cellWidget(row, 2)
            if not (name_item and type_widget):
                continue
            prop_name = name_item.text()
            prop_type = type_widget.currentData() or PropertyType.TEXT
            default_value = self._get_default_value_from_widget(row)
            prop_dict = {
                "type": prop_type,
                "default": default_value,
                "label": label_item.text() if label_item else prop_name
            }
            if prop_type == PropertyType.CHOICE:
                if prop_name in self._choice_configs:
                    prop_dict["choices"] = self._choice_configs[prop_name]
            elif prop_type == PropertyType.RANGE:
                if prop_name in self._range_configs:
                    prop_dict.update(self._range_configs[prop_name])
            elif prop_type == PropertyType.DYNAMICFORM:
                if prop_name in self._dynamic_form_schemas:
                    prop_dict["schema"] = self._dynamic_form_schemas[prop_name]
            if serialize:
                prop_dict["type"] = prop_type.value
            if prop_name in self.property_descriptions:
                prop_dict["description"] = self.property_descriptions[prop_name]
            properties[prop_name] = prop_dict
        return properties

    def set_properties(self, properties):
        self.property_descriptions.clear()
        self.table.setRowCount(0)
        self._dynamic_form_schemas.clear()
        self._range_configs.clear()
        self._choice_configs.clear()
        for prop_name, prop_def in properties.items():
            if isinstance(prop_def, dict):
                prop_def = PropertyDefinition(**prop_def)
            prop_type = getattr(prop_def, 'type', PropertyType.TEXT)
            if prop_type == PropertyType.DYNAMICFORM:
                self._dynamic_form_schemas[prop_name] = getattr(prop_def, 'schema', {})
            elif prop_type == PropertyType.RANGE:
                self._range_configs[prop_name] = {
                    'min': getattr(prop_def, 'min', 0),
                    'max': getattr(prop_def, 'max', 100),
                    'step': getattr(prop_def, 'step', 1)
                }
            elif prop_type == PropertyType.CHOICE:
                self._choice_configs[prop_name] = getattr(prop_def, 'choices', [])
            if getattr(prop_def, 'description', ""):
                self.property_descriptions[prop_name] = getattr(prop_def, 'description', 0)
            self._add_property(prop_name, prop_def)

    def add_property(self):
        self._add_property()

# ==================== Dialogs ====================

class DynamicFormEditorDialog(MessageBoxBase):
    def __init__(self, schema: dict, parent=None):
        super().__init__(parent)
        self.widget.setMinimumSize(800, 600)
        self.schema = schema or {}
        self.editor = PropertyEditorWidget(self)
        self.editor.set_properties(self.schema)
        self.titleLabel = SubtitleLabel("编辑动态表单结构")
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.editor)

    def get_schema(self):
        return self.editor.get_properties()


class RangeConfigDialog(MessageBoxBase):
    def __init__(self, min_val=0, max_val=100, step_val=1, parent=None):
        super().__init__(parent)
        self.widget.setMinimumSize(400, 200)
        self.titleLabel = SubtitleLabel("配置范围参数")
        self.viewLayout.addWidget(self.titleLabel)
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
    def __init__(self, choices=None, parent=None):
        super().__init__(parent)
        self.widget.setMinimumSize(500, 350)
        self.choices = choices or []
        self.titleLabel = SubtitleLabel("配置下拉选项")
        self.viewLayout.addWidget(self.titleLabel)
        self.list_widget = TableWidget()
        self.list_widget.setColumnCount(1)
        self.list_widget.setHorizontalHeaderLabels(["选项"])
        self.list_widget.setRowCount(len(self.choices))
        for i, choice in enumerate(self.choices):
            self.list_widget.setItem(i, 0, QTableWidgetItem(choice))
        self.list_widget.verticalHeader().hide()
        self.list_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.viewLayout.addWidget(self.list_widget)
        input_layout = QHBoxLayout()
        self.input_line = LineEdit()
        self.input_line.setPlaceholderText("输入新选项后点击“添加”")
        self.input_line.returnPressed.connect(self._add_choice)
        input_layout.addWidget(self.input_line)
        self.add_btn = PushButton("添加")
        self.add_btn.clicked.connect(self._add_choice)
        input_layout.addWidget(self.add_btn)
        self.viewLayout.addLayout(input_layout)
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
            self.input_line.setFocus()

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
