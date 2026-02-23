# -*- coding: utf-8 -*-
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from Qt import QtWidgets, QtCore
from qfluentwidgets import FluentIcon, TransparentToolButton
from qfluentwidgets import MessageBoxBase, SubtitleLabel

from app.widgets.basic_widget.variable_complete_widget import VariableCompletionTextEdit, VariableCompletionLineEdit
from app.widgets.node_widget.base import CustomNodeBaseWidget


# -----------------------
# 改造后的对话框
# -----------------------
class LongTextEditorDialog(MessageBoxBase):
    def __init__(self, content: str = "", parent=None, main_window=None, extra_keys=[], get_port_func=lambda: []):
        super().__init__(parent)
        self.main_window = main_window
        self.titleLabel = SubtitleLabel("编辑长文本")
        if not self.main_window:
            return []
        global_vars = getattr(self.main_window, 'global_variables', None)
        self.text_edit = VariableCompletionTextEdit(
            get_variable_list_func=lambda keys=extra_keys, func=get_port_func: global_vars.get_vars(keys + func()),
            parent=self
        )
        self.text_edit.setPlainText(content)
        self.text_edit.setMinimumSize(700, 500)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.text_edit)

        self.yesButton.setText("保存")
        self.cancelButton.setText("取消")

    def get_content(self) -> str:
        return self.text_edit.toPlainText()


class LongTextWidget(QtWidgets.QFrame):  # 改为 QFrame 以支持背景和边框
    """节点内显示：摘要 + 编辑按钮 (深色主题优化版)"""
    valueChanged = QtCore.Signal(str)
    fixed_height = True

    def __init__(self, parent=None, default_text="", get_port_func=lambda: []):
        super().__init__(parent)
        self.main_window = parent
        self._text = default_text
        self.get_port_func = get_port_func

        # 1. 统一的样式配置
        self.setObjectName("LongTextWidget")
        self.setStyleSheet("""
            #LongTextWidget {
                border: 1px solid rgba(255, 255, 255, 40);
                border-radius: 6px;
                background-color: rgba(30, 30, 30, 150);
            }
            #LongTextWidget:hover {
                border: 1px solid rgba(255, 255, 255, 80);
                background-color: rgba(45, 45, 45, 180);
            }
        """)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)  # 保持与 FileSelectWidget 一致的内边距
        layout.setSpacing(4)

        # 2. 摘要显示框 (使用 VariableCompletionLineEdit)
        global_vars = getattr(self.main_window, 'global_variables', None)
        self.summary_label = VariableCompletionLineEdit(
            get_variable_list_func=lambda func=get_port_func: global_vars.get_vars(func()) if global_vars else [],
            use_qcursor=False,
            parent=self
        )
        self.summary_label.setText(self._get_summary())
        self.summary_label.setReadOnly(True)
        self.summary_label.setCursor(QtCore.Qt.ArrowCursor)  # 只读状态显示普通箭头

        # 3. 编辑按钮
        self.edit_btn = TransparentToolButton(FluentIcon.EDIT, self)
        self.edit_btn.setFixedSize(28, 28)  # 统一按钮尺寸
        self.edit_btn.setIconSize(QtCore.QSize(16, 16))
        self.edit_btn.setToolTip("编辑详细内容")
        self.edit_btn.clicked.connect(self._open_editor)

        layout.addWidget(self.summary_label)
        layout.addWidget(self.edit_btn)

    def _get_summary(self):
        # 优化摘要显示：去除换行符，限制长度
        text = (self._text or "").replace('\n', ' ').replace('\r', ' ')
        if len(text) > 30:
            return text[:30] + "..."
        return text if text else "点击右侧按钮输入内容..."

    def _open_editor(self):
        # 弹出编辑器对话框
        dialog = LongTextEditorDialog(
            self._text,
            self.main_window,
            self.main_window,
            get_port_func=self.get_port_func
        )
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            new_text = dialog.text_edit.toPlainText()
            if new_text != self._text:
                self._text = new_text
                self.summary_label.setText(self._get_summary())
                self.valueChanged.emit(self._text)

    def get_value(self):
        return self._text

    def set_value(self, text):
        self._text = text or ""
        self.summary_label.setText(self._get_summary())

    def setText(self, text):
        self.set_value(text)

    def currentText(self):
        return self._text

    def sizeHint(self):
        return QtCore.QSize(240, 32)


class LongTextWidgetWrapper(CustomNodeBaseWidget):
    def __init__(self, parent=None, name="", label="", default="", window=None, z_value=1):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET + z_value)
        self.set_name(name)
        self.set_label(f"{label}({name})")
        widget = LongTextWidget(default_text=default, parent=window, get_port_func=self.get_port_func)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def _get_local_value(self):
        return self.get_custom_widget().get_value()

    def _set_local_value(self, value):
        self.get_custom_widget().set_value(value)