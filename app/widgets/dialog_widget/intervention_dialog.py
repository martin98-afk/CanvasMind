import base64

from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QScrollArea, QLabel
from qfluentwidgets import (MessageBoxBase, SubtitleLabel, BodyLabel, ComboBox, CheckBox, DoubleSpinBox, SpinBox,
                            TextEdit)

from app.widgets.basic_widget.mask_canvas import MaskCanvas


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

    def _add_shortcut_hint(self):
        hint_text = (
            "<b>快捷键说明:</b><br>"
            "• 左键拖动：绘制蒙版 • CTRL+Z：撤销 ; • [ ]：调整笔刷大小; • C：清空; S: 切换笔刷颜色;<br>"
        )
        hint_label = BodyLabel(hint_text)
        hint_label.setStyleSheet("font-size: 11px; color: #888;")
        self.viewLayout.addWidget(hint_label)

    def _setup_dynamic_form(self):
        for field_name, prop_def in self.schema.items():
            label_text = prop_def.get("label", field_name)
            prop_type = prop_def.get("type")
            default = prop_def.get("default")

            # 添加字段标签
            field_label = BodyLabel(f"{label_text}:")
            self.viewLayout.addWidget(field_label)

            # 根据类型创建控件
            if prop_type == "bool":
                widget = CheckBox()
                widget.setChecked(bool(default))
                self.viewLayout.addWidget(widget)
                self.inputs[field_name] = (widget, "isChecked")

            elif prop_type == "choice":
                widget = ComboBox()
                choices = prop_def.get("choices", [])
                widget.addItems(choices)
                if default in choices:
                    widget.setCurrentText(default)
                self.viewLayout.addWidget(widget)
                self.inputs[field_name] = (widget, "currentText")

            elif prop_type in ("int", "float", "range"):
                if prop_type == "int":
                    widget = SpinBox()
                    widget.setRange(int(prop_def.get("min", -999999)), int(prop_def.get("max", 999999)))
                    widget.setValue(int(default or 0))
                else:
                    widget = DoubleSpinBox()
                    widget.setRange(float(prop_def.get("min", -999999)), float(prop_def.get("max", 999999)))
                    widget.setValue(float(default or 0))
                self.viewLayout.addWidget(widget)
                self.inputs[field_name] = (widget, "value")
            elif prop_type == "image":
                if prop_def.get("enable_mask"):
                    self._add_shortcut_hint()
                    default_img = default or ""
                    if not isinstance(default_img, str):
                        default_img = ""
                    canvas = MaskCanvas(default_img)
                    scroll = QScrollArea()
                    scroll.setWidget(canvas)
                    scroll.setWidgetResizable(True)
                    scroll.setMinimumHeight(400)
                    self.viewLayout.addWidget(scroll)
                    self.inputs[field_name] = (canvas, "get_mask_base64")  # ← 注意方法名
                else:
                    # 普通图片显示（只读预览，不支持绘制）
                    # 可选：用 QLabel 显示缩略图
                    image_data = base64.b64decode(default_img.split(",")[-1])  # 支持 data:image/png;base64,...
                    self.original_pixmap = QPixmap()
                    self.original_pixmap.loadFromData(image_data)
                    widget = QLabel()
                    widget.setPixmap(self.original_pixmap)
                    self.viewLayout.addWidget(widget)
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