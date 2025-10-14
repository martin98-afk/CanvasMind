"""
@author: mading
@license: (C) Copyright: LUCULENT Corporation Limited.
@contact: mading@luculent.net
@file: variable_combo_widget.py
@time: 2025/10/14 11:35
@desc: 
"""
from NodeGraphQt import NodeBaseWidget
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from Qt import QtWidgets, QtCore

from app.widgets.basic_widget.combo_widget import CustomComboBox


class GlobalVarComboBoxWidget(QtWidgets.QWidget):
    """全局变量选择下拉框（动态加载）"""
    valueChanged = QtCore.Signal(str)

    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self._value = ""

        # 使用 CustomComboBox（和普通 ComboBoxWidget 一致）
        self.combobox = CustomComboBox(self)
        self.combobox.setMaxVisibleItems(12)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.combobox)

        # 初始化选项
        self._refresh_options()

        # 连接信号
        self.combobox.currentIndexChanged.connect(self._on_index_changed)

        # 监听全局变量变化（需要 main_window 有 global_vars_changed 信号）
        if self.main_window and hasattr(self.main_window, 'global_variables_changed'):
            self.main_window.global_variables_changed.connect(self._refresh_options)

    def _refresh_options(self):
        """动态加载所有全局变量"""
        # 保存当前值
        current_value = self._value

        # 清空选项
        self.combobox.clear()
        self.combobox.addItem("无")  # 默认选项

        if not self.main_window:
            return

        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return

        # 收集所有变量（带作用域前缀）
        all_vars = []

        # 1. 环境变量
        env_vars = global_vars.env.get_all_env_vars()
        for key in sorted(env_vars.keys()):
            all_vars.append(f"env.{key}")

        # 2. 自定义变量
        for key in sorted(global_vars.custom.keys()):
            all_vars.append(f"custom.{key}")

        # 3. 节点输出变量
        for key in sorted(global_vars.node_vars.keys()):
            all_vars.append(f"node_vars.{key}")

        # 添加到下拉框
        if all_vars:
            self.combobox.addItems(all_vars)

        # 恢复当前值
        if current_value:
            index = self.combobox.findText(current_value)
            if index >= 0:
                self.combobox.setCurrentIndex(index)
            else:
                # 如果当前值不在选项中（如变量被删除），重置为"无"
                self.combobox.setCurrentIndex(0)
                self._value = ""

    def _on_index_changed(self, index):
        """处理选项变化"""
        self._value = self.combobox.currentText()
        # 如果选择"无"，值设为空字符串
        if self._value == "无":
            self._value = ""
        self.valueChanged.emit(self._value)

    def get_value(self):
        return self._value

    def set_value(self, value):
        """设置值（支持动态补充选项）"""
        self._value = value or ""
        if self._value:
            # 确保选项存在（防止变量被删除后无法显示）
            index = self.combobox.findText(self._value)
            if index == -1:
                self.combobox.addItem(self._value)
                index = self.combobox.count() - 1
            self.combobox.setCurrentIndex(index)
        else:
            self.combobox.setCurrentIndex(0)  # "无"


class GlobalVarComboBoxWidgetWrapper(NodeBaseWidget):
    """全局变量下拉框包装器（用于 NodeGraphQt）"""

    def __init__(self, parent=None, name="", label="", main_window=None, z_value=1):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET + z_value)
        self.set_name(name)
        self.set_label(label)

        # 创建自定义控件
        widget = GlobalVarComboBoxWidget(main_window=main_window)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)