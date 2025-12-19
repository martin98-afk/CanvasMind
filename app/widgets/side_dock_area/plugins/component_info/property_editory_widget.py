# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QTableWidgetItem, QHeaderView,
    QFormLayout, QDialog, QSizePolicy, QWidget, QSlider
)
from qfluentwidgets import (
    LineEdit, PushButton,
    TableWidget, ComboBox, InfoBar, FluentIcon, MessageBoxBase, SubtitleLabel,
    DoubleSpinBox, TransparentToolButton, SimpleCardWidget, SwitchButton, EditableComboBox, Slider, BodyLabel
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

        # === 属性表格（6 列：5 内容 + 1 删除）===
        self.table = TableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["属性名", "标签", "类型", "默认值", "选项", "＋"])
        font = QFont()
        font.setPointSize(14)  # 或 16，根据需求调整
        font.setBold(True)

        for col in range(self.table.columnCount()):
            item = self.table.horizontalHeaderItem(col)
            if item and col == self.table.columnCount() - 1:  # 最后一列
                item.setFont(font)
                item.setTextAlignment(Qt.AlignCenter)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.verticalHeader().setMinimumSectionSize(32)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)

        self.table.itemChanged.connect(self._on_item_changed)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

        layout.addWidget(self.table)

    def _on_header_clicked(self, logical_index):
        if logical_index == 5:
            self._add_property()

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

    def _remove_property_at(self, row: int):
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
        name = prop_name if prop_name else f"prop{row + 1}"
        name_item = QTableWidgetItem(name)
        name_item.setData(Qt.UserRole, name)
        name_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.table.setItem(row, 0, name_item)

        # 标签
        label = getattr(prop_def, 'label', f"属性{row + 1}")
        label_item = QTableWidgetItem(label)
        label_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.table.setItem(row, 1, label_item)

        # 类型
        type_combo = ComboBox()
        type_combo.setStyleSheet("border: none; background: transparent; color: white;")
        type_combo.setFixedHeight(28)
        for item in PropertyType:
            type_combo.addItem(item.value, userData=item)
        current_type = getattr(prop_def, 'type', PropertyType.TEXT)
        type_combo.setCurrentText(current_type.value)
        self.table.setCellWidget(row, 2, type_combo)
        type_combo.currentTextChanged.connect(lambda _, r=row: self._on_type_changed(r))

        # 默认值列（关键改动：使用 widget）
        default_val = getattr(prop_def, 'default', '')
        self._update_default_value_widget(row, current_type, name, default_val)

        # 操作列（第4列）
        self._update_action_widget(row, current_type, name)

        # 删除按钮（第5列）
        delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
        delete_btn.setFixedSize(24, 24)
        delete_btn.setToolTip("删除此属性")
        delete_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        delete_btn.clicked.connect(self._on_delete_button_clicked)
        self.table.setCellWidget(row, 5, delete_btn)

        self.properties_changed.emit()

    def _get_default_value_from_widget(self, row: int):
        widget = self.table.cellWidget(row, 3)
        if isinstance(widget, EditableComboBox) or isinstance(widget, ComboBox):
            return widget.currentText()
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

    def _adjust_line_edit_width(self, line_edit: LineEdit, max_width=120, min_width=50):
        """根据文本内容调整 LineEdit 宽度"""
        text = line_edit.text() or "0"
        # 添加一点 padding（比如 10 像素）
        fm = line_edit.fontMetrics()
        text_width = fm.horizontalAdvance(text) + 10
        # 限制在合理范围
        width = max(min_width, min(max_width, text_width))
        line_edit.setFixedWidth(width)

    def _update_default_value_widget(self, row: int, prop_type: PropertyType, prop_name: str = None, default_value=''):
        """根据类型设置默认值列的 widget"""
        self.table.setCellWidget(row, 3, None)

        if prop_type == PropertyType.CHOICE:
            # 使用原生 QComboBox（支持 setEditable）
            combo = EditableComboBox()
            combo.setStyleSheet("color: white; background: transparent; border: none;")
            choices = self._choice_configs.get(prop_name, [])
            combo.addItems(choices)
            combo.setCurrentText(default_value)
            combo.setFixedHeight(28)
            combo.currentTextChanged.connect(self.properties_changed.emit)
            self.table.setCellWidget(row, 3, combo)
        elif prop_type == PropertyType.VARIABLE:
            # 使用原生 QComboBox（支持 setEditable）
            combo = ComboBox()
            combo.setStyleSheet("color: white; background: transparent; border: none;")
            combo.addItems(["全局变量", "导出项目", "MCP工具", "HTTP服务"])
            combo.setCurrentText(default_value)
            combo.setFixedHeight(28)
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

            # 容器
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)

            slider = Slider(Qt.Horizontal)
            slider.setRange(int_min, int_max)
            slider.setSingleStep(int_step)

            # 替换 BodyLabel 为 LineEdit
            value_edit = LineEdit()
            value_edit.setStyleSheet("color: white; background: transparent; border: 1px solid #555555;")

            layout.addWidget(slider, 1)
            layout.addWidget(value_edit)

            # 初始化值
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

            self._adjust_line_edit_width(value_edit, max_width=100, min_width=40)

            # 每次内容变化后也调整（连接信号）
            value_edit.textChanged.connect(
                lambda: self._adjust_line_edit_width(value_edit, max_width=100, min_width=40)
            )

            # Slider -> LineEdit
            def on_slider_changed(val):
                float_val = val / factor
                if max_dec > 0:
                    display_str = f"{float_val:.{max_dec}f}"
                else:
                    display_str = str(int(float_val))
                value_edit.setText(display_str)
                self.properties_changed.emit()

            slider.valueChanged.connect(on_slider_changed)

            # LineEdit -> Slider（带校验）
            def on_line_edit_finished():
                text = value_edit.text().strip()
                if not text:
                    return
                try:
                    user_val = float(text)
                    # 限制在 [min_val, max_val]
                    user_val = max(min_val, min(max_val, user_val))

                    int_val = int(round(user_val * factor))
                    slider.setValue(int_val)

                    # 精确回写格式化值（防止用户输入 1.000001）
                    display_str = f"{user_val:.{max_dec}f}" if max_dec > 0 else str(int(user_val))
                    value_edit.setText(display_str)
                    self.properties_changed.emit()
                except ValueError:
                    # 输入非法，恢复为当前 slider 对应值
                    current_float = slider.value() / factor
                    display_str = f"{current_float:.{max_dec}f}" if max_dec > 0 else str(int(current_float))
                    value_edit.setText(display_str)

            value_edit.editingFinished.connect(on_line_edit_finished)

            container.setFixedHeight(28)
            self.table.setCellWidget(row, 3, container)

            # 保存元数据供读取
            container.slider = slider
            container.factor = factor
            container.max_dec = max_dec
            container.value_edit = value_edit  # 便于将来扩展

        elif prop_type == PropertyType.BOOL:
            # 创建容器
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            # 创建开关
            switch = SwitchButton(parent=container)
            switch._offText = switch.tr("False")
            switch._onText = switch.tr("True")
            # 初始化状态
            if isinstance(default_value, bool):
                checked = default_value
            else:
                checked = str(default_value).lower() in ("true", "1", "yes", "on")
            switch.setChecked(checked)
            switch.checkedChanged.connect(self.properties_changed.emit)

            # 居中：左右加 stretch
            layout.addStretch()
            layout.addWidget(switch)
            layout.addStretch()

            container.setFixedHeight(28)
            self.table.setCellWidget(row, 3, container)

            # 保存引用，便于后续读取
            container.switch = switch
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

        # 保存当前默认值，避免切换类型时丢失
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
                # 更新默认值控件（如果当前行是 RANGE 类型）
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
                # 更新默认值控件（如果当前行是 CHOICE 类型）
                if self.table.cellWidget(row, 2).currentData() == PropertyType.CHOICE:
                    self._update_default_value_widget(row, PropertyType.CHOICE, prop_name,
                                                      self._get_default_value_from_widget(row))
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
            current_text = self._get_default_value_from_widget(row)
            dialog = LongTextEditorDialog(current_text, self.window(), self.parent)
            if dialog.exec() == QDialog.Accepted:
                new_text = dialog.text_edit.toPlainText()
                # 直接更新 widget（当前是 LineEdit）
                widget = self.table.cellWidget(row, 3)
                if isinstance(widget, LineEdit):
                    widget.setText(new_text)
                self.properties_changed.emit()
                InfoBar.success("成功", "长文本已更新", parent=self.parent, duration=1500)
        except Exception as e:
            import traceback
            traceback.print_exc()
            InfoBar.error("错误", f"编辑失败: {str(e)}", parent=self.parent, duration=3000)


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
