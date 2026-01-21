# -*- coding: utf-8 -*-
import os
import pickle
import tempfile
import uuid

from qfluentwidgets import (MessageBoxBase, SubtitleLabel, BodyLabel, ComboBox, CheckBox, DoubleSpinBox, SpinBox,
                            TextEdit)

from app.plugins.base import InteractivePlugin
from app.utils.utils import ssh_send_file


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


class AskPlugin(InteractivePlugin):
    plugin_id = "ask_user"
    plugin_name = "人工干预"
    plugin_desc = "将节点中的指定信息发送给ui侧用于人工确认"
    plugin_template = """result = self.emit_interactive_message(
            method="ask_user",
            params={
                "title":"数据核对", 
                "message":"请核对以下解析结果是否正确",
                "schema":{
                    "is_correct": {"type": "bool", "label": "结果正确", "default": True},
                    "adjust_value": {"type": "float", "label": "修正偏差值", "default": 0.0},
                    "choices": {"type": "choice", "choices": ["选项1", "选项2", "选项3"], "default": "选项1"},
                    "text": {"label": "生成文本确认", "default": "测试文本"}
                }
            }
        )
"""

    def handle(self, node, params, msg=None):
        title = params.get("title", "人工干预")
        message = params.get("message", "")
        response_file = params.get("response_file")
        schema = params.get("schema")

        env_data = getattr(node.parent_window, 'env_data', None)
        is_ssh = env_data and env_data.get('type') == 'ssh'

        def on_confirmed(result_data):
            if is_ssh:
                temp_path = os.path.join(tempfile.gettempdir(), f"ask_{uuid.uuid4().hex}.pkl")
                with open(temp_path, 'wb') as f:
                    pickle.dump(result_data, f)
                ssh_send_file(env_data, temp_path, response_file)
                if os.path.exists(temp_path): os.remove(temp_path)
            else:
                os.makedirs(os.path.dirname(response_file), exist_ok=True)
                with open(response_file, 'wb') as f:
                    pickle.dump(result_data, f)

        # 创建并显示对话框
        dialog = InterventionDialog(title, message, schema, node.parent_window)
        dialog.yesButton.setText("确认并继续")
        dialog.cancelButton.hide()

        if dialog.exec():
            # 用户点击了“确认”
            result_data = dialog.get_result()
            on_confirmed(result_data)