# -*- coding: utf-8 -*-
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET
from Qt import QtWidgets, QtCore

from app.server_manager.http_server.service_manager import SERVICE_MANAGER
from app.widgets.basic_widget.combo_widget import CustomComboBox
from app.widgets.node_widget.base import CustomNodeBaseWidget


class DynamicComboBox(CustomComboBox):
    """支持弹出前发射信号的 ComboBox"""
    aboutToShow = QtCore.Signal()

    def showPopup(self):
        # 在弹出前发送信号，通知父窗口刷新数据
        self.aboutToShow.emit()
        super(DynamicComboBox, self).showPopup()


class VarComboBoxWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(str)
    fixed_height = True

    def __init__(self, main_window=None, type="全局变量", parent=None):
        super().__init__()
        self.parent = parent
        self.main_window = main_window
        self._value = ""
        self._current_type = None
        self._change_signal_connection = None

        # 使用支持“弹出感知”的 ComboBox
        self.combobox = DynamicComboBox(self)
        self.combobox.setMaxVisibleItems(12)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.combobox)

        self.combobox.addItem("无")
        self.combobox.currentIndexChanged.connect(self._on_index_changed)

        # 核心：连接下拉刷新信号
        self.combobox.aboutToShow.connect(self._refresh_on_click)

        # 设置初始 source type
        self.set_source_type(type)

    def _refresh_on_click(self):
        """点击下拉时触发的刷新逻辑"""
        config = self._get_source_config(self._current_type)
        if config:
            # 对于“画布节点”和“节点输入变量”这种没有增量信号的，每次点击都刷新
            # 对于其他有信号的，点击时刷新也可以保证数据 100% 准确
            self._refresh_options(config["get_vars"])

    def set_source_type(self, type_name: str):
        """切换变量源类型"""
        if self._current_type == type_name:
            return

        # 断开旧信号
        if self._change_signal_connection and self.main_window:
            try:
                self._change_signal_connection.disconnect(self.on_variable_changed)
            except Exception:
                pass

        self._current_type = type_name
        self._change_signal_connection = None

        config = self._get_source_config(type_name)
        if not config:
            self.combobox.clear()
            self.combobox.addItem("无")
            self._value = ""
            return

        # 初始化刷新
        self._refresh_options(config["get_vars"])

        # 连接变更信号（如果有）
        if self.main_window and config["signal_name"]:
            signal = getattr(self.main_window, config["signal_name"], None)
            if signal and hasattr(signal, 'connect'):
                signal.connect(self.on_variable_changed)
                self._change_signal_connection = signal

    def _get_source_config(self, type_name: str):
        """配置映射"""
        mapping = {
            "全局变量": {"get_vars": self._get_global_vars, "signal_name": "global_variables_changed"},
            "画布节点": {"get_vars": self._get_all_node_names, "signal_name": ""},
            "节点输入变量": {"get_vars": self._get_node_input_vars, "signal_name": ""},
            "导出项目": {"get_vars": self._get_exported_project_vars, "signal_name": "exported_projects_changed"},
            "HTTP服务": {"get_vars": self._get_running_service_vars, "signal_name": "running_projects_changed"}
        }
        return mapping.get(type_name)

    def _refresh_options(self, get_vars_func):
        """全量更新选项，并保持当前选中值"""
        current_value = self._value

        # 阻止信号触发，避免在清除/添加项时干扰业务逻辑
        self.combobox.blockSignals(True)
        self.combobox.clear()
        self.combobox.addItem("无")

        try:
            all_vars = get_vars_func()
            if all_vars:
                # 过滤并排序，保证显示整齐
                unique_vars = sorted(list(set(all_vars)))
                self.combobox.addItems(unique_vars)
        except Exception as e:
            print(f"Refresh options error: {e}")

        # 尝试恢复之前选中的值
        if current_value:
            idx = self.combobox.findText(current_value)
            if idx >= 0:
                self.combobox.setCurrentIndex(idx)
            else:
                # 如果旧值消失了（比如节点被删了），重置为空
                self.combobox.setCurrentIndex(0)
                self._value = ""
        else:
            self.combobox.setCurrentIndex(0)

        self.combobox.blockSignals(False)

    # --- 数据获取函数保持不变 ---
    def _get_global_vars(self):
        if not self.main_window: return []
        gv = getattr(self.main_window, 'global_variables', None)
        if not gv: return []
        res = [f"custom.{k}" for k in gv.custom.keys()]
        res += [f"node_vars.{k}" for k in gv.node_vars.keys()]
        env_vars = gv.env.get_all_env_vars()
        res += [f"env.{k}" for k in env_vars.keys()]
        return res

    def _get_all_node_names(self):
        if not self.main_window: return []
        return [node.name() for node in self.main_window.graph.all_nodes()]

    def _get_node_input_vars(self):
        if not self.main_window or not hasattr(self.parent, "node"): return []
        node = self.parent.node
        vars_path = []
        for p in node.input_ports():
            for connected in p.connected_ports():
                safe_name = connected.node().name().replace(" ", "_")
                vars_path.append(f"input.{safe_name}__{connected.name()}")
        return vars_path

    def _get_exported_project_vars(self):
        page = self.main_window.parent.project_manager
        paths = getattr(page, '_known_projects', set())
        return sorted(list(paths))

    def _get_running_service_vars(self):
        page = self.main_window.parent.project_manager
        known = getattr(page, '_known_projects', set())
        return sorted([p for p in known if SERVICE_MANAGER.is_running(p)])

    def on_variable_changed(self, var_name=None, operation=None):
        """保留原有的信号触发逻辑，用于即时响应 UI 变化"""
        if operation == 'add':
            if self.combobox.findText(var_name) == -1:
                self.combobox.insertItem(1, var_name)
                if not self._value or self.combobox.currentIndex() == 0:
                    self.combobox.setCurrentIndex(1)
        elif operation == 'delete':
            idx = self.combobox.findText(var_name)
            if idx >= 0:
                if self.combobox.itemText(idx) == self._value:
                    self.combobox.setCurrentIndex(0)
                self.combobox.removeItem(idx)
        else:
            config = self._get_source_config(self._current_type)
            if config:
                self._refresh_options(config["get_vars"])

    def _on_index_changed(self, index):
        self._value = self.combobox.currentText() if index > 0 else ""
        self.valueChanged.emit(self._value)

    def get_value(self):
        return self._value

    def set_value(self, value):
        self._value = value or ""
        self.combobox.blockSignals(True)
        idx = self.combobox.findText(self._value)
        if idx == -1 and self._value:
            self.combobox.addItem(self._value)
            idx = self.combobox.count() - 1
        self.combobox.setCurrentIndex(max(0, idx))
        self.combobox.blockSignals(False)


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


CustomNodeBaseWidget.VAR_WIDGET_CLASS = VarComboBoxWidget