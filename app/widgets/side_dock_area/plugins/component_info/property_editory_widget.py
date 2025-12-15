# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QTableWidgetItem, QHeaderView,
    QFormLayout, QDialog, QSizePolicy
)
from qfluentwidgets import (
    LineEdit, PushButton,
    TableWidget, ComboBox, InfoBar, FluentIcon, MessageBoxBase, SubtitleLabel,
    DoubleSpinBox, TransparentToolButton, SimpleCardWidget
)

from app.components.base import PropertyType, PropertyDefinition
from app.widgets.node_widget.longtext_dialog import LongTextEditorDialog


class PropertyEditorWidget(SimpleCardWidget):
    """属性编辑器 - + 按钮在表头，删除按钮每行一个，对齐可靠"""
    properties_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self._dynamic_form_schemas = {}
        self._choice_configs = {}
        self._range_configs = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # === 属性表格（5 列 + 删除）===
        self.table = TableWidget()
        self.table.setColumnCount(6)  # ← 新增第 6 列：删除
        self.table.setHorizontalHeaderLabels(["属性名", "标签", "类型", "默认值", "选项", "＋"])
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.verticalHeader().setMinimumSectionSize(32)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)  # 最后一列不 stretch

        self.table.itemChanged.connect(self._on_item_changed)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)  # ← 监听表头点击

        layout.addWidget(self.table)

    def _on_header_clicked(self, logical_index):
        """点击最后一列表头时触发添加"""
        if logical_index == 5:  # 最后一列
            self._add_property()

    def _on_item_changed(self, item):
        row = self.table.row(item)
        col = item.column()
        if col == 0:  # 属性名列
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

    def _remove_property_at(self, row: int):
        """精准删除指定行"""
        if 0 <= row < self.table.rowCount():
            name_item = self.table.item(row, 0)
            if name_item:
                prop_name = name_item.text()
                self._choice_configs.pop(prop_name, None)
                self._range_configs.pop(prop_name, None)
                self._dynamic_form_schemas.pop(prop_name, None)
            self.table.removeRow(row)
            self.properties_changed.emit()

    def _on_delete_button_clicked(self):
        """通过 sender 反查行号"""
        button = self.sender()
        if not button:
            return
        for row in range(self.table.rowCount()):
            cell_widget = self.table.cellWidget(row, 5)
            if cell_widget is button:
                self._remove_property_at(row)
                return

    def _add_property(self, prop_name: str = None, prop_def: PropertyType = None):
        row = self.table.rowCount()
        self.table.insertRow(row)

        # 属性名
        name_item = QTableWidgetItem(prop_name if prop_name else f"prop{row + 1}")
        name_item.setData(Qt.UserRole, prop_name if prop_name else f"prop{row + 1}")
        name_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.table.setItem(row, 0, name_item)

        # 标签
        label = getattr(prop_def, 'label', f"属性{row + 1}")
        label_item = QTableWidgetItem(label)
        label_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.table.setItem(row, 1, label_item)

        # 类型
        type_combo = ComboBox()
        type_combo.setStyleSheet("border: none;background: transparent; color: white;")
        type_combo.setFixedHeight(28)
        for item in PropertyType:
            type_combo.addItem(item.value, userData=item)
        current_type = getattr(prop_def, 'type', PropertyType.TEXT)
        type_combo.setCurrentText(current_type.value)
        self.table.setCellWidget(row, 2, type_combo)
        type_combo.currentTextChanged.connect(lambda text, r=row: self._on_type_changed(r))

        # 默认值
        default_val = str(getattr(prop_def, 'default', ''))
        default_item = QTableWidgetItem(default_val)
        default_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.table.setItem(row, 3, default_item)

        # 操作列（第4列）
        self._update_action_widget(row, current_type, prop_name)

        # === 删除按钮（第5列）===
        delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
        delete_btn.setFixedSize(24, 24)
        delete_btn.setToolTip("删除此属性")
        delete_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        delete_btn.clicked.connect(self._on_delete_button_clicked)
        self.table.setCellWidget(row, 5, delete_btn)  # ← 直接设为 cell widget

        self.properties_changed.emit()

    def _update_action_widget(self, row, prop_type, prop_name=None):
        self.table.setItem(row, 4, None)
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
            options_item = QTableWidgetItem("")
            options_item.setFlags(options_item.flags() & ~Qt.ItemIsEditable)
            options_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.table.setItem(row, 4, options_item)

    def _on_type_changed(self, row):
        type_widget = self.table.cellWidget(row, 2)
        if not type_widget:
            return
        prop_type = type_widget.currentData() or PropertyType.TEXT
        name_item = self.table.item(row, 0)
        prop_name = name_item.text() if name_item else None
        self._update_action_widget(row, prop_type, prop_name)
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
                self.properties_changed.emit()
                InfoBar.success("成功", f"已保存下拉选项: {prop_name}", parent=self.parent, duration=1500)
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
            properties[prop_name] = prop_dict
        return properties

    def set_properties(self, properties):
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
            self._add_property(prop_name, prop_def)

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




# ==================== Dialogs ====================

class DynamicFormEditorDialog(MessageBoxBase):
    """动态表单编辑器对话框"""

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
    """范围配置对话框"""

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
    """下拉框选项配置对话框"""

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