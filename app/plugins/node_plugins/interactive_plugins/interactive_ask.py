# -*- coding: utf-8 -*-
from typing import Any, Dict

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QScrollArea, QFormLayout, QWidget, QDialog, QSizePolicy)
from qfluentwidgets import (MessageBoxBase, SubtitleLabel, BodyLabel, ComboBox,
                            DoubleSpinBox, SpinBox, LineEdit, TextEdit,
                            SwitchButton)

from app.plugins.node_plugins.base import InteractivePlugin


class InterventionDialog(MessageBoxBase):
    """
    自适应动态表单对话框，用于人工干预
    优化点：支持滚动、表单布局、更丰富的控件映射、数据校验
    """

    def __init__(self, title: str, message: str, schema: dict, parent=None):
        super().__init__(parent)
        self.schema = schema or {}
        self.field_widgets: Dict[str, Any] = {}  # 存储字段名与控件的映射
        self.field_types: Dict[str, str] = {}  # 存储字段名与类型的映射

        # 1. 标题
        self.titleLabel = SubtitleLabel(title)
        self.titleLabel.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        self.viewLayout.addWidget(self.titleLabel)

        # 2. 提示信息
        if message:
            self.messageLabel = BodyLabel(message)
            self.messageLabel.setWordWrap(True)
            self.messageLabel.setStyleSheet("margin-bottom: 15px;")
            self.viewLayout.addWidget(self.messageLabel)

        # 3. 滚动区域容器 (防止表单过长)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # 表单内容容器
        self.form_container = QWidget()
        self.form_layout = QFormLayout()
        self.form_layout.setSpacing(5)  # 控件间距
        self.form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.form_container.setLayout(self.form_layout)

        self.scroll_area.setWidget(self.form_container)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.viewport().setStyleSheet("background-color: transparent;")
        self.scroll_area.setStyleSheet("""
                QScrollArea { background-color: transparent; border: none; }
                QScrollBar:vertical { background: transparent; width: 6px; margin-right: 2px; }
                QScrollBar::handle:vertical { background: rgba(120, 120, 120, 150); border-radius: 4px; }
                QScrollBar::add-line, QScrollBar::sub-line { height: 0px; }
                """)
        self.viewLayout.addWidget(self.scroll_area)

        # 4. 动态生成表单
        self._setup_dynamic_form()

        # 5. 对话框尺寸
        self.widget.setMinimumWidth(600)
        # 不需要强制最小高度，由内容决定，但限制最大高度由 scroll_area 处理

    def _setup_dynamic_form(self):
        """根据 schema 动态创建表单控件"""
        for field_name, prop_def in self.schema.items():
            if not isinstance(prop_def, dict):
                continue

            label_text = prop_def.get("label", field_name)
            prop_type = prop_def.get("type", "text")
            default = prop_def.get("default")
            required = prop_def.get("required", False)

            # 添加必填标记
            if required:
                label_text += " *"

            widget = self._create_widget_by_type(prop_type, prop_def, default)

            # 存储引用以便后续获取值
            self.field_widgets[field_name] = widget
            self.field_types[field_name] = prop_type

            # 添加到表单布局
            self.form_layout.addRow(label_text, widget)

    def _create_widget_by_type(self, prop_type: str, prop_def: dict, default: Any) -> QWidget:
        """工厂方法：根据类型创建对应的 Fluent 控件"""

        # 布尔型 -> 开关
        if prop_type == "bool":
            widget = SwitchButton()
            widget.setChecked(bool(default) if default is not None else False)
            # SwitchButton 没有文本标签，通常放在右侧，这里通过 addRow 的 label 参数处理左侧文字
            return widget

        # 选择型 -> 下拉框
        elif prop_type == "choice":
            widget = ComboBox()
            choices = prop_def.get("choices", [])
            widget.addItems(choices)
            if default and default in choices:
                widget.setCurrentText(default)
            elif choices:
                widget.setCurrentIndex(0)
            return widget

        # 数值型 -> 数字输入框
        elif prop_type == "int":
            widget = SpinBox()
            min_val = int(prop_def.get("min", -2147483648))
            max_val = int(prop_def.get("max", 2147483647))
            widget.setRange(min_val, max_val)
            widget.setValue(int(default) if default is not None else 0)
            return widget

        elif prop_type == "float":
            widget = DoubleSpinBox()
            min_val = float(prop_def.get("min", -1e9))
            max_val = float(prop_def.get("max", 1e9))
            widget.setRange(min_val, max_val)
            widget.setDecimals(prop_def.get("decimals", 2))
            widget.setValue(float(default) if default is not None else 0.0)
            return widget

        # 多行文本 -> TextEdit
        elif prop_type == "long_text":
            widget = TextEdit()
            widget.setPlaceholderText("请输入详细内容...")
            widget.setText(str(default) if default is not None else "")
            widget.setMaximumHeight(150)  # 限制高度，配合滚动条
            return widget

        # 默认单行文本 -> LineEdit
        else:
            widget = LineEdit()
            widget.setPlaceholderText(f"请输入{prop_def.get('label')}")
            widget.setText(str(default) if default is not None else "")
            return widget

    def get_result(self) -> Dict[str, Any]:
        """解析所有控件的值并返回字典，进行类型转换"""
        result = {}
        for field_name, widget in self.field_widgets.items():
            prop_type = self.field_types.get(field_name, "text")
            val = None

            try:
                if isinstance(widget, SwitchButton):
                    val = widget.isChecked()
                elif isinstance(widget, ComboBox):
                    val = widget.currentText()
                elif isinstance(widget, (SpinBox, DoubleSpinBox)):
                    val = widget.value()
                elif isinstance(widget, TextEdit):
                    val = widget.toPlainText()
                elif isinstance(widget, LineEdit):
                    val = widget.text()
                else:
                    val = str(widget)
            except Exception as e:
                print(f"Error getting value for {field_name}: {e}")
                val = None

            # 确保类型与 Schema 定义一致 (可选，增强健壮性)
            if val is not None:
                if prop_type == "int":
                    val = int(val)
                elif prop_type == "float":
                    val = float(val)
                elif prop_type == "bool":
                    val = bool(val)

            result[field_name] = val

        return result


class AskPlugin(InteractivePlugin):
    plugin_id = "ask_user"
    plugin_name = "人工干预"
    plugin_desc = "将节点中的指定信息发送给 UI 侧用于人工确认和修改"

    # 优化后的模板，展示更多字段类型
    plugin_template = """result = self.emit_interactive_message(
    method="ask_user",
    params={
        "title": "数据核对与修正", 
        "message": "请核对以下解析结果，如有错误请修正后继续。",
        "schema": {
            "is_correct": {"type": "bool", "label": "确认无误", "default": True},
            "confidence": {"type": "float", "label": "置信度", "default": 0.95, "min": 0.0, "max": 1.0},
            "category": {"type": "choice", "label": "分类", "choices": ["A 类", "B 类", "C 类"], "default": "A 类"},
            "count": {"type": "int", "label": "数量", "default": 1, "min": 0},
            "remark": {"type": "text", "label": "备注说明", "default": ""},
            "detail_log": {"type": "long_text", "label": "详细日志", "default": ""}
        }
    }
)
"""

    def operate(self, node, params, msg=None):
        title = params.get("title", "人工干预")
        message = params.get("message", "")
        schema = params.get("schema", {})

        # 获取主窗口引用 (假设 node 有 parent_window 属性)
        parent_window = getattr(node, 'parent_window', None)

        # 创建对话框
        dialog = InterventionDialog(title, message, schema, parent_window)

        # 自定义按钮文本
        dialog.yesButton.setText("确认提交")
        dialog.cancelButton.setText("取消")
        # 注意：如果业务逻辑不允许取消，可以隐藏 cancelButton，但建议保留以便用户退出
        # dialog.cancelButton.hide()

        # 显示对话框并等待结果
        # MessageBoxBase.exec() 返回 QDialog.DialogCode
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_result()
        else:
            # 用户取消或关闭对话框
            return None