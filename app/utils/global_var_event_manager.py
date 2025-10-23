# -*- coding: utf-8 -*-
from PyQt5.QtCore import QObject, pyqtSignal

class GlobalVarEventManager(QObject):
    """
    全局变量事件管理器，用于分发更细粒度的变量变化事件。
    """
    # 信号：变量被添加
    var_added = pyqtSignal(str, str) # var_type, var_name
    # 信号：变量被删除
    var_removed = pyqtSignal(str, str) # var_type, var_name
    # 信号：变量值或策略被更新（如果需要）
    var_updated = pyqtSignal(str, str) # var_type, var_name
    # 信号：所有变量被清空或重置
    all_vars_cleared = pyqtSignal()

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._previous_state = self._get_current_state()
        # 连接总的变化信号，用于检测变化
        if hasattr(main_window, 'global_variables_changed'):
            main_window.global_variables_changed.connect(self._on_global_vars_changed)

    def _get_current_state(self):
        """获取当前所有变量的集合表示"""
        global_vars = getattr(self.main_window, 'global_variables', None)
        if not global_vars:
            return {'env': set(), 'custom': set(), 'node_vars': set()}

        env_keys = set(global_vars.env.get_all_env_vars().keys())
        custom_keys = set(global_vars.custom.keys())
        node_vars_keys = set(global_vars.node_vars.keys())
        return {'env': env_keys, 'custom': custom_keys, 'node_vars': node_vars_keys}

    def _on_global_vars_changed(self):
        """监听总变化信号，比较前后状态，分发具体事件"""
        current_state = self._get_current_state()

        # 检查新增的变量
        for var_type, current_keys in current_state.items():
            previous_keys = self._previous_state.get(var_type, set())
            new_keys = current_keys - previous_keys
            for key in new_keys:
                self.var_added.emit(var_type, key)

        # 检查删除的变量
        for var_type, previous_keys in self._previous_state.items():
            current_keys = current_state.get(var_type, set())
            removed_keys = previous_keys - current_keys
            for key in removed_keys:
                self.var_removed.emit(var_type, key)

        # 更新内部状态
        self._previous_state = current_state

    def notify_all_cleared(self):
        """手动通知所有变量被清空"""
        self.all_vars_cleared.emit()
        self._previous_state = {'env': set(), 'custom': set(), 'node_vars': set()}