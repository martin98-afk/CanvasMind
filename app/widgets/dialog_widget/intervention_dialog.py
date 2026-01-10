from qfluentwidgets import (MessageBoxBase, SubtitleLabel, BodyLabel, LineEdit,
                            ComboBox, CheckBox, DoubleSpinBox, SpinBox, TextEdit)
from app.components.base import PropertyType

class InterventionDialog(MessageBoxBase):
    """
    自适应动态表单对话框，用于人工干预
    """
    def __init__(self, title: str, message: str, schema: dict, parent=None):
        super().__init__(parent)
        self.schema = schema or {}
        self.inputs = {}

        # 1. 标题
        self.titleLabel = SubtitleLabel(title)
        self.viewLayout.addWidget(self.titleLabel)

        # 2. 提示信息
        if message:
            self.messageLabel = BodyLabel(message)
            self.messageLabel.setWordWrap(True)
            self.viewLayout.addWidget(self.messageLabel)

        # 3. 动态根据 schema 生成表单
        self._setup_dynamic_form()

        # 设置对话框宽度
        self.widget.setMinimumWidth(700)
        self.widget.setMinimumHeight(600)

    def _setup_dynamic_form(self):
        for field_name, prop_def in self.schema.items():
            label_text = prop_def.get("label", field_name)
            prop_type = prop_def.get("type")
            default = prop_def.get("default")

            # 添加字段标签
            field_label = BodyLabel(f"{label_text}:")
            self.viewLayout.addWidget(field_label)

            # 根据类型创建控件
            if prop_type == PropertyType.BOOL:
                widget = CheckBox()
                widget.setChecked(bool(default))
                self.viewLayout.addWidget(widget)
                self.inputs[field_name] = (widget, "isChecked")

            elif prop_type == PropertyType.CHOICE:
                widget = ComboBox()
                choices = prop_def.get("choices", [])
                widget.addItems(choices)
                if default in choices:
                    widget.setCurrentText(default)
                self.viewLayout.addWidget(widget)
                self.inputs[field_name] = (widget, "currentText")

            elif prop_type in [PropertyType.INT, PropertyType.FLOAT, PropertyType.RANGE]:
                if prop_type == PropertyType.INT:
                    widget = SpinBox()
                    widget.setRange(int(prop_def.get("min", -999999)), int(prop_def.get("max", 999999)))
                    widget.setValue(int(default or 0))
                else:
                    widget = DoubleSpinBox()
                    widget.setRange(float(prop_def.get("min", -999999)), float(prop_def.get("max", 999999)))
                    widget.setValue(float(default or 0))
                self.viewLayout.addWidget(widget)
                self.inputs[field_name] = (widget, "value")

            else:  # 默认文本 LineEdit
                widget = TextEdit()
                widget.setText(str(default or ""))
                self.viewLayout.addWidget(widget)
                self.inputs[field_name] = (widget, "toPlainText")

    def get_result(self):
        """解析所有控件的值并返回字典"""
        result = {}
        for field_name, (widget, getter_name) in self.inputs.items():
            getter = getattr(widget, getter_name)
            # 处理可调用对象或直接属性
            val = getter() if callable(getter) else getter
            result[field_name] = val
        return result