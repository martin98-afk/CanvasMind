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

from app.server_manager.http_server.service_manager import SERVICE_MANAGER
from app.widgets.basic_widget.combo_widget import CustomComboBox
from app.widgets.node_widget.base import CustomNodeBaseWidget


class VarComboBoxWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(str)

    def __init__(self, main_window=None, type="全局变量", parent=None):
        super().__init__()
        self.main_window = main_window
        self._value = ""
        self._current_type = None
        self._change_signal_connection = None  # 用于断开旧信号

        self.combobox = CustomComboBox(self)
        self.combobox.setMaxVisibleItems(12)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.combobox)
        self.combobox.addItem("无")
        self.combobox.currentIndexChanged.connect(self._on_index_changed)

        # 设置 source type
        self.set_source_type(type)

    def set_source_type(self, type_name: str):
        """切换变量源类型，只激活一个 source"""
        if self._current_type == type_name:
            return

        # 断开旧信号（如果有）
        if self._change_signal_connection and self.main_window:
            try:
                self._change_signal_connection.disconnect(self.on_variable_changed)
            except Exception:
                pass  # 忽略已断开的情况

        self._current_type = type_name
        self._change_signal_connection = None

        # 根据 type 映射到具体配置
        config = self._get_source_config(type_name)
        if not config:
            # 未知类型，清空
            self.combobox.clear()
            self.combobox.addItem("无")
            self._value = ""
            return

        # 刷新选项
        self._refresh_options(config["get_vars"])

        # 连接变更信号
        if self.main_window and config["signal_name"]:
            signal = getattr(self.main_window, config["signal_name"], None)
            if signal and hasattr(signal, 'connect'):
                signal.connect(self.on_variable_changed)
                self._change_signal_connection = signal

    def _get_source_config(self, type_name: str):
        """根据 type 返回 source 配置"""
        # 未来可在此扩展其他类型，如 "局部变量"、"上下文变量" 等
        if type_name == "全局变量":
            return {
                "get_vars": self._get_global_vars,
                "signal_name": "global_variables_changed"
            }
        elif type_name == "导出项目":
            return {
                "get_vars": self._get_exported_project_vars,
                "signal_name": "exported_projects_changed"
            }
        elif type_name == "HTTP服务":
            return {
                "get_vars": self._get_running_service_vars,
                "signal_name": "running_projects_changed"
            }
        else:
            return None

    def _get_global_vars(self):
        """获取全局变量列表（带前缀）"""
        if not self.main_window:
            return []
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return []

        all_vars = []
        for key in sorted(global_vars.custom.keys()):
            all_vars.append(f"custom.{key}")
        for key in sorted(global_vars.node_vars.keys()):
            all_vars.append(f"node_vars.{key}")
        env_vars = global_vars.env.get_all_env_vars()
        for key in sorted(env_vars.keys()):
            all_vars.append(f"env.{key}")
        return all_vars

    def _get_exported_project_vars(self):
        """返回所有导出项目：值=路径，显示=项目名，格式: exported_project|{path}"""
        page = self.main_window.parent.project_manager
        paths = getattr(page, '_known_projects', set())
        items = []
        for path in sorted(paths):
            # 使用特殊分隔符 encode 路径，避免与显示名混淆
            encoded = path
            items.append(encoded)
        return items

    def _get_running_service_vars(self):
        """返回所有运行中的 HTTP 服务项目"""
        page = self.main_window.parent.project_manager
        known = getattr(page, '_known_projects', set())
        running_paths = [p for p in known if SERVICE_MANAGER.is_running(p)]
        items = []
        for path in sorted(running_paths):
            encoded = path
            items.append(encoded)
        return items

    def _refresh_options(self, get_vars_func):
        current_value = self._value
        self.combobox.clear()
        self.combobox.addItem("无")

        try:
            all_vars = get_vars_func()
            # all_vars = sorted(set(all_vars))
            if all_vars:
                self.combobox.addItems(all_vars)
        except Exception:
            pass  # 容错

        # 恢复选中
        if current_value:
            idx = self.combobox.findText(current_value)
            if idx >= 0:
                self.combobox.setCurrentIndex(idx)
                self._value = current_value
            else:
                self.combobox.setCurrentIndex(0)
                self._value = ""

    def on_variable_changed(self, var_name, operation):
        """处理变量变更：新变量置顶，重命名自动同步"""

        if operation == 'add':
            # 1. 检查是否已经存在（防止重复添加）
            existing_idx = self.combobox.findText(var_name)

            if existing_idx == -1:
                # 2. 【核心修改】：插入到索引 1 的位置（即“无”的下面，作为最上面的有效项）
                self.combobox.insertItem(1, var_name)
                new_idx = 1
            else:
                new_idx = existing_idx

            # 3. 【自动同步】：如果当前是“无”（self._value为空），自动选中这个新加/新重命名的变量
            # 在重命名流程中，delete信号已经把值清空了，所以这里会精准命中并选中新名字
            if not self._value or self.combobox.currentIndex() == 0:
                self.combobox.setCurrentIndex(new_idx)

        elif operation == 'delete':
            idx = self.combobox.findText(var_name)
            if idx >= 0:
                # 4. 如果删除的是当前选中的项，先切回“无”
                if self.combobox.itemText(idx) == self._value:
                    self.combobox.setCurrentIndex(0)
                    # 此时 self._value 会由于触发 _on_index_changed 变成 ""

                # 从列表中移除旧变量
                self.combobox.removeItem(idx)

    def _insert_sorted(self, text):
        insert_pos = 1
        for i in range(1, self.combobox.count()):
            if self.combobox.itemText(i) > text:
                break
            insert_pos = i + 1
        self.combobox.insertItem(insert_pos, text)

    def _on_index_changed(self, index):
        self._value = self.combobox.currentText() if index > 0 else ""
        self.valueChanged.emit(self._value)

    def get_value(self):
        return self._value

    def currentText(self):
        return self.combobox.currentText()

    def set_value(self, value):
        self._value = value or ""
        if self._value:
            idx = self.combobox.findText(self._value)
            if idx == -1:
                self.combobox.addItem(self._value)
                idx = self.combobox.count() - 1
            self.combobox.setCurrentIndex(idx)
        else:
            self.combobox.setCurrentIndex(0)


class VarComboBoxWidgetWrapper(CustomNodeBaseWidget):
    """全局变量下拉框包装器（用于 NodeGraphQt）"""

    def __init__(self, parent=None, name="", label="", var_type="全局变量", main_window=None, z_value=10):
        super().__init__(parent)
        self.setZValue(Z_VAL_NODE_WIDGET + z_value)
        self.set_name(name)
        self.set_label(f"{label}({name})({var_type})")

        # 创建自定义控件
        widget = VarComboBoxWidget(main_window=main_window, type=var_type, parent=parent)
        self.set_custom_widget(widget)
        widget.valueChanged.connect(self.on_value_changed)

    def get_value(self):
        return self.get_custom_widget().get_value()

    def set_value(self, value):
        self.get_custom_widget().set_value(value)